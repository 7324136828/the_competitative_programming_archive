const API_BASE = '/api';

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

  const res = await fetch(`${API_BASE}/problems?${query.toString()}`);
  if (!res.ok) throw new Error('Failed to fetch problems');
  return res.json();
}

export async function fetchProblem(id) {
  const res = await fetch(`${API_BASE}/problems/${id}`);
  if (!res.ok) throw new Error(`Failed to fetch problem ${id}`);
  return res.json();
}

export async function runCode({ language, code, input, expectedOutput, timeoutMs }) {
  const res = await fetch(`${API_BASE}/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ language, code, input, expectedOutput, timeoutMs })
  });
  if (!res.ok) throw new Error('Run execution failed');
  return res.json();
}

export async function submitCode({ problemId, language, code, customTestCases }) {
  const res = await fetch(`${API_BASE}/submit`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ problemId, language, code, customTestCases })
  });
  if (!res.ok) throw new Error('Submission failed');
  return res.json();
}

export async function fetchSubmissions(problemId) {
  const res = await fetch(`${API_BASE}/submissions/${problemId}`);
  if (!res.ok) throw new Error('Failed to fetch submissions');
  return res.json();
}

export async function translateProblem({ problemId, targetLanguage, title, problem_statements }) {
  const res = await fetch(`${API_BASE}/translate-problem`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ problemId, targetLanguage, title, problem_statements })
  });
  if (!res.ok) throw new Error('Translation failed');
  return res.json();
}

export async function fetchHint({ problemId, hintLevel = 1 }) {
  const res = await fetch(`${API_BASE}/llm/hint`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ problemId, hintLevel })
  });
  if (!res.ok) throw new Error('Failed to fetch hint');
  return res.json();
}

export async function fetchRecommendations({ problemId }) {
  const res = await fetch(`${API_BASE}/llm/recommendations`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ problemId })
  });
  if (!res.ok) throw new Error('Failed to fetch recommendations');
  return res.json();
}

export async function generateSimilarProblem({ problemId, difficulty, autoSave = true }) {
  const res = await fetch(`${API_BASE}/llm/generate-problem`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ problemId, difficulty, autoSave })
  });
  if (!res.ok) throw new Error('Failed to generate problem');
  return res.json();
}

export async function generateTestCases({ problemId }) {
  const res = await fetch(`${API_BASE}/llm/generate-testcases`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ problemId })
  });
  if (!res.ok) throw new Error('Failed to generate test cases by limitations');
  return res.json();
}

export async function chatWithAI({ message, messages, problemId, code, language, sessionId }) {
  const res = await fetch(`${API_BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, messages, problemId, code, language, sessionId })
  });
  if (!res.ok) throw new Error('Chat request failed');
  return res.json();
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
  if (!res.ok) throw new Error('Failed to create problem');
  return res.json();
}

