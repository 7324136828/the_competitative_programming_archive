import { expect, test } from '@playwright/test';

test.beforeEach(async ({ request }) => {
  expect((await request.delete('/api/database')).ok()).toBeTruthy();
  const created = await request.post('/api/problems', { data: {
    title: 'A + B', problem_statements: 'Read two integers and print their sum.',
    sample_input_output: [{ input: '2 3', output: '5' }], difficulty: 'Easy',
  } });
  expect(created.ok()).toBeTruthy();
});

test('shows discovered model and uses it for hints and test cases', async ({ page }) => {
  await page.goto('/');
  await page.getByRole('row').filter({ hasText: 'A + B' }).click();
  await expect(page.getByRole('combobox', { name: 'AI model', exact: true }).first()).toHaveValue('mock-assistant');
  const hintResponse = page.waitForResponse(response => response.url().endsWith('/api/llm/hint'));
  await page.getByRole('button', { name: 'Unlock Step 1' }).click();
  const hints = await (await hintResponse).json();
  expect(hints.success).toBe(true);
  expect(hints.model).toBe('mock-assistant');
  expect(hints.totalSteps).toBeGreaterThanOrEqual(5);
  const casesResponse = page.waitForResponse(response => response.url().endsWith('/api/llm/generate-testcases'));
  await page.getByRole('button', { name: /Generate.*Case/ }).click();
  const cases = await (await casesResponse).json();
  expect(cases.success).toBe(true);
  expect(cases.model).toBe('mock-assistant');
  expect(cases.testCases.length).toBeGreaterThan(0);
});

for (const language of ['python', 'cpp']) {
test(`${language}: waits for judging and keeps solved number green after reload`, async ({ page }) => {
  const languages = await (await page.request.get('/api/languages')).json();
  test.skip(!languages.languages.some((entry: { id: string }) => entry.id === language), `${language} runtime unavailable`);
  await page.goto('/');
  await page.getByRole('row').filter({ hasText: 'A + B' }).click();
  await page.getByRole('combobox', { name: 'Programming language' }).selectOption(language);
  await page.locator('.cm-content').fill(language === 'cpp'
    ? '#include <iostream>\nint main(){long long a,b;if(std::cin>>a>>b)std::cout<<a+b<<"\\n";}'
    : 'a,b=map(int,input().split());print(a+b)');
  const submitted = page.waitForResponse(response => response.url().endsWith('/api/submit'));
  await page.getByRole('button', { name: 'Submit', exact: true }).click();
  const queued = await submitted;
  expect(queued.status()).toBe(202);
  const job = await queued.json();
  await expect.poll(async () => {
    const result = await page.request.get(`/api/submission-jobs/${job.jobId}`);
    return (await result.json()).done;
  }).toBe(true);
  await expect(page.getByText('Accepted', { exact: true }).first()).toBeVisible();
  await page.reload();
  const row = page.getByRole('row').filter({ hasText: 'A + B' });
  await expect(row.locator('td').first()).toHaveCSS('color', 'rgb(44, 187, 93)');
  await row.getByRole('button', { name: /Revisit solved problem/ }).click();
  await expect(page.getByRole('button', { name: 'Submit', exact: true })).toBeEnabled();
});
}

for (const autoSave of [true, false]) {
test(`generated problem is saved once before Solve opens it (autoSave=${autoSave})`, async ({ page }) => {
  if (!autoSave) {
    await page.route('**/api/llm/generate-problem', async route => {
      await route.continue({ postData: JSON.stringify({ ...route.request().postDataJSON(), autoSave: false }) });
    });
  }
  await page.goto('/');
  await page.getByRole('button', { name: /Generate/ }).first().click();
  const generatedResponse = page.waitForResponse(response => response.url().endsWith('/api/llm/generate-problem'));
  await page.locator('.modal-content').getByRole('button', { name: 'Generate AI Problem', exact: true }).click();
  const generated = await (await generatedResponse).json();
  expect(generated.success).toBe(true);
  if (autoSave) expect(generated.savedProblem.id).toBeTruthy();
  else expect(generated.savedProblem).toBeNull();
  await page.getByRole('button', { name: 'Solve This Problem', exact: true }).click();
  await expect(page.getByText(generated.generatedProblem.title, { exact: true }).first()).toBeVisible();
  const listing = await (await page.request.get('/api/problems')).json();
  expect(listing.total).toBe(2);
  const persisted = listing.problems.find((problem: { title: string }) => problem.title === generated.generatedProblem.title);
  expect(persisted).toBeTruthy();
  const saved = await page.request.get(`/api/problems/${persisted.id}`);
  expect((await saved.json()).problem.title).toBe(generated.generatedProblem.title);
});
}
