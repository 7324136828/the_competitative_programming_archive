import type { StudyNote, StudyNoteAttachment, UploadProgress, WorkspaceStatus } from "./types";

async function errorMessage(response: Response): Promise<string> {
  let message = `Request failed (${response.status})`;
  try {
    const payload = (await response.json()) as { error?: string; detail?: string };
    if (payload.detail) message = payload.detail;
    else if (payload.error) message = payload.error;
  } catch {
    // Keep status-based message.
  }
  return message;
}

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    throw new Error(await errorMessage(response));
  }
  return (await response.json()) as T;
}

function getUploadProgress(uploadId: string): Promise<UploadProgress> {
  return requestJson<UploadProgress>(
    `/api/workspace/uploads/progress/${encodeURIComponent(uploadId)}`,
  );
}

export async function uploadWorkspaceFile(
  file: File,
  uploadId: string,
  onProgress: (progress: UploadProgress) => void,
): Promise<WorkspaceStatus> {
  const poll = window.setInterval(() => {
    void getUploadProgress(uploadId).then(onProgress).catch(() => undefined);
  }, 250);
  try {
    const response = await fetch("/api/workspace/upload", {
      method: "POST",
      headers: {
        "Content-Type": "application/zip",
        "X-File-Name": encodeURIComponent(file.name),
        "X-Upload-ID": uploadId,
        "X-File-Size": String(file.size),
      },
      body: file,
    });
    if (!response.ok) {
      let message = `Upload failed (${response.status})`;
      try {
        const payload = (await response.json()) as { error?: string; detail?: string };
        if (payload.detail) message = payload.detail;
        else if (payload.error) message = payload.error;
      } catch {
        // Keep status-based message.
      }
      throw new Error(message);
    }
    return (await response.json()) as WorkspaceStatus;
  } finally {
    window.clearInterval(poll);
  }
}

export function getStudyNote(workspaceId: string): Promise<StudyNote> {
  return requestJson<StudyNote>(
    `/api/workspace/study-sets/${encodeURIComponent(workspaceId)}/note`,
  );
}

export function saveStudyNote(workspaceId: string, text: string): Promise<StudyNote> {
  return requestJson<StudyNote>(
    `/api/workspace/study-sets/${encodeURIComponent(workspaceId)}/note`,
    { method: "PUT", body: JSON.stringify({ text }) },
  );
}

const noteAttachmentsUrl = (workspaceId: string) =>
  `/api/workspace/study-sets/${encodeURIComponent(workspaceId)}/note/attachments`;

export async function listStudyNoteAttachments(workspaceId: string): Promise<StudyNoteAttachment[]> {
  const result = await requestJson<{ attachments: StudyNoteAttachment[] }>(noteAttachmentsUrl(workspaceId));
  return result.attachments;
}

export async function uploadStudyNoteAttachment(workspaceId: string, file: File): Promise<StudyNoteAttachment> {
  const response = await fetch(noteAttachmentsUrl(workspaceId), {
    method: "POST",
    headers: {
      "Content-Type": file.type || "application/octet-stream",
      "X-File-Name": encodeURIComponent(file.name),
    },
    body: file,
  });
  if (!response.ok) throw new Error(await errorMessage(response));
  return (await response.json()) as StudyNoteAttachment;
}

export function studyNoteAttachmentUrl(workspaceId: string, attachmentId: string): string {
  return `${noteAttachmentsUrl(workspaceId)}/${encodeURIComponent(attachmentId)}`;
}

export async function deleteStudyNoteAttachment(workspaceId: string, attachmentId: string): Promise<void> {
  const response = await fetch(studyNoteAttachmentUrl(workspaceId, attachmentId), { method: "DELETE" });
  if (!response.ok) throw new Error(await errorMessage(response));
}
