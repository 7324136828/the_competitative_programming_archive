import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';
import {
  getWorkspaceStatus,
  associateStoryWithStudySet,
  createStoryForStudySet,
  unlinkStory,
  generatePodcast,
} from '../components/studyset/lib/api.ts';

const originalFetch = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = originalFetch;
});

const jsonResponse = (data, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });

test('getWorkspaceStatus requests /api/workspace and returns uploaded workspaces', async () => {
  const calls = [];
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options });
    return jsonResponse({
      currentWorkspace: 'ws-1',
      workspaces: [
        { id: 'ws-1', name: 'Algorithms Review', story_id: 'issue-10' },
      ],
    });
  };

  const res = await getWorkspaceStatus();
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, '/api/workspace');
  assert.equal(res.workspaces.length, 1);
  assert.equal(res.workspaces[0].name, 'Algorithms Review');
  assert.equal(res.workspaces[0].story_id, 'issue-10');
});

test('associateStoryWithStudySet posts workspaceId and storyId', async () => {
  const calls = [];
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options });
    return jsonResponse({
      success: true,
      workspaceId: 'ws-1',
      storyId: 'issue-42',
    });
  };

  const res = await associateStoryWithStudySet('ws-1', 'issue-42');
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, '/api/workspace/associate-story');
  assert.equal(calls[0].options.method, 'POST');
  assert.deepEqual(JSON.parse(calls[0].options.body), {
    workspaceId: 'ws-1',
    issueId: 'issue-42',
  });
  assert.equal(res.success, true);
});

test('createStoryForStudySet creates a Jira story linked to the study set', async () => {
  const calls = [];
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options });
    return jsonResponse({
      success: true,
      issue: {
        id: 'issue-new',
        key: 'CP-50',
        summary: 'Master Graph Algorithms',
        story_type: 'study',
        study_set_id: 'ws-2',
      },
    });
  };

  const res = await createStoryForStudySet('ws-2', 'Master Graph Algorithms', 'PROJ-1');
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, '/api/workspace/create-story');
  assert.equal(calls[0].options.method, 'POST');
  assert.deepEqual(JSON.parse(calls[0].options.body), {
    workspaceId: 'ws-2',
    summary: 'Master Graph Algorithms',
    projectId: 'PROJ-1',
  });
  assert.equal(res.issue.story_type, 'study');
  assert.equal(res.issue.study_set_id, 'ws-2');
});

test('unlinkStory posts workspaceId to unlink endpoint', async () => {
  const calls = [];
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options });
    return jsonResponse({ success: true, workspaceId: 'ws-1' });
  };

  const res = await unlinkStory('ws-1');
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, '/api/workspace/unlink-story');
  assert.equal(calls[0].options.method, 'POST');
  assert.deepEqual(JSON.parse(calls[0].options.body), { workspaceId: 'ws-1' });
  assert.equal(res.success, true);
});

test('generatePodcast requests /api/generate_podcast with options', async () => {
  const calls = [];
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options });
    return jsonResponse({
      job_id: 'job-123',
      status: 'pending',
    });
  };

  const res = await generatePodcast('ep1.json', { voiceA: 'af_heart', voiceB: 'am_adam' });
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, '/api/generate_podcast');
  assert.equal(calls[0].options.method, 'POST');
  assert.deepEqual(JSON.parse(calls[0].options.body), {
    podcast_file: 'ep1.json',
    voiceA: 'af_heart',
    voiceB: 'am_adam',
  });
  assert.equal(res.job_id, 'job-123');
});
