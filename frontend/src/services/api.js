const API_BASE = '/api';

async function readResponse(res, fallback) {
  const data = await res.json().catch(() => null);
  if (!res.ok || !data?.success) throw new Error(data?.error || fallback);
  return data;
}

export async function fetchModels({ signal } = {}) {
  const res = await fetch(`${API_BASE}/llm/models`, { signal });
  const data = await readResponse(res, 'Unable to discover AI models. Please retry.');
  if (!data.model || !Array.isArray(data.models) || !data.models.some(item => item.id === data.model)) {
    throw new Error('The models API did not return an available AI model. Please retry.');
  }
  return data;
}

export async function fetchLanguages({ signal } = {}) {
  const res = await fetch(API_BASE + '/languages', { signal });
  const data = await res.json().catch(() => null);
  if (!res.ok || !data?.success || !Array.isArray(data.languages)) {
    throw new Error(data?.error || 'Unable to detect available languages. Please try again.');
  }
  return data.languages;
}

export async function clearDatabase() {
  const res = await fetch(`${API_BASE}/database`, { method: 'DELETE' });
  const data = await res.json().catch(() => null);
  if (!res.ok || !data?.success) {
    throw new Error(data?.error || 'Failed to clear the database. Please try again.');
  }
  return data;
}

export async function fetchProblems(params = {}) {
  const query = new URLSearchParams();
  if (params.page) query.set('page', params.page);
  if (params.limit) query.set('limit', params.limit);
  if (params.search) query.set('search', params.search);
  if (params.language && params.language !== 'all') query.set('language', params.language);
  if (params.difficulty && params.difficulty !== 'all') query.set('difficulty', params.difficulty);
  if (params.solved && params.solved !== 'all') query.set('solved', params.solved);

  const res = await fetch(`${API_BASE}/problems?${query.toString()}`);
  if (!res.ok) throw new Error('Failed to fetch problems');
  return res.json();
}

export async function generateProblemTags({ problemIds, model }, { signal } = {}) {
  const res = await fetch(`${API_BASE}/llm/generate-tags`, {
    method: 'POST',
    signal,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ problemIds, model })
  });
  return readResponse(res, 'Failed to generate problem tags');
}

export async function fetchProblem(id) {
  const res = await fetch(`${API_BASE}/problems/${id}`);
  if (!res.ok) throw new Error(`Failed to fetch problem ${id}`);
  return res.json();
}

export async function runCode({ language, code, input, expectedOutput, timeoutMs }, { signal } = {}) {
  const res = await fetch(`${API_BASE}/run`, {
    method: 'POST',
    signal,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ language, code, input, expectedOutput, timeoutMs })
  });
  return readResponse(res, 'Run execution failed');
}

function waitForPoll(delay, signal) {
  return new Promise((resolve, reject) => {
    signal?.throwIfAborted();
    const abort = () => {
      clearTimeout(timer);
      reject(signal.reason || new DOMException('Aborted', 'AbortError'));
    };
    const timer = setTimeout(() => {
      signal?.removeEventListener('abort', abort);
      resolve();
    }, delay);
    signal?.addEventListener('abort', abort, { once: true });
  });
}

export async function submitCode({ problemId, language, code, customTestCases }, { signal, onProgress, pollIntervalMs = 500, waitTimeoutMs = 300000 } = {}) {
  const res = await fetch(`${API_BASE}/submit`, {
    method: 'POST',
    signal,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ problemId, language, code, customTestCases, async: true })
  });
  let data = await readResponse(res, 'Submission failed');
  const jobId = data.jobId;
  const deadline = Date.now() + waitTimeoutMs;
  while (data.done === false) {
    if (!jobId) throw new Error('The server did not return a submission job ID.');
    onProgress?.(data);
    if (Date.now() >= deadline) throw new Error('Still waiting for the submission. Check submission history before submitting again.');
    await waitForPoll(pollIntervalMs, signal);
    const progress = await fetch(`${API_BASE}/submission-jobs/${encodeURIComponent(jobId)}`, { signal });
    data = await readResponse(progress, 'Unable to check submission status. Check submission history before submitting again.');
  }
  if (!data.grading) throw new Error(data.error || 'The server completed the submission without a grading result.');
  return data;
}

export async function fetchSubmissions(problemId) {
  const res = await fetch(`${API_BASE}/submissions/${problemId}`);
  if (!res.ok) throw new Error('Failed to fetch submissions');
  return res.json();
}

export async function fetchDraft(problemId, language) {
  const res = await fetch(`${API_BASE}/problems/${problemId}/drafts/${encodeURIComponent(language)}`);
  return readResponse(res, 'Unable to load the saved draft. Retry before editing.');
}

