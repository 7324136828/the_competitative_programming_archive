import { expect, test, type Locator, type Page } from '@playwright/test';

test.use({ viewport: { width: 1280, height: 900 } });

test.beforeEach(async ({ page, request }) => {
  expect((await request.delete('/api/database')).ok()).toBeTruthy();
  const created = await request.post('/api/problems', { data: {
    title: 'Workspace A + B',
    problem_statements: 'Read two integers and print their sum.',
    sample_input_output: [{ input: '2 3', output: '5' }],
    difficulty: 'Easy',
  } });
  expect(created.ok()).toBeTruthy();
  await page.goto('/');
  await page.getByRole('row').filter({ hasText: 'Workspace A + B' }).click();
  await expect(page.getByRole('region', { name: 'Problem panel', exact: true })).toBeVisible();
  await expect(page.getByRole('combobox', { name: 'Programming language' })).toBeEnabled();
  await expect(page.locator('.cm-content')).toHaveAttribute('contenteditable', 'true');
  await expect(page.getByPlaceholder('Enter custom input...')).toHaveValue('2 3');
});

async function bounds(locator: Locator) {
  const box = await locator.boundingBox();
  expect(box).not.toBeNull();
  return box!;
}

async function dragSeparator(page: Page, separator: Locator, dx: number, dy: number) {
  const box = await bounds(separator);
  const x = box.x + box.width / 2;
  const y = box.y + box.height / 2;
  await page.mouse.move(x, y);
  await page.mouse.down();
  await page.mouse.move(x + dx, y + dy, { steps: 8 });
  await page.mouse.up();
}

test('visible separators resize both splits with the mouse and reset on double click', async ({ page }) => {
  const problem = page.getByRole('region', { name: 'Problem panel', exact: true });
  const editor = page.getByRole('region', { name: 'Code editor panel', exact: true });
  const cases = page.getByRole('region', { name: 'Test cases panel', exact: true });
  const columns = page.getByRole('separator', { name: 'Resize problem and editor' });
  const rows = page.getByRole('separator', { name: 'Resize editor and test cases' });
  await expect(columns).toBeVisible();
  await expect(columns).toHaveAttribute('aria-orientation', 'vertical');
  await expect(rows).toBeVisible();
  await expect(rows).toHaveAttribute('aria-orientation', 'horizontal');
  expect((await bounds(columns)).width).toBeGreaterThanOrEqual(6);
  expect((await bounds(rows)).height).toBeGreaterThanOrEqual(6);

  const originalProblem = await bounds(problem);
  const originalEditor = await bounds(editor);
  const originalCases = await bounds(cases);
  await dragSeparator(page, columns, 110, 0);
  await expect.poll(async () => (await bounds(problem)).width).toBeGreaterThan(originalProblem.width + 80);
  expect((await bounds(editor)).width).toBeLessThan(originalEditor.width - 80);
  await dragSeparator(page, rows, 0, -90);
  await expect.poll(async () => (await bounds(editor)).height).toBeLessThan(originalEditor.height - 60);
  expect((await bounds(cases)).height).toBeGreaterThan(originalCases.height + 60);

  await columns.dblclick();
  await rows.dblclick();
  await expect.poll(async () => Math.abs((await bounds(problem)).width - originalProblem.width)).toBeLessThan(2);
  await expect.poll(async () => Math.abs((await bounds(editor)).height - originalEditor.height)).toBeLessThan(2);
});

