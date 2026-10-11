import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';
import { fetchModels, fetchHint, fetchProblems, fetchSettings, generateProblemTags, generateSimilarProblem, generateTestCases, submitCode, updateSettings } from './api.js';

const originalFetch = globalThis.fetch;
afterEach(() => { globalThis.fetch = originalFetch; });
const response = (data, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });

test('storage settings use the host API and preserve cancellation and read-only metadata', async () => {
  const controller = new AbortController();
  const settings = { success: true, data_dir: 'C:\\data', active_data_dir: 'C:\\data', editable: false };
  globalThis.fetch = async (url, options) => {
    assert.equal(url, '/api/settings');
    assert.equal(options.signal, controller.signal);
    return response(settings);
  };
  assert.deepEqual(await fetchSettings({ signal: controller.signal }), settings);
});

test('storage settings save trimmed host folder paths and reset with an empty path', async () => {
  const calls = [];
  globalThis.fetch = async (url, options) => {
    calls.push([url, options]);
    return response({ success: true, restart_required: true });
  };
  assert.equal((await updateSettings('  C:\\Study data  ')).restart_required, true);
  await updateSettings('');
  assert.deepEqual(calls.map(([url, options]) => [url, options.method, options.headers, JSON.parse(options.body)]), [
    ['/api/settings', 'PUT', { 'Content-Type': 'application/json' }, { data_dir: 'C:\\Study data' }],
    ['/api/settings', 'PUT', { 'Content-Type': 'application/json' }, { data_dir: '' }],
  ]);
});

test('storage settings show host validation and authorization errors', async () => {
  globalThis.fetch = async () => response({ success: false, error: 'Use an absolute folder path.' }, 400);
  await assert.rejects(updateSettings('relative-folder'), /Use an absolute folder path/);
  globalThis.fetch = async () => response({ success: false, error: 'Storage settings may only be changed locally.' }, 403);
  await assert.rejects(updateSettings('C:\\data'), /only be changed locally/);
  globalThis.fetch = async () => new Response('Not JSON', { status: 503 });
  await assert.rejects(fetchSettings(), /Unable to load storage settings/);
});

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

test('problem filters and tag batches use the expected API payloads', async () => {
  const calls = [];
  globalThis.fetch = async (url, options = {}) => {
    calls.push([url, options]);
    return response({ success: true, problems: [], tags: [] });
  };
  await fetchProblems({ page: 3, limit: 25, solved: 'unsolved' });
  await generateProblemTags({ problemIds: [2, 4, 6], model: 'my-config' });
  assert.equal(calls[0][0], '/api/problems?page=3&limit=25&solved=unsolved');
  assert.equal(calls[1][0], '/api/llm/generate-tags');
  assert.deepEqual(JSON.parse(calls[1][1].body), { problemIds: [2, 4, 6], model: 'my-config' });
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
