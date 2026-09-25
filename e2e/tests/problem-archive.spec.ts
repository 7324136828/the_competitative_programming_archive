import { expect, test } from '@playwright/test';

test.use({ viewport: { width: 1100, height: 520 } });

test('problem archive scrolls to its pagination footer', async ({ page, request }) => {
  expect((await request.delete('/api/database')).ok()).toBeTruthy();
  for (let index = 1; index <= 12; index += 1) {
    const created = await request.post('/api/problems', {
      data: {
        title: `Scrollable problem ${index}`,
        problem_statements: 'A problem used to verify archive scrolling.',
        difficulty: 'Easy',
      },
    });
    expect(created.ok()).toBeTruthy();
  }

  await page.goto('/#problems');
  await expect(page.getByRole('heading', { name: 'Problem Archive' })).toBeVisible();

  const archive = page.getByTestId('problem-archive-scroll');
  await expect.poll(() => archive.evaluate(element => element.scrollHeight > element.clientHeight)).toBe(true);
  await archive.evaluate(element => { element.scrollTop = element.scrollHeight; });
  await expect.poll(() => archive.evaluate(element => element.scrollTop)).toBeGreaterThan(0);
  await expect(page.getByText(/Showing page/)).toBeVisible();
});

test('coding screen navigates back to its original story', async ({ page, request }) => {
  expect((await request.delete('/api/database')).ok()).toBeTruthy();
  const created = await request.post('/api/problems', {
    data: {
      title: 'Story navigation problem',
      problem_statements: 'Open the linked story from the coding workspace.',
      difficulty: 'Medium',
    },
  });
  expect(created.ok()).toBeTruthy();

  await page.goto('/#problems');
  await page.getByRole('row').filter({ hasText: 'Story navigation problem' }).click();
  await expect(page.getByRole('region', { name: 'Problem panel', exact: true })).toBeVisible();

  await page.getByRole('button', { name: 'Navigate to story' }).click();
  await expect(page.getByRole('button', { name: /Open Activity/ })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Story navigation problem' })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Problem panel', exact: true })).toBeHidden();
});
