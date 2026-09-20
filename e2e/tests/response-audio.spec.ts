/// <reference lib="dom" />
import { expect, test, type Page } from '@playwright/test';
import { readFile } from 'node:fs/promises';

const reply = 'The checksum is $N + 1$. Try a small example before writing your solution.';
const key = 'c'.repeat(64);
const audioUrl = `/api/audio/${key}.mp3`;

async function askAssistant(page: Page) {
  await page.getByRole('button', { name: 'AI Chat', exact: true }).click();
  await page.getByPlaceholder('Ask a question about this problem, algorithms, or code...').fill('Explain the checksum.');
  await page.getByRole('button', { name: 'Send message', exact: true }).click();
  await expect(page.getByRole('dialog', { name: 'AI Assistant' }).getByText('Try a small example', { exact: false })).toBeVisible();
}

test.beforeEach(async ({ page }) => {
  await page.route('**/api/chat', route => route.fulfill({ json: { success: true, reply, model: 'mock-model' } }));
  await page.goto('/');
});

test('AI narration waits for an MP3, reuses it, and Settings clears playing audio before regeneration', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 1400, height: 950 });
  const mp3 = await readFile(new URL('../fixtures/problem-audio.mp3', import.meta.url));
  let starts = 0;
  let clears = 0;
  let cached = true;
  await page.route('**/api/audio/cache', route => {
    if (route.request().method() === 'DELETE') {
      clears += 1;
      cached = false;
      return route.fulfill({ json: { success: true, cache: { removedFiles: 2, removedBytes: 2048, files: 0, bytes: 0 } } });
    }
    return route.fulfill({ json: { success: true, cache: { files: cached ? 2 : 0, bytes: cached ? 2048 : 0 } } });
  });
  await page.route('**/api/audio/responses', route => {
    starts += 1;
    expect(route.request().postDataJSON()).toEqual({ text: reply, language: 'en' });
    return route.fulfill({ status: 202, json: { success: true, audio: { key, status: 'queued', done: false, cached: false } } });
  });
  await page.route(`**/api/audio/responses/${key}`, route => route.fulfill({ json: { success: true, audio: { key, status: 'ready', done: true, cached: true, url: audioUrl } } }));
  await page.route(`**${audioUrl}`, route => route.fulfill({ body: mp3, contentType: 'audio/mpeg' }));

  await page.getByRole('button', { name: 'Settings', exact: true }).click();
  await expect(page.getByText('2 saved audio files', { exact: false })).toBeVisible();
  await askAssistant(page);
  const readAloud = page.getByRole('button', { name: 'Read response aloud', exact: true }).last();
  await readAloud.click();
  await expect(page.getByRole('status').filter({ hasText: 'Creating your MP3' })).toBeVisible();
  const player = page.getByLabel('Read AI response aloud', { exact: true });
  await expect(player).toBeVisible();
  await expect.poll(() => player.evaluate(element => (element as HTMLAudioElement).readyState)).toBeGreaterThan(0);
  await player.evaluate(element => (element as HTMLAudioElement).play());
  expect(starts).toBe(1);
  await expect(page.getByRole('link', { name: 'Download MP3', exact: true })).toHaveAttribute('href', audioUrl);
  await page.getByRole('button', { name: 'Close AI narration player' }).click();
  await readAloud.click();
  await expect(player).toBeVisible();
  expect(starts).toBe(1);

  await page.getByRole('button', { name: 'Clear saved audio', exact: true }).click();
  await expect(page.getByRole('status').filter({ hasText: 'Cleared 2 saved audio files' })).toBeVisible();
  await expect(player).toHaveCount(0);
  await expect(readAloud).toHaveAttribute('aria-expanded', 'false');
  expect(clears).toBe(1);
  await expect(page.getByText('0 saved audio files', { exact: false })).toBeVisible();
  await readAloud.click();
  await expect(player).toBeVisible();
  expect(starts).toBe(2);
  await page.screenshot({ path: testInfo.outputPath('ai-audio-settings.png') });
});

