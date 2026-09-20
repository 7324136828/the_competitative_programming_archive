import { expect, test, type Page } from '@playwright/test';

const defaultModel = 'my-config';
const alternateModel = 'alternate-model';
const availableModels = [
  { id: defaultModel, name: defaultModel },
  { id: alternateModel, name: 'Alternative model' },
];

async function discoverModels(page: Page) {
  await page.route('**/api/llm/models', route => route.fulfill({ json: {
    success: true, model: defaultModel, models: availableModels,
  } }));
}

async function openProblem(page: Page) {
  await page.goto('/');
  await page.getByRole('row').filter({ hasText: 'Model selection example' }).click();
  await expect(page.getByRole('combobox', { name: 'AI model' }).first()).toBeEnabled();
}

test.beforeEach(async ({ request }) => {
  expect((await request.delete('/api/database')).ok()).toBeTruthy();
  const created = await request.post('/api/problems', { data: {
    title: 'Model selection example', problem_statements: 'Read two integers and print their sum.',
    sample_input_output: [{ input: '2 3', output: '5' }], difficulty: 'Easy',
  } });
  expect(created.ok()).toBeTruthy();
});

test('shares the selected discovered model across hints, test cases, and problem generation', async ({ page }) => {
  await discoverModels(page);
  await page.route('**/api/llm/hint', route => route.fulfill({ json: {
    success: true, model: route.request().postDataJSON().model, hintLevel: 1,
    totalSteps: 5, stepTitle: 'Understand the input', category: 'Analysis', hintText: 'Read the two values.',
  } }));
  await page.route('**/api/llm/generate-testcases', route => route.fulfill({ json: {
    success: true, model: route.request().postDataJSON().model, testCases: [{ input: '0 0', output: '0' }],
  } }));
  await page.route('**/api/llm/generate-problem', route => route.fulfill({ json: {
    success: true, model: route.request().postDataJSON().model, savedProblem: null,
    generatedProblem: { title: 'Generated sum', problem_statements: 'Print the sum.', difficulty: 'Easy', language: 'AI', source: 'Unknown' },
  } }));
  await openProblem(page);
  const selectors = page.getByRole('combobox', { name: 'AI model' });
  await expect(selectors.first()).toHaveValue(defaultModel);
  await selectors.first().selectOption(alternateModel);
  for (const selector of await selectors.all()) await expect(selector).toHaveValue(alternateModel);

  const hintRequest = page.waitForRequest('**/api/llm/hint');
  await page.getByRole('button', { name: 'Unlock Step 1', exact: true }).click();
  expect((await hintRequest).postDataJSON().model).toBe(alternateModel);
  await expect(page.getByText('Read the two values.')).toBeVisible();

  const casesRequest = page.waitForRequest('**/api/llm/generate-testcases');
  await page.getByRole('button', { name: /Generate.*Case/ }).click();
  expect((await casesRequest).postDataJSON().model).toBe(alternateModel);

  await page.getByRole('button', { name: 'Generate AI Problem', exact: true }).click();
  const modal = page.locator('.modal-content');
  await expect(modal.getByRole('combobox', { name: 'AI model' })).toHaveValue(alternateModel);
  const generationRequest = page.waitForRequest('**/api/llm/generate-problem');
  await modal.getByRole('button', { name: 'Generate AI Problem', exact: true }).click();
  expect((await generationRequest).postDataJSON().model).toBe(alternateModel);
  await expect(modal.getByText(`Result model: ${alternateModel}`)).toBeVisible();
});

test('preserves model preference on refresh and reload, falling back when it disappears', async ({ page }) => {
  let models = availableModels;
  await page.route('**/api/llm/models', route => route.fulfill({ json: {
    success: true, model: defaultModel, models,
  } }));
  await page.goto('/');
  const selector = page.getByRole('combobox', { name: 'AI model' }).first();
  await expect(selector).toBeEnabled();
  await selector.selectOption(alternateModel);
  await page.getByRole('button', { name: 'Refresh models' }).first().click();
  await expect(selector).toBeEnabled();
  await expect(selector).toHaveValue(alternateModel);
  await page.reload();
  await expect(selector).toBeEnabled();
  await expect(selector).toHaveValue(alternateModel);

  models = [availableModels[0]];
  await page.getByRole('button', { name: 'Refresh models' }).first().click();
  await expect(selector).toBeEnabled();
  await expect(selector).toHaveValue(defaultModel);
  await page.reload();
  await expect(selector).toBeEnabled();
  await expect(selector).toHaveValue(defaultModel);
});

