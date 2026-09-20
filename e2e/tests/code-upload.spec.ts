/// <reference lib="dom" />
import { expect, test, type Page } from '@playwright/test';

test.use({ viewport: { width: 1400, height: 950 } });

async function openProblem(page: Page) {
  await page.getByRole('row').filter({ hasText: 'Upload A + B' }).click();
  await expect(page.locator('.cm-content')).toHaveAttribute('contenteditable', 'true');
}

async function dropFiles(page: Page, files: { name: string; code: string }[]) {
  const transfer = await page.evaluateHandle(files => {
    const data = new DataTransfer();
    for (const file of files) data.items.add(new File([file.code], file.name, { type: 'text/plain' }));
    return data;
  }, files);
  await page.locator('.cm-content').dispatchEvent('dragenter', { dataTransfer: transfer });
  await expect(page.locator('.source-drop-overlay')).toBeVisible();
  await page.locator('.cm-content').dispatchEvent('drop', { dataTransfer: transfer });
  await expect(page.locator('.source-drop-overlay')).toBeHidden();
  await transfer.dispose();
}

test.beforeEach(async ({ page, request }) => {
  expect((await request.delete('/api/database')).ok()).toBeTruthy();
  expect((await request.post('/api/problems', { data: {
    title: 'Upload A + B', problem_statements: 'Read two integers and print their sum.',
    sample_input_output: [{ input: '2 3', output: '5' }], difficulty: 'Easy',
  } })).ok()).toBeTruthy();
  await page.route('**/api/languages', route => route.fulfill({ json: { success: true, languages: [
    { id: 'python', label: 'Python 3', editorLanguage: 'python' },
    { id: 'cpp', label: 'C++', editorLanguage: 'cpp' },
  ] } }));
  await page.goto('/');
  await openProblem(page);
});

