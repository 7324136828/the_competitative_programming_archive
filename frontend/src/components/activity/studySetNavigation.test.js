import assert from 'node:assert/strict';
import test from 'node:test';
import { navigateToLinkedStudySet } from './studySetNavigation.js';

test('opens the linked study set and preserves the chosen viewer', async () => {
  const calls = [];
  await navigateToLinkedStudySet(
    'study-42', 'quizzes',
    async id => {
      calls.push(['activate', id]);
      return { activeWorkspace: id };
    },
    (id, tab) => calls.push(['navigate', id, tab]),
  );
  assert.deepEqual(calls, [
    ['activate', 'study-42'],
    ['navigate', 'study-42', 'quizzes'],
  ]);
});

test('missing or deleted study sets keep the activity open and report the problem', async () => {
  let navigated = false;
  const navigate = () => { navigated = true; };

  await assert.rejects(
    navigateToLinkedStudySet(null, 'home', async () => { throw new Error('unexpected'); }, navigate),
    /No study set is linked/,
  );
  await assert.rejects(
    navigateToLinkedStudySet('deleted', 'flashcards', async () => {
      throw new Error('Workspace not found');
    }, navigate),
    /linked study set is unavailable/,
  );
  await assert.rejects(
    navigateToLinkedStudySet('study-42', 'home', async () => ({ activeWorkspace: 'other' }), navigate),
    /could not be activated/,
  );
  await assert.rejects(
    navigateToLinkedStudySet('study-42', 'home', async () => {
      throw new Error('Connection lost');
    }, navigate),
    /Could not open the linked study set: Connection lost/,
  );
  assert.equal(navigated, false);
});
