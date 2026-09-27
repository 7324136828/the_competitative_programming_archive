/**
 * API client for Study Sets, Content, QA Sessions, Podcasts, and Jira associations.
 */

import type {
  UploadedWorkspace,
  UploadProgress,
  WorkspaceStatus,
} from "../types";

export interface QASessionResponse {
  id: string;
  question: string;
  answer: string;
}

export interface QASession {
  id: string;
  qaFile: string;
  title: string;
  status: "in_progress" | "completed";
  currentQuestion: number;
  createdAt: string;
  updatedAt: string;
  completedAt: string | null;
  responses: QASessionResponse[];
}

export interface QuizAttemptResponse {
  question: string;
  selectedAnswer: string | null;
  correctAnswer: string;
  correct: boolean;
  explanation: string;
}

export interface QuizAttempt {
  id: string;
  quizFile: string;
  title: string;
  responses: QuizAttemptResponse[];
  score: number;
  total: number;
  completedAt: string;
}

export interface FlashcardProgress {
  flashcardFile: string;
  cardKey: string;
  remembered: boolean;
  updatedAt: string;
}

export interface PodcastGenerationResponse {
  job_id: string;
  status: "starting" | "running" | "completed" | "failed";
  audio_url?: string;
  error?: string;
}

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const payload = (await response.json()) as { error?: string; detail?: string };
      if (payload.detail) message = payload.detail;
      else if (payload.error) message = payload.error;
    } catch {
      // Keep status-based message
    }
    throw new Error(message);
  }
  return (await response.json()) as T;
}

// --------------------------------------------------------------------------
// Workspace & Study Sets
// --------------------------------------------------------------------------

export function getWorkspaceStatus(): Promise<WorkspaceStatus> {
  return requestJson<WorkspaceStatus>("/api/workspace");
}

export function activateWorkspace(workspaceId: string): Promise<WorkspaceStatus> {
  return requestJson<WorkspaceStatus>("/api/workspace/activate", {
    method: "POST",
    body: JSON.stringify({ workspace: workspaceId }),
  });
}

export function listWorkspaceUploads(): Promise<{ uploads: UploadedWorkspace[] }> {
  return requestJson<{ uploads: UploadedWorkspace[] }>("/api/workspace/uploads");
}

export function getUploadProgress(uploadId: string): Promise<UploadProgress> {
  return requestJson<UploadProgress>(`/api/workspace/uploads/progress/${encodeURIComponent(uploadId)}`);
}

export function loadUploadedWorkspace(
  uploadId: string,
  workspaceKey?: string,
): Promise<WorkspaceStatus> {
  return requestJson<WorkspaceStatus>("/api/workspace/load", {
    method: "POST",
    body: JSON.stringify({ uploadId, workspaceKey }),
  });
}

export function deleteStudySet(
  workspaceId: string,
): Promise<WorkspaceStatus & { deleted: { id: string } }> {
  return requestJson<WorkspaceStatus & { deleted: { id: string } }>(
    `/api/workspace/study-sets/${encodeURIComponent(workspaceId)}`,
    { method: "DELETE" },
  );
}

export function deleteStudyLibrary(
  uploadId: string,
): Promise<WorkspaceStatus & { deleted: { id: string; workspaceIds: string[] } }> {
  return requestJson<WorkspaceStatus & { deleted: { id: string; workspaceIds: string[] } }>(
    `/api/workspace/uploads/${encodeURIComponent(uploadId)}`,
    { method: "DELETE" },
  );
}

// --------------------------------------------------------------------------
// Jira Story Associations
// --------------------------------------------------------------------------

export function associateStory(
  workspaceId: string,
  issueId: string,
): Promise<{ success: boolean; workspaceId: string; storyId: string }> {
  return requestJson("/api/workspace/associate-story", {
    method: "POST",
    body: JSON.stringify({ workspaceId, issueId }),
  });
}
export const associateStoryWithStudySet = associateStory;

export function createStoryForStudySet(
  workspaceId: string,
  summary?: string,
  projectId?: string,
): Promise<{ success: boolean; issue: any }> {
  return requestJson("/api/workspace/create-story", {
    method: "POST",
    body: JSON.stringify({ workspaceId, summary, projectId }),
  });
}

export function unlinkStory(
  workspaceId: string,
): Promise<{ success: boolean; workspaceId: string }> {
  return requestJson("/api/workspace/unlink-story", {
    method: "POST",
    body: JSON.stringify({ workspaceId }),
  });
}