test('splitters support keyboard resizing without collapsing either pane', async ({ page }) => {
  const problem = page.getByRole('region', { name: 'Problem panel', exact: true });
  const editor = page.getByRole('region', { name: 'Code editor panel', exact: true });
  const cases = page.getByRole('region', { name: 'Test cases panel', exact: true });
  const columns = page.getByRole('separator', { name: 'Resize problem and editor' });
  const rows = page.getByRole('separator', { name: 'Resize editor and test cases' });
  const originalProblem = await bounds(problem);
  const originalEditor = await bounds(editor);

  await columns.focus();
  await columns.press('ArrowRight');
  await expect.poll(async () => (await bounds(problem)).width).toBeGreaterThan(originalProblem.width);
  await columns.press('ArrowLeft');
  await expect.poll(async () => Math.abs((await bounds(problem)).width - originalProblem.width)).toBeLessThan(2);
  await rows.focus();
  await rows.press('ArrowDown');
  await expect.poll(async () => (await bounds(editor)).height).toBeGreaterThan(originalEditor.height);
  await rows.press('ArrowUp');
  await expect.poll(async () => Math.abs((await bounds(editor)).height - originalEditor.height)).toBeLessThan(2);

  await dragSeparator(page, columns, 1600, 0);
  expect((await bounds(editor)).width).toBeGreaterThan(200);
  await dragSeparator(page, columns, -1600, 0);
  expect((await bounds(problem)).width).toBeGreaterThan(200);
  await dragSeparator(page, rows, 0, 1200);
  expect((await bounds(cases)).height).toBeGreaterThan(100);
  await dragSeparator(page, rows, 0, -1200);
  expect((await bounds(editor)).height).toBeGreaterThan(100);
});

for (const panel of [
  { region: 'Problem panel', button: 'Expand problem' },
  { region: 'Code editor panel', button: 'Expand code editor' },
  { region: 'Test cases panel', button: 'Expand test cases' },
]) {
  test(`${panel.region} expands to the viewport and restores draft, selected case, and split sizes`, async ({ page }, testInfo) => {
    const problem = page.getByRole('region', { name: 'Problem panel', exact: true });
    const editor = page.getByRole('region', { name: 'Code editor panel', exact: true });
    const cases = page.getByRole('region', { name: 'Test cases panel', exact: true });
    const columns = page.getByRole('separator', { name: 'Resize problem and editor' });
    const rows = page.getByRole('separator', { name: 'Resize editor and test cases' });
    const draft = '# Keep this draft when changing panel layout\nprint(42)';
    await page.locator('.cm-content').fill(draft);
    await cases.getByRole('button', { name: 'Add Case', exact: true }).click();
    await page.getByPlaceholder('Enter custom input...').fill('17 25');
    await page.getByPlaceholder('Enter expected output...').fill('42');
    await dragSeparator(page, columns, -70, 0);
    await dragSeparator(page, rows, 0, -45);
    const originalProblem = await bounds(problem);
    const originalEditor = await bounds(editor);
    if (panel.region === 'Code editor panel') {
      await page.screenshot({ path: testInfo.outputPath('workspace-desktop.png') });
    }

    const expanded = page.getByRole('region', { name: panel.region, exact: true });
    await page.getByRole('button', { name: panel.button, exact: true }).click();
    const viewport = page.viewportSize()!;
    await expect.poll(async () => (await bounds(expanded)).width).toBeGreaterThanOrEqual(viewport.width - 2);
    const expandedBounds = await bounds(expanded);
    expect(expandedBounds.height).toBeGreaterThanOrEqual(viewport.height - 2);
    expect(Math.abs(expandedBounds.x)).toBeLessThan(2);
    expect(Math.abs(expandedBounds.y)).toBeLessThan(2);
    if (panel.region === 'Code editor panel') {
      await page.screenshot({ path: testInfo.outputPath('workspace-code-fullscreen.png') });
    }
    await expect(expanded.getByRole('button', { name: 'Restore layout', exact: true })).toBeVisible();
    await expect(columns).toBeHidden();
    await expect(rows).toBeHidden();
    for (const other of ['Problem panel', 'Code editor panel', 'Test cases panel']) {
      if (other !== panel.region) {
        await expect(page.getByRole('region', { name: other, exact: true })).toBeHidden();
      }
    }

    await page.keyboard.press('Escape');
    await expect(problem).toBeVisible();
    await expect(editor).toBeVisible();
    await expect(cases).toBeVisible();
    await expect(page.locator('.cm-line')).toHaveText(draft.split('\n'));
    await expect(page.getByPlaceholder('Enter custom input...')).toHaveValue('17 25');
    await expect(page.getByPlaceholder('Enter expected output...')).toHaveValue('42');
    await expect.poll(async () => Math.abs((await bounds(problem)).width - originalProblem.width)).toBeLessThan(2);
    await expect.poll(async () => Math.abs((await bounds(editor)).height - originalEditor.height)).toBeLessThan(2);
    await cases.getByRole('button', { name: 'Case 1', exact: true }).click();
    await expect(page.getByPlaceholder('Enter custom input...')).toHaveValue('2 3');
    await cases.getByRole('button', { name: 'Case 2', exact: true }).click();
    await expect(page.getByPlaceholder('Enter custom input...')).toHaveValue('17 25');

    // The visible restore control should work as well as the Escape shortcut.
    await page.getByRole('button', { name: panel.button, exact: true }).click();
    await page.getByRole('button', { name: 'Restore layout', exact: true }).click();
    await expect(columns).toBeVisible();
    await expect(rows).toBeVisible();
    await expect(page.locator('.cm-line')).toHaveText(draft.split('\n'));
  });
}

