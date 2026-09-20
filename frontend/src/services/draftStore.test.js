import assert from 'node:assert/strict';
import { test } from 'node:test';
import { DraftStore } from './draftStore.js';
import { CODE_TEMPLATES } from '../utils/codeTemplates.js';

const absent = () => Promise.resolve({ draft: { code: null, saved: false, revision: 0 } });
const deferred = () => { let resolve; const promise = new Promise(done => { resolve = done; }); return { promise, resolve }; };

test('drafts are independent per problem/language and a saved empty file stays empty', async () => {
  const writes = [];
  const store = new DraftStore({ load: async (id, language) => id === 2 ? { draft: { code: '', saved: true, revision: 4 } } : absent(), save: async (...args) => { writes.push(args); return { draft: { revision: args[3] + 1 } }; }, delay: 60000 });
  await Promise.all([store.ensure(1, 'python'), store.ensure(1, 'cpp'), store.ensure(2, 'python')]);
  assert.equal(store.get(1, 'python').code, CODE_TEMPLATES.python);
  assert.equal(store.get(1, 'cpp').code, CODE_TEMPLATES.cpp);
  assert.equal(store.get(2, 'python').code, '');
  store.change(1, 'python', 'print(42)');
  await store.flushAll();
  assert.deepEqual(writes, [[1, 'python', 'print(42)', 0]]);
  assert.equal(store.get(2, 'python').code, '');
  assert.equal(store.get(1, 'python').status, 'saved');
});

test('typing while a save is pending queues the latest code behind its revision', async () => {
  const pending = deferred();
  const writes = [];
  const store = new DraftStore({ load: absent, delay: 60000, save: async (...args) => { writes.push(args); if (writes.length === 1) await pending.promise; return { draft: { revision: args[3] + 1 } }; } });
  await store.ensure(1, 'python');
  store.change(1, 'python', 'first');
  const saving = store.flush(store.get(1, 'python'));
  store.change(1, 'python', 'newer');
  store.change(1, 'python', 'latest');
  assert.equal(writes.length, 1);
  pending.resolve();
  await saving;
  assert.deepEqual(writes, [[1, 'python', 'first', 0], [1, 'python', 'latest', 1]]);
  assert.equal(store.get(1, 'python').code, 'latest');
  assert.equal(store.get(1, 'python').revision, 2);
  assert.equal(store.hasPending(), false);
  store.clear();
});

test('failed loads do not silently substitute a starter and cannot overwrite the disk draft', async () => {
  let attempts = 0;
  const store = new DraftStore({ load: async () => { if (++attempts === 1) throw Error('Offline'); return { draft: { code: 'on disk', saved: true, revision: 2 } }; }, save: () => assert.fail('must not save') });
  await store.ensure(1, 'python');
  assert.equal(store.get(1, 'python').loaded, false);
  store.change(1, 'python', 'overwrite');
  assert.equal(store.get(1, 'python').code, '');
  await store.retry(1, 'python');
  assert.equal(store.get(1, 'python').code, 'on disk');
});

test('save failures preserve all edits until an explicit retry succeeds', async () => {
  let attempts = 0;
  const store = new DraftStore({ load: absent, delay: 60000, save: async () => { if (++attempts === 1) throw Error('Disk unavailable'); return { draft: { revision: 1 } }; } });
  await store.ensure(1, 'python');
  store.change(1, 'python', 'before error');
  await store.flushAll();
  store.change(1, 'python', 'after error');
  await store.flushAll();
  assert.equal(attempts, 1);
  assert.equal(store.get(1, 'python').code, 'after error');
  assert.equal(store.get(1, 'python').status, 'error');
  await store.retry(1, 'python');
  assert.equal(store.get(1, 'python').status, 'saved');
  assert.equal(attempts, 2);
});

test('revision conflicts require explicit choice and never discard local edits', async () => {
  let loads = 0;
  const writes = [];
  const store = new DraftStore({ delay: 60000, load: async () => ({ draft: { code: loads++ ? 'other tab' : null, saved: loads > 1, revision: loads > 1 ? 5 : 0 } }), save: async (...args) => { writes.push(args); if (args[3] === 0) throw Object.assign(Error('Changed elsewhere'), { status: 409 }); return { draft: { revision: 6 } }; } });
  await store.ensure(1, 'python');
  store.change(1, 'python', 'my edits');
  await store.flushAll();
  await store.retry(1, 'python');
  assert.equal(store.get(1, 'python').status, 'conflict');
  assert.equal(store.get(1, 'python').code, 'my edits');
  assert.equal(writes.length, 1);
  await store.resolveConflict(1, 'python', true);
  assert.deepEqual(writes[1], [1, 'python', 'my edits', 5]);
  assert.equal(store.get(1, 'python').code, 'my edits');
  assert.equal(store.get(1, 'python').status, 'saved');
});

test('clearing the database invalidates outstanding draft loads', async () => {
  const pending = deferred();
  const store = new DraftStore({ load: () => pending.promise });
  const loading = store.ensure(1, 'python');
  store.clear();
  pending.resolve({ draft: { code: 'old database', saved: true, revision: 9 } });
  await loading;
  assert.equal(store.get(1, 'python'), undefined);
});

test('import waits for the destination draft and saves against its existing revision', async () => {
  const pending = deferred();
  const writes = [];
  const store = new DraftStore({ load: () => pending.promise, delay: 60000, save: async (...args) => { writes.push(args); return { draft: { revision: args[3] + 1 } }; } });
  const importing = store.importCode(1, 'cpp', '// imported');
  assert.equal(store.get(1, 'cpp').loaded, false);
  pending.resolve({ draft: { code: '// previous', saved: true, revision: 7 } });
  assert.equal(await importing, true);
  await store.flushAll();
  assert.deepEqual(writes, [[1, 'cpp', '// imported', 7]]);
});

test('canceled imports and failed destination draft loads preserve saved code', async () => {
  const pending = deferred();
  const store = new DraftStore({ load: () => pending.promise, save: () => assert.fail('must not save') });
  let current = true;
  const importing = store.importCode(1, 'cpp', '// imported', () => current);
  current = false;
  pending.resolve({ draft: { code: '// saved', saved: true, revision: 2 } });
  assert.equal(await importing, false);
  assert.equal(store.get(1, 'cpp').code, '// saved');
  const failing = new DraftStore({ load: async () => { throw Error('Disk unavailable'); }, save: () => assert.fail('must not save') });
  await assert.rejects(failing.importCode(1, 'python', 'print(1)'), /Disk unavailable/);
  assert.equal(failing.get(1, 'python').dirty, false);
});
