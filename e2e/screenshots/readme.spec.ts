/// <reference lib="dom" />
import { expect, test, type Page } from '@playwright/test';
import { mkdir } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const screenshots = resolve(dirname(fileURLToPath(import.meta.url)), '../../docs/screenshots');
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
  await mkdir(screenshots, { recursive: true });
  expect((await request.delete('/api/database')).ok()).toBeTruthy();
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
  const wrong = await request.post('/api/submit', { data: {
    problemId: problem.id, language: 'python', code: solution.replace('current = best = values[0]', 'current = best = 0'), async: false,
  } });
  expect(wrong.ok()).toBeTruthy();

  // Use an explicit demonstration reply, independent of external LLM services.
  await page.route('**/api/chat', route => route.fulfill({ json: {
    success: true, model: 'mock-assistant', reply: explanation,
  } }));
  await page.goto('/');
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

  await page.getByRole('button', { name: 'AI Chat', exact: true }).click();
  const chat = page.getByRole('dialog', { name: 'AI Assistant' });
  await chat.getByRole('textbox').fill('Explain the recurrence and an edge case.');
  await chat.getByRole('button', { name: 'Send message', exact: true }).click();
  const response = chat.locator('.rich-content').last();
  await expect(response.locator('.katex-display')).toBeVisible();
  await response.getByRole('heading').first().scrollIntoViewIfNeeded();
  await capture(page, 'ai-assistant.png');
  await chat.getByRole('button', { name: 'Close Chat' }).click();

  await page.getByRole('banner').getByRole('button', { name: 'Submissions', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Submission history' })).toBeVisible();
  const history = (await (await request.get('/api/submissions')).json()).submissions;
  await page.getByRole('button', { name: `View submission ${history[0].id}`, exact: true }).click();
  await expect(page.getByLabel('Submitted code', { exact: true })).toHaveText(solution);
  await capture(page, 'submission-history.png');

  await page.getByRole('button', { name: 'Problem Set', exact: true }).click();
  await expect(page.getByRole('row')).toHaveCount(9);
  await expect(page.getByRole('row').filter({ hasText: 'Maximum Subarray Sum' }).locator('td').first()).toHaveCSS('color', 'rgb(44, 187, 93)');
  await capture(page, 'problem-archive.png');
});
