/// <reference lib="dom" />
import { expect, test, type Page } from '@playwright/test';
import { mkdir } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const screenshots = resolve(dirname(fileURLToPath(import.meta.url)), '../../docs/screenshots');

const crcTable = Array.from({ length: 256 }, (_, value) => {
  let crc = value;
  for (let bit = 0; bit < 8; bit += 1) crc = (crc >>> 1) ^ ((crc & 1) ? 0xedb88320 : 0);
  return crc >>> 0;
});

function crc32(data: Buffer) {
  let crc = 0xffffffff;
  for (const byte of data) crc = (crc >>> 8) ^ crcTable[(crc ^ byte) & 0xff];
  return (crc ^ 0xffffffff) >>> 0;
}

function zip(entries: Record<string, string>) {
  const localParts: Buffer[] = [];
  const centralParts: Buffer[] = [];
  let offset = 0;
  for (const [filename, contents] of Object.entries(entries)) {
    const name = Buffer.from(filename, 'utf8');
    const body = Buffer.from(contents, 'utf8');
    const checksum = crc32(body);
    const local = Buffer.alloc(30);
    local.writeUInt32LE(0x04034b50, 0);
    local.writeUInt16LE(20, 4);
    local.writeUInt32LE(checksum, 14);
    local.writeUInt32LE(body.length, 18);
    local.writeUInt32LE(body.length, 22);
    local.writeUInt16LE(name.length, 26);
    localParts.push(local, name, body);

    const central = Buffer.alloc(46);
    central.writeUInt32LE(0x02014b50, 0);
    central.writeUInt16LE(20, 4);
    central.writeUInt16LE(20, 6);
    central.writeUInt32LE(checksum, 16);
    central.writeUInt32LE(body.length, 20);
    central.writeUInt32LE(body.length, 24);
    central.writeUInt16LE(name.length, 28);
    central.writeUInt32LE(offset, 42);
    centralParts.push(central, name);
    offset += local.length + name.length + body.length;
  }
  const centralSize = centralParts.reduce((total, part) => total + part.length, 0);
  const end = Buffer.alloc(22);
  end.writeUInt32LE(0x06054b50, 0);
  end.writeUInt16LE(Object.keys(entries).length, 8);
  end.writeUInt16LE(Object.keys(entries).length, 10);
  end.writeUInt32LE(centralSize, 12);
  end.writeUInt32LE(offset, 16);
  return Buffer.concat([...localParts, ...centralParts, end]);
}
const solution = [
  'import sys',
  '',
  'def solve():',
  '    data = list(map(int, sys.stdin.buffer.read().split()))',
  '    n, values = data[0], data[1:]',
  '',
  '    # Best sum ending here, and best sum seen so far.',
  '    current = best = values[0]',
  '    for value in values[1:n]:',
  '        current = max(value, current + value)',
  '        best = max(best, current)',
  '',
  '    print(best)',
  '',
  'if __name__ == "__main__":',
  '    solve()',
].join('\n');

const examples = [
  { input: '9\n-2 1 -3 4 -1 2 1 -5 4', output: '6' },
  { input: '4\n-8 -3 -6 -2', output: '-2' },
  { input: '5\n1 2 3 4 5', output: '15' },
];

const explanation = [
  '### Build the answer one position at a time',
  'Let $d_i$ be the best sum of a **non-empty subarray ending at position $i$**.',
  '',
  '$$',
  'd_i = \\max(a_i, d_{i-1} + a_i)',
  '$$',
  '',
  '1. **Start fresh** at the current element.',
  '2. **Extend** the previous subarray if its sum helps.',
  '3. Keep the largest value seen so far.',
  '',
  'Initialize both values to the first element, so an all-negative array works too.',
  '',
  '**Complexity:** $O(N)$ time and $O(1)$ extra space.',
  '',
  '### An edge case to try',
  '```json',
  '{"input":"4\\n-8 -3 -6 -2","output":"-2"}',
  '```',
].join('\n');

async function capture(page: Page, name: string) {
  await page.evaluate(() => document.fonts.ready);
  await page.mouse.move(0, 0);
  await page.screenshot({ path: resolve(screenshots, name), animations: 'disabled', caret: 'hide' });
}

