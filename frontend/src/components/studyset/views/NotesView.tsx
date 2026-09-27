import { useCallback, useEffect, useRef, useState } from "react";
import { FileText } from "lucide-react";
import { getStudyNote, saveStudyNote } from "../studyPersistenceApi";

type SaveState = "idle" | "loading" | "saving" | "saved" | "error";

interface NotesViewProps {
  workspaceId: string | null;
}

export function NotesView({ workspaceId }: NotesViewProps) {
  const [text, setText] = useState("");
  const [saveState, setSaveState] = useState<SaveState>("idle");
  const [error, setError] = useState("");
  const [ready, setReady] = useState(false);
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
      </div>
    </section>
  );
}