test('AI narration errors can be retried and the player fits a narrow chat drawer', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  let starts = 0;
  const mp3 = await readFile(new URL('../fixtures/problem-audio.mp3', import.meta.url));
  await page.route('**/api/audio/responses', route => {
    starts += 1;
    return starts === 1
      ? route.fulfill({ status: 503, json: { success: false, error: 'Kokoro is temporarily unavailable. Please retry.' } })
      : route.fulfill({ json: { success: true, audio: { key, status: 'ready', done: true, cached: true, url: audioUrl } } });
  });
  await page.route(`**${audioUrl}`, route => route.fulfill({ body: mp3, contentType: 'audio/mpeg' }));
  await askAssistant(page);
  const readAloud = page.getByRole('button', { name: 'Read response aloud', exact: true }).last();
  await readAloud.click();
  await expect(page.getByRole('alert')).toContainText('Kokoro is temporarily unavailable');
  await readAloud.click();
  const player = page.getByLabel('Read AI response aloud', { exact: true });
  await expect(player).toBeVisible();
  await expect(page.getByRole('alert')).toHaveCount(0);
  expect(starts).toBe(2);
  const bounds = await player.boundingBox();
  expect(bounds!.x).toBeGreaterThanOrEqual(0);
  expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(390);
});

test('Settings reports a cleanup failure and leaves the usage visible for retry', async ({ page }) => {
  let attempts = 0;
  await page.route('**/api/audio/cache', route => {
    if (route.request().method() === 'GET') return route.fulfill({ json: { success: true, cache: { files: 1, bytes: 1024 } } });
    attempts += 1;
    return attempts === 1
      ? route.fulfill({ status: 503, json: { success: false, error: 'Audio cleanup could not finish. Please retry.' } })
      : route.fulfill({ json: { success: true, cache: { removedFiles: 1, removedBytes: 1024, files: 0, bytes: 0 } } });
  });
  await page.getByRole('button', { name: 'Settings', exact: true }).click();
  await page.getByRole('button', { name: 'Clear saved audio', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Audio cleanup could not finish');
  await expect(page.getByText('1 saved audio file', { exact: false })).toBeVisible();
  await page.getByRole('button', { name: 'Clear saved audio', exact: true }).click();
  await expect(page.getByRole('status')).toContainText('Cleared 1 saved audio file');
  await expect(page.getByRole('alert')).toHaveCount(0);
  expect(attempts).toBe(2);
});

test('Settings updates after a cleanup finishes across navigation and ignores older usage responses', async ({ page }) => {
  let finishDelete!: () => void;
  let finishUsage!: () => void;
  let completeUsage!: () => void;
  let holdUsage = false;
  let heldUsageCalls = 0;
  const deletePending = new Promise<void>(resolve => { finishDelete = resolve; });
  const usagePending = new Promise<void>(resolve => { finishUsage = resolve; });
  const usageCompleted = new Promise<void>(resolve => { completeUsage = resolve; });
  await page.route('**/api/audio/cache', async route => {
    if (route.request().method() === 'DELETE') {
      await deletePending;
      return route.fulfill({ json: { success: true, cache: { removedFiles: 4, removedBytes: 4096, files: 0, bytes: 0 } } });
    }
    if (holdUsage) {
      heldUsageCalls += 1;
      await usagePending;
      try {
        await route.fulfill({ json: { success: true, cache: { files: 4, bytes: 4096 } } });
      } catch {
        // Successful cleanup aborts this obsolete browser request.
      } finally {
        completeUsage();
      }
      return;
    }
    return route.fulfill({ json: { success: true, cache: { files: 4, bytes: 4096 } } });
  });

  await page.getByRole('button', { name: 'Settings', exact: true }).click();
  await expect(page.getByText('4 saved audio files', { exact: false })).toBeVisible();
  await page.getByRole('button', { name: 'Clear saved audio', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Clearing saved audio...', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Problem Set', exact: true }).click();
  await page.getByRole('button', { name: 'Settings', exact: true }).click();
  await expect(page.getByText('4 saved audio files', { exact: false })).toBeVisible();
  holdUsage = true;
  await page.getByRole('button', { name: 'Refresh usage', exact: true }).click();
  await expect.poll(() => heldUsageCalls).toBeGreaterThan(0);
  await expect(page.getByText('Checking saved audio...', { exact: true })).toBeVisible();

  finishDelete();
  await expect(page.getByText('0 saved audio files', { exact: false })).toBeVisible();
  finishUsage();
  await usageCompleted;
  await expect(page.getByText('0 saved audio files', { exact: false })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Clear saved audio', exact: true })).toBeEnabled();
  await expect(page.getByRole('alert')).toHaveCount(0);
});
