import { expect, test, type APIRequestContext, type Page } from '@playwright/test';
import { readFile, unlink } from 'node:fs/promises';
import { basename, dirname, isAbsolute, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const e2eRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const fixtureRoot = join(e2eRoot, 'test-results', 'settings-fixtures');
let settingsFile: string | undefined;

test.use({ viewport: { width: 1400, height: 1000 } });

async function getSettings(request: APIRequestContext) {
  const response = await request.get('/api/settings');
  expect(response.ok()).toBeTruthy();
  return response.json();
}

async function openStorage(page: Page) {
  await page.goto('/#settings');
  await page.getByRole('button', { name: 'Storage', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Data storage', exact: true })).toBeVisible();
}

function assertFixturePath(path: string) {
  const local = relative(fixtureRoot, path);
  expect(isAbsolute(local)).toBe(false);
  expect(local === '..' || local.startsWith(`..${process.platform === 'win32' ? '\\' : '/'}`)).toBe(false);
}

test.beforeEach(async ({ request }) => {
  const reset = await request.put('/api/settings', { data: { data_dir: '' } });
  expect(reset.ok()).toBeTruthy();
  const settings = await reset.json();
  settingsFile = settings.settings_path;
  assertFixturePath(settings.settings_path);
  assertFixturePath(settings.default_data_dir);
  expect(settings.editable).toBe(true);
  expect(settings.restart_required).toBe(false);
});

test.afterEach(async ({ request }) => {
  expect((await request.put('/api/settings', { data: { data_dir: '' } })).ok()).toBeTruthy();
});

test.afterAll(async () => {
  if (settingsFile) {
    assertFixturePath(settingsFile);
    await unlink(settingsFile).catch(error => { if (error.code !== 'ENOENT') throw error; });
  }
});

test('host storage settings persist in APPDATA without changing the active folder before restart', async ({ page, request }, testInfo) => {
  const initial = await getSettings(request);
  expect(initial.app_name).toBe('the_study_platform');
  expect(basename(initial.settings_path)).toBe('settings.json');
  expect(basename(dirname(initial.settings_path))).toBe(initial.app_name);
  expect(basename(dirname(dirname(initial.settings_path)))).toBe('appdata');
  expect(basename(initial.default_data_dir)).toBe(initial.app_name);
  expect(basename(dirname(initial.default_data_dir))).toBe('temp');
  expect(initial.data_dir).toBe(initial.default_data_dir);
  expect(initial.active_data_dir).toBe(initial.default_data_dir);

  await openStorage(page);
  const storage = page.getByRole('region', { name: 'Data storage', exact: true });
  const folder = storage.getByLabel('Data storage folder', { exact: true });
  const active = storage.locator('dl div').filter({ has: page.getByText('Active storage folder', { exact: true }) });
  await expect(folder).toHaveValue(initial.default_data_dir);
  await expect(active.locator('dd')).toHaveText(initial.active_data_dir);
  await expect(storage.getByText(initial.settings_path, { exact: true })).toBeVisible();
  await expect(storage.getByText('When connected over LAN', { exact: false })).toBeVisible();
  await expect(storage.getByRole('button', { name: 'Save storage folder', exact: true })).toBeDisabled();
  await expect(storage.getByRole('button', { name: 'Use default folder', exact: true })).toBeDisabled();

  const chosenFolder = join(dirname(dirname(initial.settings_path)), 'chosen data');
  assertFixturePath(chosenFolder);
  await folder.fill(`  ${chosenFolder}  `);
  const savedResponse = page.waitForResponse(response => response.url().endsWith('/api/settings') && response.request().method() === 'PUT');
  await storage.getByRole('button', { name: 'Save storage folder', exact: true }).click();
  expect((await savedResponse).ok()).toBeTruthy();
  await expect(folder).toHaveValue(chosenFolder);
  await expect(storage.getByRole('status').filter({ hasText: 'Restart required.' })).toBeVisible();
  await expect(active.locator('dd')).toHaveText(initial.active_data_dir);
  expect(JSON.parse(await readFile(initial.settings_path, 'utf8')).data_dir).toBe(chosenFolder);
  const saved = await getSettings(request);
  expect(saved.data_dir).toBe(chosenFolder);
  expect(saved.active_data_dir).toBe(initial.active_data_dir);
  expect(saved.restart_required).toBe(true);
  await page.screenshot({ path: testInfo.outputPath('storage-restart-required.png'), fullPage: true });

  await openStorage(page);
  await expect(folder).toHaveValue(chosenFolder);
  await expect(storage.getByRole('status').filter({ hasText: 'Restart required.' })).toBeVisible();
  await storage.getByRole('button', { name: 'Use default folder', exact: true }).click();
  await expect(folder).toHaveValue(initial.default_data_dir);
  await expect(storage.getByRole('status').filter({ hasText: 'Restart required.' })).toHaveCount(0);
  await expect(storage.getByRole('status')).toContainText('already active');
  await expect(active.locator('dd')).toHaveText(initial.active_data_dir);
  expect(JSON.parse(await readFile(initial.settings_path, 'utf8')).data_dir).toBe('');
  expect((await getSettings(request)).restart_required).toBe(false);
});

test('LAN clients see host storage paths with editing disabled', async ({ page, request }) => {
  const settings = await getSettings(request);
  await page.route('**/api/settings', async route => {
    expect(route.request().method()).toBe('GET');
    await route.fulfill({ json: { ...settings, editable: false } });
  });
  await openStorage(page);
  const storage = page.getByRole('region', { name: 'Data storage', exact: true });
  await expect(storage.getByLabel('Data storage folder', { exact: true })).toHaveValue(settings.data_dir);
  await expect(storage.getByLabel('Data storage folder', { exact: true })).toBeDisabled();
  await expect(storage.getByRole('button', { name: 'Save storage folder', exact: true })).toBeDisabled();
  await expect(storage.getByRole('button', { name: 'Use default folder', exact: true })).toBeDisabled();
  await expect(storage.getByText('Storage settings can only be changed from a browser on the host computer.', { exact: true })).toBeVisible();
});
