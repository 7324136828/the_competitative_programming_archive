import { expect, test, type Page } from '@playwright/test';
import { readFile } from 'node:fs/promises';

test.use({ viewport: { width: 1400, height: 950 } });

async function openProblem(page: Page, title = 'Draft problem A') {
  await page.getByRole('button', { name: 'Problem Set', exact: true }).click();
  await page.getByRole('row').filter({ hasText: title }).click();
  await expect(page.locator('.cm-content')).toHaveAttribute('contenteditable', 'true');
}

test.beforeEach(async ({ page, request }) => {
  expect((await request.delete('/api/database')).ok()).toBeTruthy();
  for (const title of ['Draft problem A', 'Draft problem B']) {
    expect((await request.post('/api/problems', { data: { title, problem_statements: 'Read two integers and print their sum.', sample_input_output: [{ input: '2 3', output: '5' }], difficulty: 'Easy' } })).ok()).toBeTruthy();
  }
  await page.route('**/api/languages', route => route.fulfill({ json: { success: true, languages: [
    { id: 'python', label: 'Python 3', editorLanguage: 'python' },
    { id: 'cpp', label: 'C++', editorLanguage: 'cpp' },
  ] } }));
  await page.goto('/');
});

test('editor drafts survive reload, remain separate by problem/language, and preserve empty files', async ({ page, request }, testInfo) => {
  await openProblem(page);
  const pythonDraft = '# persisted Python\nprint(5)';
  await page.locator('.cm-content').fill(pythonDraft);
  // Switching immediately flushes the pending debounce for this language.
  await page.getByRole('combobox', { name: 'Programming language' }).selectOption('cpp');
  await expect(page.locator('.cm-content')).toHaveAttribute('contenteditable', 'true');
  await expect(page.locator('.cm-content')).toContainText('#include');
  await page.locator('.cm-content').fill('// persisted C++');
  await openProblem(page, 'Draft problem B');
  await expect(page.locator('.cm-content')).not.toContainText('persisted');
  await page.getByRole('combobox', { name: 'Programming language' }).selectOption('python');
  await expect(page.locator('.cm-content')).toHaveAttribute('contenteditable', 'true');
  await page.locator('.cm-content').fill('');
  await expect(page.getByText('Saved to disk', { exact: true })).toBeVisible();
  await page.reload();
  await openProblem(page);
  await expect(page.locator('.cm-line')).toHaveText(pythonDraft.split('\n'));
  await page.screenshot({ path: testInfo.outputPath('saved-editor-draft.png') });
  await page.getByRole('combobox', { name: 'Programming language' }).selectOption('cpp');
  await expect(page.locator('.cm-content')).toHaveText('// persisted C++');
  await openProblem(page, 'Draft problem B');
  await page.getByRole('combobox', { name: 'Programming language' }).selectOption('python');
  await expect(page.locator('.cm-content')).toHaveAttribute('contenteditable', 'true');
  await expect(page.locator('.cm-content')).toHaveText('');
  const problems = await (await request.get('/api/problems')).json();
  const firstId = problems.problems.find((problem: { title: string }) => problem.title === 'Draft problem A').id;
  const draft = await (await request.get(`/api/problems/${firstId}/drafts/python`)).json();
  expect(draft.draft.code).toBe(pythonDraft);
  expect(draft.draft.saved).toBe(true);
});

test('draft save errors retain edits and can be retried', async ({ page }) => {
  let rejectSave = true;
  await page.route('**/api/problems/*/drafts/python', async route => {
    if (route.request().method() === 'PUT' && rejectSave) {
      rejectSave = false;
      await route.fulfill({ status: 503, json: { success: false, error: 'Draft disk temporarily unavailable' } });
    } else await route.continue();
  });
  await openProblem(page);
  await page.locator('.cm-content').fill('# keep these edits');
  await expect(page.getByRole('alert')).toContainText('Draft disk temporarily unavailable');
  await page.locator('.cm-content').fill('# keep the latest edits too');
  await page.getByRole('button', { name: 'Retry draft', exact: true }).click();
  await expect(page.getByText('Saved to disk', { exact: true })).toBeVisible();
  await page.reload();
  await openProblem(page);
  await expect(page.locator('.cm-content')).toHaveText('# keep the latest edits too');
});

test('a draft load failure blocks editing until the saved source can be loaded', async ({ page, request }) => {
  const problems = await (await request.get('/api/problems')).json();
  const firstId = problems.problems.find((problem: { title: string }) => problem.title === 'Draft problem A').id;
  expect((await request.put(`/api/problems/${firstId}/drafts/python`, { data: { code: '# existing file', revision: 0 } })).ok()).toBeTruthy();
  let rejectLoad = true;
  await page.route(`**/api/problems/${firstId}/drafts/python`, async route => {
    if (route.request().method() === 'GET' && rejectLoad) {
      rejectLoad = false;
      await route.fulfill({ status: 503, json: { success: false, error: 'Cannot read the draft yet' } });
    } else await route.continue();
  });
  await page.getByRole('row').filter({ hasText: 'Draft problem A' }).click();
  await expect(page.getByRole('alert')).toContainText('Cannot read the draft yet');
  await expect(page.locator('.cm-content')).toHaveAttribute('contenteditable', 'false');
  await expect(page.getByRole('button', { name: 'Submit', exact: true })).toBeDisabled();
  await page.getByRole('button', { name: 'Retry draft', exact: true }).click();
  await expect(page.locator('.cm-content')).toHaveAttribute('contenteditable', 'true');
  await expect(page.locator('.cm-content')).toHaveText('# existing file');
});