test('choosing a source file loads and saves the editor, and submits the same source', async ({ page, request }, testInfo) => {
  const code = '# Uploaded source\nprint(sum(map(int, input().split())))';
  const picker = page.waitForEvent('filechooser');
  await page.getByRole('button', { name: 'Upload code', exact: true }).click();
  await (await picker).setFiles({ name: 'solution.py', mimeType: 'text/plain', buffer: Buffer.from(code) });
  await expect(page.locator('.cm-line')).toHaveText(code.split('\n'));
  await expect(page.getByRole('status').filter({ hasText: 'Loaded solution.py' })).toBeVisible();
  expect((await (await request.get('/api/submissions')).json()).total).toBe(0);
  await expect(page.getByText('Saved to disk', { exact: true })).toBeVisible();
  await page.reload();
  await openProblem(page);
  await expect(page.locator('.cm-line')).toHaveText(code.split('\n'));
  await page.getByRole('button', { name: 'Submit', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Test cases panel', exact: true }).getByText('Accepted', { exact: true }).first()).toBeVisible({ timeout: 20000 });
  const records = (await (await request.get('/api/submissions')).json()).submissions;
  expect(records).toHaveLength(1);
  expect(records[0].code).toBe(code);
  await page.screenshot({ path: testInfo.outputPath('uploaded-source-desktop.png') });
});

test('dropping a C++ file changes language and replaces code once; empty text files remain empty', async ({ page }) => {
  const code = '// Uploaded C++\n#include <iostream>\nint main() { std::cout << 5; }';
  await dropFiles(page, [{ name: 'answer.cc', code }]);
  await expect(page.getByRole('combobox', { name: 'Programming language' })).toHaveValue('cpp');
  await expect(page.locator('.cm-line')).toHaveText(code.split('\n'));
  await expect(page.getByText('Saved to disk', { exact: true })).toBeVisible();
  await dropFiles(page, [{ name: 'empty.txt', code: '' }]);
  await expect(page.getByRole('combobox', { name: 'Programming language' })).toHaveValue('cpp');
  await expect(page.locator('.cm-content')).toHaveText('');
  await expect(page.getByText('Saved to disk', { exact: true })).toBeVisible();
  await page.reload();
  await openProblem(page);
  await page.getByRole('combobox', { name: 'Programming language' }).selectOption('cpp');
  await expect(page.locator('.cm-content')).toHaveAttribute('contenteditable', 'true');
  await expect(page.locator('.cm-content')).toHaveText('');
});

test('invalid and unavailable files leave the current source unchanged', async ({ page }) => {
  const source = '# Keep this code';
  await page.locator('.cm-content').fill(source);
  const input = page.getByLabel('Choose source code file');
  for (const file of [
    { name: 'Main.java', buffer: Buffer.from('class Main {}'), error: 'Java JDK' },
    { name: 'program.exe', buffer: Buffer.from('executable'), error: 'source file' },
    { name: 'binary.py', buffer: Buffer.from([65, 0, 66]), error: 'binary file' },
    { name: 'encoding.py', buffer: Buffer.from([255, 254]), error: 'UTF-8' },
    { name: 'huge.py', buffer: Buffer.alloc(2 * 1024 * 1024 + 1, 'x'), error: '2 MiB' },
  ]) {
    await input.setInputFiles({ name: file.name, mimeType: 'text/plain', buffer: file.buffer });
    await expect(page.getByRole('alert')).toContainText(file.error);
    await expect(page.locator('.cm-content')).toHaveText(source);
  }
  await dropFiles(page, [{ name: 'one.py', code: 'first' }, { name: 'two.py', code: 'second' }]);
  await expect(page.getByRole('alert')).toContainText('one source file at a time');
  await expect(page.locator('.cm-content')).toHaveText(source);
  await expect(page.getByRole('combobox', { name: 'Programming language' })).toHaveValue('python');
});

test('typing during a slow file read cancels import without losing newer edits', async ({ page }) => {
  await page.evaluate(() => {
    const read = File.prototype.arrayBuffer;
    File.prototype.arrayBuffer = function () {
      return new Promise<ArrayBuffer>(resolve => {
        (window as Window & { releaseSourceRead?: () => void }).releaseSourceRead = () => { void read.call(this).then(resolve); };
      });
    };
  });
  await page.getByLabel('Choose source code file').setInputFiles({ name: 'slow.py', mimeType: 'text/plain', buffer: Buffer.from('print("old file")') });
  await expect(page.getByRole('button', { name: 'Importing...', exact: true })).toBeVisible();
  await page.locator('.cm-content').fill('# Newer editor changes');
  await page.evaluate(() => (window as Window & { releaseSourceRead?: () => void }).releaseSourceRead?.());
  await expect(page.getByRole('alert')).toContainText('Import canceled');
  await expect(page.locator('.cm-content')).toHaveText('# Newer editor changes');
});

test('switching languages away and back while a destination draft loads cancels import', async ({ page, request }) => {
  const problems = (await (await request.get('/api/problems')).json()).problems;
  const problemId = problems[0].id;
  expect((await request.put(`/api/problems/${problemId}/drafts/cpp`, { data: { code: '// Existing saved C++', revision: 0 } })).ok()).toBeTruthy();
  let release!: () => void;
  const pending = new Promise<void>(resolve => { release = resolve; });
  await page.route('**/api/problems/*/drafts/cpp', async route => {
    if (route.request().method() === 'GET') await pending;
    await route.continue();
  });
  const loading = page.waitForRequest(request => request.url().endsWith('/drafts/cpp'));
  await page.getByLabel('Choose source code file').setInputFiles({ name: 'incoming.cpp', mimeType: 'text/plain', buffer: Buffer.from('// Incoming file') });
  await loading;
  await page.getByRole('combobox', { name: 'Programming language' }).selectOption('cpp');
  await page.getByRole('combobox', { name: 'Programming language' }).selectOption('python');
  release();
  await expect(page.getByRole('alert')).toContainText('Import canceled');
  await expect(page.getByRole('combobox', { name: 'Programming language' })).toHaveValue('python');
  await page.getByRole('combobox', { name: 'Programming language' }).selectOption('cpp');
  await expect(page.locator('.cm-content')).toHaveText('// Existing saved C++');
  const saved = (await (await request.get(`/api/problems/${problemId}/drafts/cpp`)).json()).draft;
  expect(saved.code).toBe('// Existing saved C++');
});

test('upload controls fit a narrow expanded editor and remain usable', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole('button', { name: 'Expand code editor', exact: true }).click();
  const upload = page.getByRole('button', { name: 'Upload code', exact: true });
  await expect(upload).toBeVisible();
  await page.getByLabel('Choose source code file').setInputFiles({ name: 'mobile.py', mimeType: 'text/plain', buffer: Buffer.from('print(5)') });
  await expect(page.locator('.cm-content')).toHaveText('print(5)');
  for (const label of ['Upload code', 'Run Code', 'Submit']) {
    const box = await page.getByRole('button', { name: label, exact: true }).boundingBox();
    expect(box).not.toBeNull();
    expect(box!.x).toBeGreaterThanOrEqual(0);
    expect(box!.x + box!.width).toBeLessThanOrEqual(390);
  }
  await page.screenshot({ path: testInfo.outputPath('source-upload-mobile.png') });
});
