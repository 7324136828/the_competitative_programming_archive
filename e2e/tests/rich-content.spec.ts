/// <reference lib="dom" />
import { expect, test, type Page } from '@playwright/test';

const explanation = [
  '**### The Core Problem Rule (Checksum Property)**',
  'For any **original** word of length $N$, the input satisfies $4 \\le N \\le 1000$.',
  '',
  '1. A multiple of $(N + 1)$.',
  '2. Exactly $0$.',
  '',
  '**#### Processing Word 1: `"1011"` (Length = 4)**',
  '',
  '\\[ \\sum_{i=1}^{N} i x_i \\equiv 0 \\pmod{N+1} \\]',
  '',
  'The flip is \\(0 \\to 1\\).',
  '',
  '```json',
  '{"input":"4\\n1011\\n011","output":["1111"],"note":"$N$ remains a string"}',
  '```',
  '',
  '```cpp',
  'cout << "$N$"; // \\(raw\\)',
  '```',
  '',
  '<script>window.richResponseUnsafe = true</script>',
  '',
  '[Unsafe link](javascript:alert%281%29)',
  '',
  '![Untrusted image](https://example.invalid/tracking.png)',
].join('\n');

test.beforeEach(async ({ page, request }) => {
  expect((await request.delete('/api/database')).ok()).toBeTruthy();
  expect((await request.post('/api/problems', { data: {
    title: 'Rich response example', problem_statements: 'Read two integers and print their sum.',
    sample_input_output: [{ input: '2 3', output: '5' }], difficulty: 'Easy',
  } })).ok()).toBeTruthy();
  await page.route('**/api/llm/models', route => route.fulfill({ json: {
    success: true, model: 'my-config', models: [{ id: 'my-config', name: 'my-config' }],
  } }));
});

async function openChat(page: Page) {
  await page.goto('/');
  await page.getByRole('button', { name: 'AI Chat', exact: true }).click();
  const chat = page.getByRole('dialog', { name: 'AI Assistant', exact: true });
  await expect(chat.getByRole('combobox', { name: 'AI model' })).toBeEnabled();
  return chat;
}

test('renders AI explanations with math and JSON safely on desktop and mobile', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 1400, height: 1100 });
  await page.route('**/api/chat', route => route.fulfill({ json: {
    success: true, model: 'my-config', reply: explanation,
  } }));
  const chat = await openChat(page);
  await chat.getByRole('textbox').fill('Explain the input and output.');
  await chat.getByRole('button', { name: 'Send message', exact: true }).click();
  const response = chat.locator('.rich-content').last();
  await expect(response.getByRole('heading', { name: 'The Core Problem Rule (Checksum Property)' })).toBeVisible();
  await expect(response.getByRole('heading', { name: 'Processing Word 1: "1011" (Length = 4)' })).toBeVisible();
  await expect(response.locator('ol > li')).toHaveCount(2);
  await expect(response.locator('.katex-display')).toHaveCount(1);
  await expect(response.locator('.katex-error')).toHaveCount(0);
  expect(await response.locator('.katex').first().evaluate(el => getComputedStyle(el).fontFamily)).toContain('KaTeX');
  await expect(response.locator('pre code.language-json')).toHaveText(JSON.stringify({
    input: '4\n1011\n011', output: ['1111'], note: '$N$ remains a string',
  }, null, 2) + '\n');
  await expect(response.locator('pre code.language-cpp')).toHaveText('cout << "$N$"; // \\(raw\\)\n');
  await expect(response.locator('script, img')).toHaveCount(0);
  await expect(response.getByRole('link', { name: 'Unsafe link' })).toHaveAttribute('href', '');
  expect(await page.evaluate(() => 'richResponseUnsafe' in window)).toBe(false);

  await response.getByRole('heading').first().scrollIntoViewIfNeeded();
  await page.screenshot({ path: testInfo.outputPath('ai-formatted-response-desktop.png') });

  await page.setViewportSize({ width: 390, height: 844 });
  const dimensions = await chat.evaluate(el => ({ width: el.clientWidth, scrollWidth: el.scrollWidth }));
  expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.width + 1);
  await response.getByRole('heading').first().scrollIntoViewIfNeeded();
  await expect(response.getByRole('heading').first()).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath('ai-formatted-response-mobile.png') });
});

test('renders a structured JSON reply and math in progressive hints', async ({ page }) => {
  await page.route('**/api/chat', route => route.fulfill({ json: {
    success: true, model: 'my-config', reply: { testCases: [{ input: '2 3', output: '5' }] },
  } }));
  await page.route('**/api/llm/hint', route => route.fulfill({ json: {
    success: true, model: 'my-config', hintLevel: 1, totalSteps: 5,
    stepTitle: 'Checksum', category: 'Analysis', hintText: 'Use **positions** and calculate $s \\bmod (N+1)$.',
  } }));
  const chat = await openChat(page);
  await chat.getByRole('textbox').fill('Give me JSON test cases.');
  await chat.getByRole('button', { name: 'Send message', exact: true }).click();
  const code = chat.locator('.rich-content pre code').last();
  await expect(code).toHaveClass('language-json');
  await expect(code).toContainText('"testCases": [');
  await chat.getByRole('button', { name: 'Close Chat' }).click();
  await page.getByRole('row').filter({ hasText: 'Rich response example' }).click();
  await page.getByRole('button', { name: 'Unlock Step 1', exact: true }).click();
  const hint = page.locator('.rich-content').filter({ hasText: 'Use positions and calculate' });
  await expect(hint.locator('strong')).toHaveText('positions');
  await expect(hint.locator('.katex')).toHaveCount(1);
});