test('global history opens code and test results and downloads all submissions as ZIP', async ({ page, request }, testInfo) => {
  const problems = await (await request.get('/api/problems')).json();
  const problemId = problems.problems[0].id;
  const code = 'print(sum(map(int, input().split())))';
  const submitted = await request.post('/api/submit', { data: { problemId, language: 'python', code, async: false } });
  expect(submitted.ok()).toBeTruthy();
  const history = await (await request.get('/api/submissions')).json();
  expect(history.total).toBe(1);
  await page.getByRole('button', { name: 'Submissions', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Submission history' })).toBeVisible();
  await page.getByRole('button', { name: `View submission ${history.submissions[0].id}`, exact: true }).click();
  await expect(page.getByLabel('Submitted code', { exact: true })).toHaveText(code);
  await page.getByText('Case 1: Accepted', { exact: false }).click();
  await expect(page.getByRole('heading', { name: 'Expected output', exact: true })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath('submission-history.png'), fullPage: true });
  const downloadPromise = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Export all submissions (ZIP)', exact: true }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe('codejudge-submissions.zip');
  const zip = await readFile((await download.path())!);
  expect(zip.subarray(0, 2).toString()).toBe('PK');
  expect(zip.length).toBeGreaterThan(100);
  await page.getByRole('button', { name: 'Open problem', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Code editor panel', exact: true })).toBeVisible();
  await expect(page.locator('.cm-content')).toHaveAttribute('contenteditable', 'true');
  await expect(page.locator('.cm-content')).not.toHaveText(code);
});

test('problem narration shows generation status, plays an MP3, and reuses cached audio', async ({ page }, testInfo) => {
  const mp3 = await readFile(new URL('../fixtures/problem-audio.mp3', import.meta.url));
  const key = 'a'.repeat(64);
  const url = `/api/audio/${key}.mp3`;
  let generations = 0;
  let checksAfterStart = 0;
  let ready = false;
  await page.route('**/api/problems/*/audio', route => {
    if (route.request().method() === 'POST') {
      generations += 1;
      return route.fulfill({ status: 202, json: { success: true, audio: { key, status: 'queued', done: false, cached: false } } });
    }
    if (generations && ++checksAfterStart >= 1) ready = true;
    return route.fulfill({ json: { success: true, audio: ready ? { key, status: 'ready', done: true, cached: true, url } : { key, status: 'missing', done: true, cached: false } } });
  });
  await page.route(`**${url}`, route => route.fulfill({ body: mp3, contentType: 'audio/mpeg' }));
  await openProblem(page);
  expect(generations).toBe(0);
  await page.getByRole('button', { name: 'Read problem aloud', exact: true }).click();
  await expect(page.getByRole('status').filter({ hasText: 'Creating your MP3' })).toBeVisible();
  await page.getByRole('button', { name: 'Close narration player' }).click();
  await page.getByRole('button', { name: /Narration queued|Generating narration|Listen to problem/ }).click();
  expect(generations).toBe(1);
  const player = page.getByLabel('Read problem description aloud');
  await expect(player).toBeVisible();
  await expect.poll(() => player.evaluate(audio => (audio as unknown as { readyState: number }).readyState)).toBeGreaterThan(0);
  await player.evaluate(audio => (audio as unknown as { play: () => Promise<void> }).play());
  await expect(page.getByRole('link', { name: 'Download MP3' })).toHaveAttribute('href', url);
  await page.screenshot({ path: testInfo.outputPath('problem-audio-player.png') });
  await page.getByRole('button', { name: 'Close narration player' }).click();
  await expect(player).toBeHidden();
  await page.reload();
  await openProblem(page);
  await page.getByRole('button', { name: 'Listen to problem', exact: true }).click();
  await expect(player).toBeVisible();
  expect(generations).toBe(1);
});

test('narration service failures are visible and can be retried', async ({ page }) => {
  let attempts = 0;
  await page.route('**/api/problems/*/audio', route => {
    if (route.request().method() === 'POST') {
      attempts += 1;
      return route.fulfill({ status: 503, json: { success: false, error: 'Kokoro voice service is unavailable. Retry after starting it.' } });
    }
    return route.fulfill({ json: { success: true, audio: { status: 'missing', done: true, cached: false, key: 'b'.repeat(64) } } });
  });
  await openProblem(page);
  await page.getByRole('button', { name: 'Read problem aloud', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Kokoro voice service is unavailable');
  await page.getByRole('button', { name: 'Read problem aloud', exact: true }).click();
  expect(attempts).toBe(2);
});