test('capture the README application gallery', async ({ page, request }) => {
  test.setTimeout(120_000);
  await mkdir(screenshots, { recursive: true });
  expect((await request.delete('/api/database')).ok()).toBeTruthy();
  const existingLibraries = (await (await request.get('/api/workspace/uploads')).json()).uploads ?? [];
  for (const library of existingLibraries) {
    expect((await request.delete(`/api/workspace/uploads/${library.id}`)).ok()).toBeTruthy();
  }
  const created = await request.post('/api/problems', { data: {
    title: 'Maximum Subarray Sum', difficulty: 'Medium', language: 'en',
    tags: ['Dynamic Programming', 'Arrays'],
    problem_statements: [
      'Given an array of $N$ integers, find the largest sum of any **non-empty contiguous subarray**.',
      '', '### Input',
      'The first line contains $N$. The second line contains $N$ integers $a_1, a_2, \\ldots, a_N$.',
      '', '### Output',
      'Print the maximum subarray sum.',
      '', '### Constraints',
      '- $1 \\le N \\le 200000$',
      '- $-10^9 \\le a_i \\le 10^9$',
      '', '### Example',
      'For `[-2, 1, -3, 4, -1, 2, 1, -5, 4]`, choose `[4, -1, 2, 1]`. Its sum is **6**.',
    ].join('\n'),
    sample_input_output: examples,
  } });
  expect(created.ok()).toBeTruthy();
  const problem = (await created.json()).problem;
  const otherProblems = [
    ['A + B', 'Easy', ['Math', 'Implementation'], 'Read two integers and print their sum.'],
    ['Balanced Brackets', 'Easy', ['Stack', 'Strings'], 'Determine whether every opening bracket has a matching closing bracket.'],
    ['Range Sum Queries', 'Easy', ['Prefix Sums', 'Arrays'], 'Answer range-sum queries over an immutable array.'],
    ['Shortest Path in a Grid', 'Medium', ['BFS', 'Graphs'], 'Find the fewest moves from the start cell to the destination.'],
    ['Longest Increasing Subsequence', 'Medium', ['Dynamic Programming', 'Binary Search'], 'Find the length of the longest strictly increasing subsequence.'],
    ['Minimum Spanning Tree', 'Hard', ['Graphs', 'Disjoint Set'], 'Connect all vertices with minimum total edge weight.'],
    ['Edit Distance', 'Hard', ['Dynamic Programming', 'Strings'], 'Find the minimum edits needed to transform one string into another.'],
  ];
  for (const [title, difficulty, tags, statement] of otherProblems) {
    expect((await request.post('/api/problems', { data: {
      title, difficulty, tags, problem_statements: statement, language: 'en', sample_input_output: [],
    } })).ok()).toBeTruthy();
  }

  const studyArchive = zip({
    'workspace.json': JSON.stringify({
      title: 'Actuarial Learning Lab',
      workspace: [
        { name: 'Probability Foundations (Chapter 1)', path: './chapter_output/ch_1/output' },
        { name: 'Life Contingencies (Chapter 2)', path: './chapter_output/ch_2/output' },
      ],
    }),
    'chapter_output/ch_1/output/quizzes/probability.json': JSON.stringify({
      title: 'Probability Foundations Quiz',
      description: 'Review expectation, variance, and conditional probability.',
      questions: [{
        question: 'If $$E[X]=4$$ and $$E[X^2]=20$$, what is $$Var(X)$$?',
        options: ['2', '4', '8', '16'], correct: 1,
        explanation: '$$Var(X)=E[X^2]-E[X]^2=20-16=4$$.',
        difficulty: 'understanding', sources: ['Chapter 1'],
      }],
    }),
    'chapter_output/ch_1/output/qandas/probability.json': JSON.stringify({
      title: 'Probability Q&A',
      questions: [{ id: 'conditional', question: 'Explain conditional probability in your own words.' }],
    }),
    'chapter_output/ch_1/output/flashcards/probability.json': JSON.stringify({
      title: 'Probability Essentials', description: 'Core formulas and interpretations.',
      cards: [{ type: 'definition', front: 'Variance identity', back: '$$Var(X)=E[X^2]-E[X]^2$$', tags: ['probability'], source_ids: ['Chapter 1'] }],
    }),
    'chapter_output/ch_2/output/quizzes/contingencies.json': JSON.stringify({
      title: 'Life Contingencies Quiz', description: 'Connect survival models and present values.',
      questions: [{
        question: 'Which function represents survival beyond age $$x+t$$?',
        options: ['$$q_x$$', '$$_tp_x$$', '$$\\mu_x$$', '$$v^t$$'], correct: 1,
        explanation: '$$_tp_x$$ is the probability of surviving at least $$t$$ more years.',
        difficulty: 'recall', sources: ['Chapter 2'],
      }],
    }),
  });
  const uploaded = await request.post('/api/workspace/upload', {
    headers: { 'Content-Type': 'application/zip', 'X-File-Name': 'actuarial_learning_lab.zip' },
    data: studyArchive,
  });
  expect(uploaded.ok()).toBeTruthy();
  const wrong = await request.post('/api/submit', { data: {
    problemId: problem.id, language: 'python', code: solution.replace('current = best = values[0]', 'current = best = 0'), async: false,
  } });
  expect(wrong.ok()).toBeTruthy();

  // Use an explicit demonstration reply, independent of external LLM services.
  await page.route('**/api/chat', route => route.fulfill({ json: {
    success: true, model: 'mock-assistant', reply: explanation,
  } }));
  await page.goto('/#problems');
  await page.getByRole('row').filter({ hasText: 'Maximum Subarray Sum' }).click();
  await expect(page.locator('.cm-content')).toHaveAttribute('contenteditable', 'true');
  await page.locator('.cm-content').fill(solution);
  await page.locator('.cm-content').press('ControlOrMeta+Home');
  await expect(page.getByText('Saved to disk', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Submit', exact: true }).click();
  await expect(page.getByText('3 / 3 test cases passed')).toBeVisible();
  await page.getByText('Case 1: Accepted', { exact: false }).click();
  // Let the actual success animation finish before photographing the workspace.
  await expect(page.locator('canvas')).toHaveCount(0, { timeout: 10_000 });
  await capture(page, 'solving-workspace.png');

  await page.getByRole('button', { name: 'AI Tutor', exact: true }).click();
  const chat = page.getByRole('dialog', { name: 'AI Assistant' });
  await chat.getByRole('textbox').fill('Explain the recurrence and an edge case.');
  await chat.getByRole('button', { name: 'Send message', exact: true }).click();
  const response = chat.locator('.rich-content').last();
  await expect(response.locator('.katex-display')).toBeVisible();
  await response.getByRole('heading').first().scrollIntoViewIfNeeded();
  await capture(page, 'ai-assistant.png');
  await chat.getByRole('button', { name: 'Close Chat' }).click();

  await page.getByRole('button', { name: 'Submissions', exact: true }).click();
  await expect(page.getByText(/Past Submissions \(\d+\)/)).toBeVisible();
  await capture(page, 'submission-history.png');

  await page.getByRole('button', { name: 'Close Activity Screen' }).click();
  await expect(page.getByRole('row')).toHaveCount(9);
  await expect(page.getByRole('row').filter({ hasText: 'Maximum Subarray Sum' }).locator('td').first()).toHaveCSS('color', 'rgb(44, 187, 93)');
  await capture(page, 'problem-archive.png');

  await page.goto('/#studyset');
  await expect(page.getByRole('heading', { name: 'Choose a study set' })).toBeVisible();
  await page.locator('.saved-library-toggle').filter({ hasText: 'actuarial_learning_lab.zip' }).click();
  const chapterOne = page.locator('.study-set-open').filter({ hasText: 'Probability Foundations (Chapter 1)' });
  await expect(chapterOne).toBeVisible();
  await expect(page.locator('.study-set-open').filter({ hasText: 'Life Contingencies (Chapter 2)' })).toBeVisible();
  await capture(page, 'study-set-library.png');

  await chapterOne.click();
  await expect(page.getByRole('option', { name: 'Probability Foundations Quiz', exact: true })).toBeVisible();
  await capture(page, 'study-set-quiz.png');
});
