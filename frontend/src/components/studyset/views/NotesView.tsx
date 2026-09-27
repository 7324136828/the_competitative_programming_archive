import { useCallback, useEffect, useRef, useState } from "react";
import { Download, FileText, Paperclip, Trash2 } from "lucide-react";
import {
  deleteStudyNoteAttachment,
  getStudyNote,
  listStudyNoteAttachments,
  saveStudyNote,
  studyNoteAttachmentUrl,
  uploadStudyNoteAttachment,
} from "../studyPersistenceApi";
import type { StudyNoteAttachment } from "../types";

type SaveState = "idle" | "loading" | "saving" | "saved" | "error";

interface NotesViewProps {
  workspaceId: string | null;
}

export function NotesView({ workspaceId }: NotesViewProps) {
  const [text, setText] = useState("");
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [error, setError] = useState("");
  const [ready, setReady] = useState(false);
  const [attachments, setAttachments] = useState<StudyNoteAttachment[]>([]);
  const [attachmentLoading, setAttachmentLoading] = useState(false);
  const [attachmentBusy, setAttachmentBusy] = useState(false);
  const [attachmentError, setAttachmentError] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);
  const currentWorkspace = useRef(workspaceId);
  currentWorkspace.current = workspaceId;
  const timer = useRef<number | null>(null);
  const saveQueue = useRef<Promise<void>>(Promise.resolve());
  const latestText = useRef("");
  const dirty = useRef(false);

  useEffect(() => {
    let cancelled = false;
    if (timer.current !== null) window.clearTimeout(timer.current);
    setText("");
    latestText.current = "";
    dirty.current = false;
    setError("");
    setReady(false);
    if (!workspaceId) {
      setSaveState("idle");
      return () => { cancelled = true; };
    }

    setSaveState("loading");
    void getStudyNote(workspaceId)
      .then((note) => {
        if (cancelled) return;
        setText(note.text);
        latestText.current = note.text;
        setReady(true);
        setSaveState("saved");
      })
      .catch((reason: Error) => {
        if (cancelled) return;
        setError(reason.message);
        setSaveState("error");
      });
    return () => {
      cancelled = true;
      if (timer.current !== null) window.clearTimeout(timer.current);
      if (workspaceId && dirty.current) {
        const finalText = latestText.current;
        saveQueue.current = saveQueue.current
          .catch(() => undefined)
          .then(() => saveStudyNote(workspaceId, finalText))
          .then(() => undefined);
      }
    };
  }, [workspaceId]);

  useEffect(() => {
    let cancelled = false;
    setAttachments([]);
    setAttachmentError("");
    setAttachmentBusy(false);
    setAttachmentLoading(Boolean(workspaceId));
    if (workspaceId) {
      void listStudyNoteAttachments(workspaceId)
        .then((files) => { if (!cancelled) setAttachments(files); })
        .catch((reason: Error) => { if (!cancelled) setAttachmentError(reason.message); })
        .finally(() => { if (!cancelled) setAttachmentLoading(false); });
    }
    return () => { cancelled = true; };
  }, [workspaceId]);

  const persist = useCallback((targetWorkspaceId: string, value: string) => {
    setSaveState("saving");
    setError("");
    const operation = saveQueue.current
      .catch(() => undefined)
      .then(async () => {
        try {
          await saveStudyNote(targetWorkspaceId, value);
          if (workspaceId === targetWorkspaceId && latestText.current === value) {
            dirty.current = false;
            setSaveState("saved");
          }
        } catch (reason) {
          if (workspaceId === targetWorkspaceId) {
            setError((reason as Error).message);
            setSaveState("error");
          }
          throw reason;
        }
      });
    saveQueue.current = operation;
    return operation;
  }, [workspaceId]);

  const scheduleSave = (value: string) => {
    if (!workspaceId || !ready) return;
    if (timer.current !== null) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      timer.current = null;
      void persist(workspaceId, value).catch(() => undefined);
    }, 650);
  };

  const flushSave = () => {
    if (!workspaceId || !ready || timer.current === null) return;
    window.clearTimeout(timer.current);
    timer.current = null;
    void persist(workspaceId, latestText.current).catch(() => undefined);
  };

  const handleUpload = async (files: FileList | null) => {
    if (!workspaceId || !files?.length) return;
    const targetWorkspaceId = workspaceId;
    setAttachmentBusy(true);
    setAttachmentError("");
    try {
      for (const file of Array.from(files)) {
        if (file.size > 20 * 1024 * 1024) throw new Error(`${file.name} exceeds the 20 MB limit.`);
        const attachment = await uploadStudyNoteAttachment(targetWorkspaceId, file);
        if (currentWorkspace.current === targetWorkspaceId) {
          setAttachments((current) => [attachment, ...current]);
        }
      }
    } catch (reason) {
      if (currentWorkspace.current === targetWorkspaceId) setAttachmentError((reason as Error).message);
    } finally {
      if (fileInput.current) fileInput.current.value = "";
      if (currentWorkspace.current === targetWorkspaceId) setAttachmentBusy(false);
    }
  };

  const handleDelete = async (attachment: StudyNoteAttachment) => {
    if (!workspaceId || !window.confirm(`Remove ${attachment.filename} from this note?`)) return;
    const targetWorkspaceId = workspaceId;
    setAttachmentBusy(true);
    setAttachmentError("");
    try {
      await deleteStudyNoteAttachment(targetWorkspaceId, attachment.id);
      if (currentWorkspace.current === targetWorkspaceId) {
        setAttachments((current) => current.filter((file) => file.id !== attachment.id));
      }
    } catch (reason) {
      if (currentWorkspace.current === targetWorkspaceId) setAttachmentError((reason as Error).message);
    } finally {
      if (currentWorkspace.current === targetWorkspaceId) setAttachmentBusy(false);
    }
  };

  if (!workspaceId) {
    return (
      <div className="flex-1 flex items-center justify-center p-8 text-center text-gray-400">
        Upload or select a study set before adding notes.
      </div>
    );
  }

  return (
    <section className="flex-1 min-h-0 overflow-y-auto p-5 sm:p-8 bg-[#0f1720]">
      <div className="max-w-5xl mx-auto h-full min-h-[420px] flex flex-col gap-4">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <FileText className="w-5 h-5 text-emerald-400" />
              <h2 className="text-xl font-semibold text-white">Notes</h2>
            </div>
            <p className="mt-1 text-sm text-gray-400">Keep free-form notes for this study set. Changes save automatically.</p>
          </div>
          <span className={`text-xs shrink-0 ${saveState === "error" ? "text-rose-400" : "text-gray-400"}`}>
            {saveState === "loading" && "Loading…"}
            {saveState === "saving" && "Saving…"}
            {saveState === "saved" && "Saved"}
            {saveState === "error" && "Save failed"}
          </span>
        </div>
        {error && <p className="m-0 text-xs text-rose-400">{error}</p>}
        <textarea
          value={text}
          disabled={!ready}
          onChange={(event) => {
            const value = event.target.value;
            setText(value);
            latestText.current = value;
            dirty.current = true;
            scheduleSave(value);
          }}
          onBlur={flushSave}
          placeholder="Write your study notes here…"
          aria-label="Study set notes"
          className="flex-1 min-h-[340px] w-full resize-y rounded-xl border border-gray-700 bg-[#111827] p-4 text-[15px] leading-7 text-gray-100 placeholder:text-gray-600 shadow-inner outline-none transition focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 disabled:opacity-60"
        />
        <div className="rounded-xl border border-gray-700 bg-[#111827] p-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2 text-gray-100">
              <Paperclip className="h-4 w-4 text-emerald-400" />
              <h3 className="text-sm font-semibold">Attachments ({attachments.length})</h3>
            </div>
            <input
              ref={fileInput}
              type="file"
              multiple
              className="hidden"
              aria-label="Choose note attachments"
              onChange={(event) => { void handleUpload(event.target.files); }}
            />
            <button
              type="button"
              disabled={attachmentBusy || attachmentLoading}
              onClick={() => fileInput.current?.click()}
              className="rounded-lg bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {attachmentBusy ? "Working…" : "Attach files"}
            </button>
          </div>
          <p className="mt-1 text-xs text-gray-400">Keep resources with this study set. Up to 20 MB per file.</p>
          {attachmentError && <p role="alert" className="mt-3 text-sm text-rose-400">{attachmentError}</p>}
          {attachmentLoading && <p className="mt-3 text-sm text-gray-400">Loading attachments…</p>}
          {!attachmentLoading && attachments.length === 0 && (
            <p className="mt-3 text-sm text-gray-400">No files attached yet.</p>
          )}
          {attachments.length > 0 && (
            <ul className="mt-3 divide-y divide-gray-700">
              {attachments.map((attachment) => (
                <li key={attachment.id} className="flex items-center justify-between gap-3 py-2 text-sm">
                  <div className="min-w-0">
                    <a
                      href={studyNoteAttachmentUrl(workspaceId, attachment.id)}
                      className="block truncate text-emerald-300 hover:underline"
                      title={`Download ${attachment.filename}`}
                    >
                      {attachment.filename}
                    </a>
                    <span className="text-xs text-gray-400">{(attachment.size / 1024).toFixed(1)} KB</span>
                  </div>
                  <div className="flex shrink-0 items-center gap-1">
                    <a
                      href={studyNoteAttachmentUrl(workspaceId, attachment.id)}
                      aria-label={`Download ${attachment.filename}`}
                      title={`Download ${attachment.filename}`}
                      className="rounded p-1.5 text-gray-300 hover:bg-gray-700 hover:text-white"
                    ><Download className="h-4 w-4" /></a>
                    <button
                      type="button"
                      disabled={attachmentBusy}
                      onClick={() => { void handleDelete(attachment); }}
                      aria-label={`Remove ${attachment.filename}`}
                      title={`Remove ${attachment.filename}`}
                      className="rounded p-1.5 text-gray-300 hover:bg-gray-700 hover:text-rose-300 disabled:opacity-50"
                    ><Trash2 className="h-4 w-4" /></button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </section>
  );
}
