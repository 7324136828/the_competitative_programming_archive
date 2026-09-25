import { getModelOverride } from '../utils/modelPreference.js';

const API_BASE = '/api';

// Attach the per-browser model override to AI request bodies when set.
function withModel<T extends object>(data: T): T {
  const model = getModelOverride();
  return model ? { ...data, model } : data;
}

export function getActiveUserId(): string {
  return localStorage.getItem('jira_active_user_id') || '';
}

export function setActiveUserId(id: string) {
  localStorage.setItem('jira_active_user_id', id);
}

export async function apiRequest<T = any>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers || {});
  headers.set('x-user-id', getActiveUserId());

  if (!(options.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }

  const res = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers,
  });

  if (!res.ok) {
    let errorMsg = `HTTP ${res.status}: ${res.statusText}`;
    try {
      const data = await res.json();
      if (data.error) errorMsg = data.error;
    } catch (e) {}
    throw new Error(errorMsg);
  }

  return res.json();
}

// Typed API helper methods
export const api = {
  // Projects
  getProjects: () => apiRequest('/projects'),
  getProject: (id: string) => apiRequest(`/projects/${id}`),
  createProject: (data: any) => apiRequest('/projects', { method: 'POST', body: JSON.stringify(data) }),

  // Issues
  getIssues: (params: Record<string, any> = {}) => {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') query.append(k, String(v));
    });
    return apiRequest(`/issues?${query.toString()}`);
  },
  getIssue: (id: string) => apiRequest(`/issues/${id}`),
  getStoryByProblem: (problemId: number) => apiRequest(`/issues/by-problem/${problemId}`),
  ensureStoryForProblem: (problemId: number, projectId?: string) =>
    apiRequest(`/issues/from-problem/${problemId}`, {
      method: 'POST',
      body: JSON.stringify({ projectId }),
    }),
  createIssue: (data: any) => apiRequest('/issues', { method: 'POST', body: JSON.stringify(data) }),
  updateIssue: (id: string, data: any) => apiRequest(`/issues/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
  deleteIssue: (id: string) => apiRequest(`/issues/${id}`, { method: 'DELETE' }),

  assignIssue: (id: string, assigneeId: string | null) =>
    apiRequest(`/issues/${id}/assign`, { method: 'POST', body: JSON.stringify({ assigneeId }) }),

  createSubtask: (parentId: string, data: any) =>
    apiRequest(`/issues/${parentId}/subtasks`, { method: 'POST', body: JSON.stringify(data) }),

  linkIssues: (id: string, targetId: string, linkType: string) =>
    apiRequest(`/issues/${id}/links`, { method: 'POST', body: JSON.stringify({ targetId, linkType }) }),
  deleteLink: (linkId: string) => apiRequest(`/issues/links/${linkId}`, { method: 'DELETE' }),

  reorderRank: (id: string, targetRank: number) =>
    apiRequest(`/issues/${id}/rank`, { method: 'POST', body: JSON.stringify({ targetRank }) }),

  setStoryPoints: (id: string, points: number | null) =>
    apiRequest(`/issues/${id}/points`, { method: 'POST', body: JSON.stringify({ points }) }),

  setSprint: (id: string, sprintId: string | null) =>
    apiRequest(`/issues/${id}/sprint`, { method: 'POST', body: JSON.stringify({ sprintId }) }),

  updateStatus: (id: string, status: string) =>
    apiRequest(`/issues/${id}/status`, { method: 'POST', body: JSON.stringify({ status }) }),

  getComments: (id: string) => apiRequest(`/issues/${id}/comments`),
  addComment: (id: string, body: string) =>
    apiRequest(`/issues/${id}/comments`, { method: 'POST', body: JSON.stringify({ body }) }),
  deleteComment: (commentId: string) => apiRequest(`/issues/comments/${commentId}`, { method: 'DELETE' }),

  toggleWatch: (id: string) => apiRequest(`/issues/${id}/watch`, { method: 'POST' }),

  getWorklogs: (id: string) => apiRequest(`/issues/${id}/worklogs`),
  logWork: (id: string, data: any) =>
    apiRequest(`/issues/${id}/worklogs`, { method: 'POST', body: JSON.stringify(data) }),

  updateDates: (id: string, startDate: string | null, dueDate: string | null) =>
    apiRequest(`/issues/${id}/dates`, { method: 'POST', body: JSON.stringify({ startDate, dueDate }) }),

  setVersion: (id: string, versionId: string | null) =>
    apiRequest(`/issues/${id}/version`, { method: 'POST', body: JSON.stringify({ versionId }) }),

  setCustomField: (id: string, fieldId: string, value: string) =>
    apiRequest(`/issues/${id}/custom-fields`, { method: 'POST', body: JSON.stringify({ fieldId, value }) }),

  getCrossTeamDependencies: () => apiRequest('/issues/cross-team/dependencies'),

  // Sprints
  getSprints: (projectId: string) => apiRequest(`/sprints/projects/${projectId}`),
  createSprint: (projectId: string, data: any) =>
    apiRequest(`/sprints/projects/${projectId}`, { method: 'POST', body: JSON.stringify(data) }),
  startSprint: (id: string, data?: any) =>
    apiRequest(`/sprints/${id}/start`, { method: 'POST', body: JSON.stringify(data || {}) }),
  completeSprint: (id: string, data?: any) =>
    apiRequest(`/sprints/${id}/complete`, { method: 'POST', body: JSON.stringify(data || {}) }),
  getBurndown: (sprintId: string) => apiRequest(`/sprints/${sprintId}/burndown`),

  // Workflows
  getWorkflow: (projectId: string) => apiRequest(`/workflows/project/${projectId}`),
  getAllowedTransitions: (projectId: string, status: string) =>
    apiRequest(`/workflows/project/${projectId}/allowed-transitions?status=${encodeURIComponent(status)}`),
  addTransition: (data: any) => apiRequest('/workflows/transitions', { method: 'POST', body: JSON.stringify(data) }),
  deleteTransition: (id: string) => apiRequest(`/workflows/transitions/${id}`, { method: 'DELETE' }),
  addStatus: (data: any) => apiRequest('/workflows/statuses', { method: 'POST', body: JSON.stringify(data) }),

  // Automation
  getAutomationRules: (projectId?: string) => apiRequest(`/automation/rules?projectId=${projectId || ''}`),
  createAutomationRule: (data: any) => apiRequest('/automation/rules', { method: 'POST', body: JSON.stringify(data) }),
  toggleAutomationRule: (id: string) => apiRequest(`/automation/rules/${id}/toggle`, { method: 'PATCH' }),
  deleteAutomationRule: (id: string) => apiRequest(`/automation/rules/${id}`, { method: 'DELETE' }),
  getAutomationLogs: (projectId?: string) => apiRequest(`/automation/logs?projectId=${projectId || ''}`),

  // Dev tools
  getPullRequests: (issueId: string) => apiRequest(`/dev/issues/${issueId}/prs`),
  linkPullRequest: (issueId: string, data: any) =>
    apiRequest(`/dev/issues/${issueId}/prs`, { method: 'POST', body: JSON.stringify(data) }),
  simulatePullRequest: (data: { issueKey: string; title?: string; branch?: string }) =>
    apiRequest('/dev/simulate-pr', { method: 'POST', body: JSON.stringify(data) }),

  // Saved Filters
  getFilters: () => apiRequest('/filters'),
  saveFilter: (data: any) => apiRequest('/filters', { method: 'POST', body: JSON.stringify(data) }),
  deleteFilter: (id: string) => apiRequest(`/filters/${id}`, { method: 'DELETE' }),

  // Dashboard
  getDashboard: (projectId: string) => apiRequest(`/dashboard/projects/${projectId}`),

  // Versions
  getVersions: (projectId: string) => apiRequest(`/versions/projects/${projectId}`),
  createVersion: (projectId: string, data: any) =>
    apiRequest(`/versions/projects/${projectId}`, { method: 'POST', body: JSON.stringify(data) }),
  updateVersionStatus: (id: string, status: string) =>
    apiRequest(`/versions/${id}/status`, { method: 'PATCH', body: JSON.stringify({ status }) }),

  // Custom Fields
  getCustomFields: (projectId: string) => apiRequest(`/custom-fields/projects/${projectId}`),
  createCustomField: (projectId: string, data: any) =>
    apiRequest(`/custom-fields/projects/${projectId}`, { method: 'POST', body: JSON.stringify(data) }),

  // Attachments
  getAttachments: (issueId: string) => apiRequest(`/attachments/issues/${issueId}`),
  uploadAttachment: (issueId: string, file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    return apiRequest(`/attachments/issues/${issueId}`, { method: 'POST', body: formData });
  },
  deleteAttachment: (id: string) => apiRequest(`/attachments/${id}`, { method: 'DELETE' }),

  // Metrics
  getIssueMetrics: (issueIdOrKey: string) => apiRequest(`/metrics/issues/${issueIdOrKey}`),
  getSprintMetrics: (sprintId: string) => apiRequest(`/metrics/sprints/${sprintId}`),
  getProjectMetrics: (projectId: string) => apiRequest(`/metrics/projects/${projectId}`),
  getProjectIssueMetrics: (projectId: string) => apiRequest(`/metrics/projects/${projectId}/issues`),

  // AI
  getAiStatus: () => apiRequest('/ai/status'),
  getAiSettings: () => apiRequest('/ai/settings'),
  updateAiSettings: (model: string | null) =>
    apiRequest('/ai/settings', { method: 'PUT', body: JSON.stringify({ model }) }),
  aiDraftTickets: (data: { text: string; projectId: string; maxTickets?: number }) =>
    apiRequest('/ai/tickets/draft', { method: 'POST', body: JSON.stringify(withModel(data)) }),
  aiCreateTickets: (projectId: string, tickets: any[]) =>
    apiRequest('/ai/tickets/create', { method: 'POST', body: JSON.stringify({ projectId, tickets }) }),
  aiRecommend: (data: { query: string; projectId?: string | null; limit?: number; includeDone?: boolean; useAi?: boolean }) =>
    apiRequest('/ai/recommend', { method: 'POST', body: JSON.stringify(withModel(data)) }),
  aiAssistant: (data: { messages: Array<{ role: string; content: string }>; projectId?: string | null }) =>
    apiRequest('/ai/assistant', { method: 'POST', body: JSON.stringify(withModel(data)) }),
  aiIntake: (data: any) =>
    apiRequest('/ai/intake', { method: 'POST', body: JSON.stringify(withModel(data)) }),
  aiRegisterTools: () => apiRequest('/ai/connector/register-tools', { method: 'POST', body: '{}' }),
  getAiRequests: (limit = 20) => apiRequest(`/ai/requests?limit=${limit}`),

  // Activity (client-side beacons for UI steps; server middleware logs API calls)
  logActivity: (action: string, detail?: any) =>
    apiRequest('/activity', { method: 'POST', body: JSON.stringify({ action, detail }) }).catch(() => {}),
  getActivity: (params: Record<string, any> = {}) => {
    const query = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '') query.append(k, String(v));
    });
    return apiRequest(`/activity?${query.toString()}`);
  },

  // Users & Notifications
  getUsers: () => apiRequest('/users'),
  createUser: (data: { name: string; email: string; role: string }) =>
    apiRequest('/users', { method: 'POST', body: JSON.stringify(data) }),
  getNotifications: () => apiRequest('/notifications'),
  markNotificationRead: (id: string) => apiRequest(`/notifications/${id}/read`, { method: 'POST' }),

  // System administration
  purgeDatabase: (confirmation: string) =>
    apiRequest('/admin/purge', { method: 'POST', body: JSON.stringify({ confirmation }) }),

  // Stories & CP integration
  importStories: (data: any) =>
    apiRequest('/issues/import-stories', { method: 'POST', body: JSON.stringify(data) }),
  submitCodingResult: (issueId: string, data: { verdict: string; test_results?: any }) =>
    apiRequest(`/issues/${issueId}/submission`, { method: 'POST', body: JSON.stringify(data) }),
  aiGenerateStory: (data: { story_type: string; prompt: string; difficulty?: string; title?: string; projectId?: string }) =>
    apiRequest('/ai/generate-story', { method: 'POST', body: JSON.stringify(withModel(data)) }),
};