test('narrow screens stack the workspace and expand each panel without losing data', async ({ page }, testInfo) => {
  const draft = '# Mobile draft\nprint(42)';
  await page.locator('.cm-content').fill(draft);
  await page.getByPlaceholder('Enter custom input...').fill('17 25');
  await page.setViewportSize({ width: 390, height: 844 });

  const problem = page.getByRole('region', { name: 'Problem panel', exact: true });
  const editor = page.getByRole('region', { name: 'Code editor panel', exact: true });
  const divider = page.getByRole('separator', { name: 'Resize problem and editor' });
  await expect(divider).toHaveAttribute('aria-orientation', 'horizontal');
  const originalProblem = await bounds(problem);
  const editorBounds = await bounds(editor);
  expect(editorBounds.y).toBeGreaterThanOrEqual(originalProblem.y + originalProblem.height);
  expect(originalProblem.width).toBeLessThanOrEqual(390);
  expect(editorBounds.width).toBeLessThanOrEqual(390);
  await divider.focus();
  await divider.press('ArrowDown');
  await expect.poll(async () => (await bounds(problem)).height).toBeGreaterThan(originalProblem.height);
  await page.screenshot({ path: testInfo.outputPath('workspace-mobile.png') });

  for (const panel of [
    { region: 'Problem panel', button: 'Expand problem' },
    { region: 'Code editor panel', button: 'Expand code editor' },
    { region: 'Test cases panel', button: 'Expand test cases' },
  ]) {
    await page.getByRole('button', { name: panel.button, exact: true }).click();
    const expanded = page.getByRole('region', { name: panel.region, exact: true });
    await expect.poll(async () => (await bounds(expanded)).height).toBeGreaterThanOrEqual(842);
    const expandedBounds = await bounds(expanded);
    expect(expandedBounds.width).toBeGreaterThanOrEqual(388);
    expect(expandedBounds.width).toBeLessThanOrEqual(390);
    expect(Math.abs(expandedBounds.x)).toBeLessThan(2);
    expect(Math.abs(expandedBounds.y)).toBeLessThan(2);
    if (panel.region === 'Test cases panel') {
      await expect(page.getByPlaceholder('Enter custom input...')).toHaveValue('17 25');
      await page.screenshot({ path: testInfo.outputPath('workspace-test-cases-mobile-fullscreen.png') });
    }
    await expanded.getByRole('button', { name: 'Restore layout', exact: true }).click();
    await expect(divider).toBeVisible();
    await expect(problem).toBeVisible();
    await expect(editor).toBeVisible();
  }

  await page.getByRole('button', { name: 'Expand code editor', exact: true }).click();
  await expect(page.locator('.cm-line')).toHaveText(draft.split('\n'));
  await page.keyboard.press('Escape');
  await expect(divider).toBeVisible();
});