// --------------------------------------------------------------------------
// Free-text Q&A Sessions
// --------------------------------------------------------------------------

export function createQASession(
  qaFile: string,
  title: string,
  questions: { id: string; question: string }[],
): Promise<QASession> {
  return requestJson<QASession>("/api/qa/sessions", {
    method: "POST",
    body: JSON.stringify({ qaFile, title, questions }),
  });
}

export function getQASession(sessionId: string): Promise<QASession> {
  return requestJson<QASession>(`/api/qa/sessions/${encodeURIComponent(sessionId)}`);
}

export function updateQASession(
  sessionId: string,
  answers: string[],
  currentQuestion: number,
  completed: boolean,
): Promise<QASession> {
  return requestJson<QASession>(`/api/qa/sessions/${encodeURIComponent(sessionId)}`, {
    method: "PUT",
    body: JSON.stringify({ answers, currentQuestion, completed }),
  });
}

export function listQASessions(qaFile?: string): Promise<{ sessions: QASession[] }> {
  const query = qaFile ? `?qa_file=${encodeURIComponent(qaFile)}` : "";
  return requestJson<{ sessions: QASession[] }>(`/api/qa/sessions${query}`);
}

export function qaDownloadUrl(sessionId: string): string {
  return `/api/qa/sessions/${encodeURIComponent(sessionId)}/download`;
}
export const downloadQASessionUrl = qaDownloadUrl;

// --------------------------------------------------------------------------
// Quiz attempt history
// --------------------------------------------------------------------------

export function createQuizAttempt(
  quizFile: string,
  title: string,
  responses: QuizAttemptResponse[],
  score: number,
  total: number,
): Promise<QuizAttempt> {
  return requestJson<QuizAttempt>("/api/quiz/attempts", {
    method: "POST",
    body: JSON.stringify({ quizFile, title, responses, score, total }),
  });
}

export function listQuizAttempts(quizFile?: string): Promise<{ attempts: QuizAttempt[] }> {
  const query = quizFile ? `?quiz_file=${encodeURIComponent(quizFile)}` : "";
  return requestJson<{ attempts: QuizAttempt[] }>(`/api/quiz/attempts${query}`);
}

// --------------------------------------------------------------------------
// Flashcard Audio
// --------------------------------------------------------------------------

export function generateFlashcardAudio(
  items: { text: string; voice?: string }[],
): Promise<{ audios: Record<string, string> }> {
  return requestJson<{ audios: Record<string, string> }>("/api/flashcards/audio", {
    method: "POST",
    body: JSON.stringify({ items }),
  });
}

export function listFlashcardProgress(
  flashcardFile?: string,
): Promise<{ items: FlashcardProgress[] }> {
  const query = flashcardFile ? `?flashcard_file=${encodeURIComponent(flashcardFile)}` : "";
  return requestJson<{ items: FlashcardProgress[] }>(`/api/flashcards/progress${query}`);
}

export function saveFlashcardProgress(
  flashcardFile: string,
  cardKey: string,
  remembered: boolean,
): Promise<FlashcardProgress> {
  return requestJson<FlashcardProgress>("/api/flashcards/progress", {
    method: "PUT",
    body: JSON.stringify({ flashcardFile, cardKey, remembered }),
  });
}

// --------------------------------------------------------------------------
// Podcast Generation
// --------------------------------------------------------------------------

export function generatePodcast(
  podcastFile?: string,
  options?: { voiceA?: string; voiceB?: string; subject?: string | null },
): Promise<PodcastGenerationResponse> {
  const { subject, ...voices } = options ?? {};
  return requestJson<PodcastGenerationResponse>("/api/generate_podcast", {
    method: "POST",
    body: JSON.stringify({
      podcast_file: podcastFile || "",
      ...voices,
      ...(subject !== undefined ? { podcast_subject: subject ?? "" } : {}),
    }),
  });
}

export function getPodcastStatus(jobId: string): Promise<PodcastGenerationResponse> {
  return requestJson<PodcastGenerationResponse>(`/api/generate_podcast?job_id=${encodeURIComponent(jobId)}`);
}

export function getPodcastLogs(jobId: string): Promise<{ logs: string[] }> {
  return requestJson<{ logs: string[] }>(`/api/generate_podcast/logs?job_id=${encodeURIComponent(jobId)}`);
}