export async function saveDraft(problemId, language, code, revision) {
  const body = JSON.stringify({ code, revision });
  const res = await fetch(`${API_BASE}/problems/${problemId}/drafts/${encodeURIComponent(language)}`, {
    method: 'PUT',
    keepalive: new TextEncoder().encode(body).byteLength < 60000,
    headers: { 'Content-Type': 'application/json' },
    body,
  });
  const data = await res.json().catch(() => null);
  if (!res.ok || !data?.success) {
    const error = new Error(data?.error || 'Unable to save the draft. Your edits are still in this tab.');
    error.status = res.status;
    throw error;
  }
  return data;
}

export async function fetchAllSubmissions({ page = 1, limit = 25, problemId, signal } = {}) {
  const query = new URLSearchParams({ page, limit });
  if (problemId) query.set('problemId', problemId);
  const res = await fetch(`${API_BASE}/submissions?${query}`, { signal });
  return readResponse(res, 'Unable to load submission history.');
}

export async function fetchSubmissionRecord(id, { signal } = {}) {
  const res = await fetch(`${API_BASE}/submission-records/${id}`, { signal });
  return readResponse(res, 'Unable to load this submission.');
}

export async function exportSubmissions() {
  const res = await fetch(`${API_BASE}/submissions/export.zip`);
  if (!res.ok) {
    const data = await res.json().catch(() => null);
    throw new Error(data?.error || 'Unable to export submissions. Please retry.');
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = 'codejudge-submissions.zip';
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 30000);
}

export async function translateProblem({ problemId, targetLanguage, title, problem_statements, model }) {
  const res = await fetch(`${API_BASE}/translate-problem`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ problemId, targetLanguage, title, problem_statements, model })
  });
  return readResponse(res, 'Translation failed');
}

export async function fetchHint({ problemId, hintLevel = 1, model }) {
  const res = await fetch(`${API_BASE}/llm/hint`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ problemId, hintLevel, model })
  });
  return readResponse(res, 'Failed to fetch hint');
}

export async function fetchRecommendations({ problemId, model }) {
  const res = await fetch(`${API_BASE}/llm/recommendations`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ problemId, model })
  });
  return readResponse(res, 'Failed to fetch recommendations');
}

export async function generateSimilarProblem({ problemId, difficulty, autoSave = true, model }) {
  const res = await fetch(`${API_BASE}/llm/generate-problem`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ problemId, difficulty, autoSave, model })
  });
  return readResponse(res, 'Failed to generate problem');
}

export async function generateTestCases({ problemId, model }) {
  const res = await fetch(`${API_BASE}/llm/generate-testcases`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ problemId, model })
  });
  return readResponse(res, 'Failed to generate test cases by limitations');
}

export async function chatWithAI({ message, messages, problemId, code, language, sessionId, model }) {
  const res = await fetch(`${API_BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, messages, problemId, code, language, sessionId, model })
  });
  return readResponse(res, 'Chat request failed');
}

export async function fetchChatHistory(sessionId = 'default') {
  const res = await fetch(`${API_BASE}/chat/history?sessionId=${encodeURIComponent(sessionId)}`);
  if (!res.ok) throw new Error('Failed to fetch chat history');
  return res.json();
}

async function readUploadResponse(res) {
  const data = await res.json().catch(() => null);
  if (!res.ok || !data?.success) {
    const fallback = res.status === 413
      ? 'This dataset exceeds the server upload size limit. Split it into smaller JSON files and try again.'
      : 'Failed to upload problems. Please try again.';
    throw new Error(data?.error || fallback);
  }
  return data;
}

export async function uploadProblemsFile(file) {
  const formData = new FormData();
  formData.append('file', file);
  const res = await fetch(`${API_BASE}/problems/upload`, {
    method: 'POST',
    body: formData
  });
  return readUploadResponse(res);
}

export async function uploadProblemsJson(jsonObj) {
  const res = await fetch(`${API_BASE}/problems/upload`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(jsonObj)
  });
  return readUploadResponse(res);
}

export async function saveProblem(problemData) {
  const res = await fetch(`${API_BASE}/problems`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(problemData)
  });
  return readResponse(res, 'Failed to create problem');
}

export async function importStories(payload) {
  const res = await fetch(`${API_BASE}/issues/import-stories`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  return readResponse(res, 'Failed to import stories');
}

export async function submitCodingResult(issueId, payload) {
  const res = await fetch(`${API_BASE}/issues/${encodeURIComponent(issueId)}/submission`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  return readResponse(res, 'Failed to record coding submission');
}

export async function aiGenerateStory(payload) {
  const res = await fetch(`${API_BASE}/ai/generate-story`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  return readResponse(res, 'Failed to generate story with AI');
}