test('disables AI actions after discovery fails and recovers on retry', async ({ page }) => {
  let unavailable = true;
  await page.route('**/api/llm/models', route => unavailable
    ? route.fulfill({ status: 503, json: { success: false, error: 'Model catalog temporarily unavailable' } })
    : route.fulfill({ json: { success: true, model: defaultModel, models: availableModels } }));
  await page.goto('/');
  await page.getByRole('row').filter({ hasText: 'Model selection example' }).click();
  await expect(page.getByRole('combobox', { name: 'AI model' }).first()).toBeDisabled();
  await expect(page.getByRole('button', { name: 'Unlock Step 1', exact: true })).toBeDisabled();
  await expect(page.getByRole('alert').filter({ hasText: 'Model catalog temporarily unavailable' }).first()).toBeVisible();
  unavailable = false;
  await page.getByRole('button', { name: 'Retry models' }).first().click();
  await expect(page.getByRole('combobox', { name: 'AI model' }).first()).toBeEnabled();
  await expect(page.getByRole('button', { name: 'Unlock Step 1', exact: true })).toBeEnabled();
});

test('resets progressive hints and ignores a previous model response after switching', async ({ page }) => {
  await discoverModels(page);
  let releasePrevious!: () => void;
  const previousResponse = new Promise<void>(resolve => { releasePrevious = resolve; });
  await page.route('**/api/llm/hint', async route => {
    const { model, hintLevel } = route.request().postDataJSON();
    if (model === defaultModel && hintLevel === 2) await previousResponse;
    await route.fulfill({ json: {
      success: true, model, hintLevel, totalSteps: 5, category: 'Analysis',
      stepTitle: `Step ${hintLevel}`, hintText: `${model} hint ${hintLevel}`,
    } });
  });
  await openProblem(page);
  await page.getByRole('button', { name: 'Unlock Step 1', exact: true }).click();
  await expect(page.getByText(`${defaultModel} hint 1`, { exact: true })).toBeVisible();
  const pendingRequest = page.waitForRequest('**/api/llm/hint');
  await page.getByRole('button', { name: 'Unlock Step 2', exact: true }).click();
  await pendingRequest;
  try {
    await page.getByRole('combobox', { name: 'AI model' }).first().selectOption(alternateModel);
    await expect(page.getByText(`${defaultModel} hint 1`, { exact: true })).toHaveCount(0);
    const nextRequest = page.waitForRequest('**/api/llm/hint');
    await page.getByRole('button', { name: 'Unlock Step 1', exact: true }).click();
    expect((await nextRequest).postDataJSON()).toMatchObject({ model: alternateModel, hintLevel: 1 });
    await expect(page.getByText(`${alternateModel} hint 1`, { exact: true })).toBeVisible();
    const previousFinished = page.waitForResponse(response => response.url().endsWith('/api/llm/hint')
      && response.request().postDataJSON().model === defaultModel);
    releasePrevious();
    await (await previousFinished).finished();
    await expect(page.getByText(`${defaultModel} hint 2`, { exact: true })).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Unlock Step 2', exact: true })).toBeEnabled();
  } finally {
    releasePrevious();
  }
});

test('keeps completed result metadata tied to the model used for an in-flight request', async ({ page }) => {
  await discoverModels(page);
  let release!: () => void;
  const pendingResponse = new Promise<void>(resolve => { release = resolve; });
  await page.route('**/api/llm/generate-testcases', async route => {
    const { model } = route.request().postDataJSON();
    await pendingResponse;
    await route.fulfill({ json: { success: true, model, testCases: [{ input: '0 0', output: '0' }] } });
  });
  await openProblem(page);
  const started = page.waitForRequest('**/api/llm/generate-testcases');
  await page.getByRole('button', { name: /Generate.*Case/ }).click();
  expect((await started).postDataJSON().model).toBe(defaultModel);
  try {
    await page.getByRole('combobox', { name: 'AI model' }).first().selectOption(alternateModel);
    release();
    await expect(page.getByText(`Result model: ${defaultModel}`, { exact: true })).toBeVisible();
    await expect(page.getByRole('combobox', { name: 'AI model' }).first()).toHaveValue(alternateModel);
  } finally {
    release();
  }
});
