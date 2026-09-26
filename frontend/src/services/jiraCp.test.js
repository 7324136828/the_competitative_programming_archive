import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';
import { importStories, submitCodingResult, aiGenerateStory } from './api.js';

const originalFetch = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = originalFetch;
});

const jsonResponse = (data, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });

test('importStories sends stories payload with feature and epic mapping', async () => {
  const calls = [];
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options });
    return jsonResponse({
      success: true,
      epics_created: 1,
      features_created: 2,
      stories_created: 3,
    });
  };

  const payload = {
    projectId: 'PROJ-1',
    epicName: 'Algorithm Mastery',
    featureName: 'Arrays & Hashing',
    stories: [
      { title: 'Two Sum', difficulty: 'Easy', story_type: 'coding' },
      { title: 'Learn Hashes', story_type: 'learning' },
    ],
  };

  const res = await importStories(payload);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, '/api/issues/import-stories');
  assert.equal(calls[0].options.method, 'POST');
  assert.deepEqual(JSON.parse(calls[0].options.body), payload);
  assert.equal(res.stories_created, 3);
});

test('submitCodingResult posts verdict and returns updated issue', async () => {
  const calls = [];
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options });
    return jsonResponse({
      success: true,
      issue_id: 'issue-123',
      submission_status: 'Accepted',
      status: 'Done',
    });
  };

  const res = await submitCodingResult('issue-123', {
    verdict: 'Accepted',
    test_results: { status: 'Accepted', passedTests: 5, totalTests: 5 },
  });

  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, '/api/issues/issue-123/submission');
  assert.equal(calls[0].options.method, 'POST');
  assert.equal(res.status, 'Done');
  assert.equal(res.submission_status, 'Accepted');
});

test('aiGenerateStory requests story synthesis with specified story_type', async () => {
  const calls = [];
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options });
    return jsonResponse({
      success: true,
      issue: {
        id: 'issue-ai-1',
        key: 'CP-99',
        summary: 'Sliding Window Median',
        story_type: 'coding',
        difficulty: 'Hard',
        status: 'To Do',
      },
    });
  };

  const payload = {
    projectId: 'PROJ-1',
    story_type: 'coding',
    difficulty: 'Hard',
    prompt: 'Create a problem about finding median in sliding window using two heaps.',
  };

  const res = await aiGenerateStory(payload);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, '/api/ai/generate-story');
  assert.equal(res.issue.key, 'CP-99');
  assert.equal(res.issue.story_type, 'coding');
});
