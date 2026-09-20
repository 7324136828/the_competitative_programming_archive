import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';
import { fetchModels, fetchHint, generateSimilarProblem, generateTestCases, submitCode } from './api.js';

const originalFetch = globalThis.fetch;
afterEach(() => { globalThis.fetch = originalFetch; });
const response = (data, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });

test('models must include the selected configuration before AI tasks can use it', async () => {
  globalThis.fetch = async () => response({ success: true, model: 'my-config', models: [{ id: 'my-config' }] });
  assert.equal((await fetchModels()).model, 'my-config');
  globalThis.fetch = async () => response({ success: true, model: 'missing', models: [{ id: 'my-config' }] });
  await assert.rejects(fetchModels(), /did not return an available AI model/);
});

test('AI task requests pass the discovered model and expose server error details', async () => {
  const requested = [];
  globalThis.fetch = async (url, options) => {
    requested.push([url, JSON.parse(options.body)]);
    return response({ success: false, error: 'The Connector returned no active models. Configure an alias first.' }, 502);
  };
  for (const action of [fetchHint, generateSimilarProblem, generateTestCases]) {
    await assert.rejects(action({ problemId: 4, model: 'my-config' }), /Configure an alias first/);
  }
  assert.deepEqual(requested.map(([, body]) => body.model), ['my-config', 'my-config', 'my-config']);
});

test('submission waits through compile and run phases, returns final stdout, and posts only once', async () => {
  const calls = [];
  const progress = [];
  const finalResult = { success: true, done: true, phase: 'completed', grading: { status: 'Accepted', results: [{ stdout: '3\n' }] } };
  const replies = [
    { success: true, jobId: 'job-1', done: false, phase: 'queued' },
    { success: true, jobId: 'job-1', done: false, phase: 'compiling' },
    { success: true, jobId: 'job-1', done: false, phase: 'running' },
    finalResult,
  ];
  globalThis.fetch = async (url, options = {}) => {
    calls.push([url, options]);
    return response(replies.shift(), calls.length === 1 ? 202 : 200);
  };
  const result = await submitCode({ problemId: 1, language: 'cpp', code: 'code', customTestCases: [] }, {
    pollIntervalMs: 0,
    onProgress: job => progress.push(job.phase),
  });
  assert.deepEqual(result, finalResult);
  assert.deepEqual(progress, ['queued', 'compiling', 'running']);
  assert.equal(calls.filter(([, options]) => options.method === 'POST').length, 1);
  assert.equal(JSON.parse(calls[0][1].body).async, true);
  assert.deepEqual(JSON.parse(calls[0][1].body).customTestCases, []);
  assert.deepEqual(calls.slice(1).map(([url]) => url), Array(3).fill('/api/submission-jobs/job-1'));
});

test('synchronous responses remain supported without polling', async () => {
  let calls = 0;
  globalThis.fetch = async () => {
    calls += 1;
    return response({ success: true, grading: { status: 'Not Judged' } });
  };
  const result = await submitCode({ language: 'cpp', code: 'code' });
  assert.equal(result.grading.status, 'Not Judged');
  assert.equal(calls, 1);
});

test('problem changes abort polling without submitting or showing a result again', async () => {
  const controller = new AbortController();
  let calls = 0;
  globalThis.fetch = async () => {
    calls += 1;
    return response({ success: true, jobId: 'job-1', done: false, phase: 'compiling' }, 202);
  };
  await assert.rejects(submitCode({ language: 'cpp', code: 'code' }, {
    signal: controller.signal,
    onProgress: () => controller.abort(),
  }), { name: 'AbortError' });
  assert.equal(calls, 1);
});

test('a finished job without grading does not become a false success', async () => {
  globalThis.fetch = async () => response({ success: true, done: true });
  await assert.rejects(submitCode({ language: 'cpp', code: 'code' }), /without a grading result/);
});

test('stalled jobs time out without retrying the original submission', async () => {
  let calls = 0;
  globalThis.fetch = async () => {
    calls += 1;
    return response({ success: true, jobId: 'job-1', done: false, phase: 'queued' }, 202);
  };
  await assert.rejects(submitCode({ language: 'cpp', code: 'code' }, { waitTimeoutMs: 0 }), /Check submission history before submitting again/);
  assert.equal(calls, 1);
});
