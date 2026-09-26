import React, { useState, useEffect, useRef } from "react";
import { X, BookOpen, Upload, CheckCircle2, ArrowRight, Link2, AlertCircle, Plus } from "lucide-react";
import { getWorkspaceStatus, listWorkspaceUploads, activateWorkspace, loadUploadedWorkspace, getUploadProgress } from "./lib/api";
import type { UploadedWorkspace, WorkspaceStatus, StudySet, WorkspaceOption, UploadProgress } from "./types";
import { AssociateStoryModal } from "./AssociateStoryModal";

interface LoadStudySetModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSelectStudySet: (studySetId: string) => void;
  onOpenStory?: (storyId: string) => void;
  projectId?: string | null;
}

export const LoadStudySetModal: React.FC<LoadStudySetModalProps> = ({
  isOpen,
  onClose,
  onSelectStudySet,
  onOpenStory,
  projectId,
}) => {
  const [workspace, setWorkspace] = useState<WorkspaceStatus | null>(null);
  const [uploads, setUploads] = useState<UploadedWorkspace[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState<UploadProgress | null>(null);
  const [associatingSet, setAssociatingSet] = useState<StudySet | WorkspaceOption | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [ws, up] = await Promise.all([getWorkspaceStatus(), listWorkspaceUploads()]);
      setWorkspace(ws);
      setUploads(up.uploads || []);
    } catch (err: any) {
      setError(err.message || "Failed to load study sets");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      loadData();
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleSelect = async (id: string, uploadId?: string, workspaceKey?: string) => {
    setError(null);
    try {
      if (uploadId && workspaceKey) {
        await loadUploadedWorkspace(uploadId, workspaceKey);
      } else {
        await activateWorkspace(id);
      }
      onSelectStudySet(id);
      onClose();
    } catch (err: any) {
      setError(err.message || "Failed to activate study set");
    }
  };

  const handleFileUpload = async (file: File) => {
    if (!file.name.toLowerCase().endsWith(".zip")) {
      setError("Please select a .zip study set archive.");
      return;
    }
    setUploading(true);
    setError(null);
    const progressId = crypto.randomUUID().replace(/-/g, "");
    setUploadProgress({
      id: progressId,
      state: "uploading",
      percent: 0,
      message: "Preparing upload",
      currentWorkspace: null,
      completedWorkspaces: 0,
      totalWorkspaces: 0,
    });

    const poll = setInterval(async () => {
      try {
        const prog = await getUploadProgress(progressId);
        setUploadProgress(prog);
      } catch {}
    }, 250);

    try {
      const res = await fetch("/api/workspace/upload", {
        method: "POST",
        headers: {
          "Content-Type": "application/zip",
          "X-File-Name": encodeURIComponent(file.name),
          "X-Upload-ID": progressId,
          "X-File-Size": String(file.size),
        },
        body: file,
      });
      if (!res.ok) {
        let msg = `Upload failed (${res.status})`;
        try {
          const body = await res.json();
          if (body.detail) msg = body.detail;
        } catch {}
        throw new Error(msg);
      }
      const data = await res.json();
      setWorkspace(data);
      await loadData();
      if (data.activeWorkspace) {
        onSelectStudySet(data.activeWorkspace);
        onClose();
      }
    } catch (err: any) {
      setError(err.message || "Failed to upload study set");
    } finally {
      clearInterval(poll);
      setUploading(false);
      setUploadProgress(null);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4">
      <div className="bg-[#1f2937] text-white border border-gray-700 rounded-xl shadow-2xl w-full max-w-2xl max-h-[85vh] flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-150">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-700 bg-[#111827]">
          <div className="flex items-center space-x-2.5">
            <BookOpen className="w-5 h-5 text-emerald-400" />
            <h3 className="font-semibold text-lg">Load Study Set</h3>
          </div>
          <div className="flex items-center space-x-2">
            <input
              ref={fileInputRef}
              type="file"
              accept=".zip"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) handleFileUpload(f);
                e.target.value = "";
              }}
            />
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading}
              className="inline-flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-emerald-600 hover:bg-emerald-500 text-white shadow-xs transition"
            >
              <Upload className="w-3.5 h-3.5" />
              <span>{uploading ? `${uploadProgress?.percent ?? 0}%` : "Upload New ZIP"}</span>
            </button>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-white p-1 rounded-lg hover:bg-gray-800 transition"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {uploading && uploadProgress && (
          <div className="px-6 py-3 bg-emerald-950/70 border-b border-emerald-800 text-xs text-emerald-100 space-y-1.5">
            <div className="flex items-center justify-between gap-4 font-semibold">
              <span>{uploadProgress.message}</span>
              <span>{uploadProgress.percent}%</span>
            </div>
            {uploadProgress.currentWorkspace && (
              <div className="flex items-center justify-between gap-4">
                <span className="truncate" title={uploadProgress.currentWorkspace}>
                  {uploadProgress.currentWorkspace}
                </span>
                {uploadProgress.totalWorkspaces ? (
                  <span className="shrink-0 text-emerald-300/80">
                    {uploadProgress.completedWorkspaces ?? 0}/{uploadProgress.totalWorkspaces} completed
                  </span>
                ) : null}
              </div>
            )}
            <div className="w-full h-1.5 bg-gray-800 rounded-full overflow-hidden">
              <div
                className="h-full bg-emerald-400 transition-all duration-200"
                style={{ width: `${uploadProgress.percent}%` }}
              />
            </div>
          </div>
        )}

        {/* Error notification */}
        {error && (
          <div className="p-3 bg-rose-950/70 border-b border-rose-800 text-rose-200 text-xs flex items-center space-x-2">
            <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {/* Content list */}
        <div className="flex-1 overflow-y-auto p-6 space-y-5">
          {/* Active Study Sets */}
          {workspace?.workspaces && workspace.workspaces.length > 0 && (
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs uppercase tracking-wider text-gray-400 font-bold">
                  Active Library Study Sets
                </span>
                <span className="text-xs text-gray-500">{workspace.workspaces.length} sets</span>
              </div>
              <div className="space-y-2">
                {workspace.workspaces.map((ws) => {
                  const isActive = ws.id === workspace.activeWorkspace;
                  const story = ws.story;
                  return (
                    <div
                      key={ws.id}
                      className={`p-3.5 rounded-xl border transition flex items-center justify-between ${
                        isActive
                          ? "bg-emerald-950/40 border-emerald-600/80 ring-1 ring-emerald-500/50"
                          : "bg-gray-800/60 border-gray-700 hover:border-gray-500 hover:bg-gray-800"
                      }`}
                    >
                      <div className="space-y-1 pr-3 flex-1 min-w-0">
                        <div className="flex items-center space-x-2">
                          <span className="font-semibold text-sm text-white truncate">{ws.name}</span>
                          {isActive && (
                            <span className="px-1.5 py-0.5 text-[10px] font-bold rounded bg-emerald-600 text-white">
                              ACTIVE
                            </span>
                          )}
                        </div>
                        {story && (
                          <div className="flex items-center space-x-1.5 text-xs text-emerald-400">
                            <Link2 className="w-3 h-3" />
                            <span>
                              {story.key}: {story.summary} ({story.status})
                            </span>
                          </div>
                        )}
                      </div>

                      <div className="flex items-center gap-2 shrink-0">
                        {story ? (
                          <button
                            type="button"
                            onClick={() => onOpenStory?.(story.id)}
                            className="px-2.5 py-1.5 rounded-lg text-xs font-semibold border border-emerald-700 text-emerald-300 hover:bg-emerald-950/70"
                            aria-label={`Open story ${story.key} for ${ws.name}`}
                          >
                            {story.key}
                          </button>
                        ) : (
                          <button
                            type="button"
                            onClick={() => setAssociatingSet(ws)}
                            className="px-2.5 py-1.5 rounded-lg text-xs font-semibold border border-gray-600 text-gray-300 hover:border-emerald-600 hover:text-emerald-300 inline-flex items-center gap-1"
                            aria-label={`Create story for ${ws.name}`}
                          >
                            <Plus className="w-3 h-3" />
                            Create story
                          </button>
                        )}
                        <button
                          type="button"
                          onClick={() => handleSelect(ws.id)}
                          className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center space-x-1 transition ${
                            isActive
                              ? "bg-emerald-600 text-white hover:bg-emerald-500"
                              : "bg-gray-700 text-gray-200 hover:bg-gray-600 hover:text-white"
                          }`}
                        >
                          <span>{isActive ? "Open" : "Select & Open"}</span>
                          <ArrowRight className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Saved Libraries */}
          {uploads.length > 0 && (
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs uppercase tracking-wider text-gray-400 font-bold">
                  All Saved Libraries ({uploads.length})
                </span>
              </div>
              <div className="space-y-4">
                {uploads.map((upload) => (
                  <div key={upload.id} className="rounded-xl border border-gray-700/80 bg-gray-900/60 p-4 space-y-2.5">
                    <div className="flex items-center justify-between text-xs text-gray-400 pb-2 border-b border-gray-800">
                      <div>
                        <strong className="text-sm text-gray-200">{upload.name}</strong>
                        <span className="ml-2 text-[11px] text-gray-500">({upload.originalFilename})</span>
                      </div>
                      <span>{upload.workspaceCount} sets</span>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                      {upload.studySets.map((sset) => {
                        const story = sset.story;
                        return (
                          <div
                            key={sset.id}
                            className="p-2.5 rounded-lg bg-gray-800/80 border border-gray-700 hover:border-emerald-500 transition group flex items-center gap-2"
                          >
                            <button
                              type="button"
                              onClick={() => handleSelect(sset.id, upload.id, sset.key)}
                              className="min-w-0 flex-1 text-left border-0 bg-transparent p-0"
                            >
                              <span className="block text-xs font-semibold text-gray-200 group-hover:text-emerald-300 truncate">
                                {sset.name}
                              </span>
                              {story && (
                                <span className="text-[10px] text-emerald-400 mt-1 flex items-center gap-1">
                                  <Link2 className="w-2.5 h-2.5" />
                                  {story.key} ({story.status})
                                </span>
                              )}
                            </button>
                            {story ? (
                              <button
                                type="button"
                                onClick={() => onOpenStory?.(story.id)}
                                className="px-2 py-1 rounded text-[10px] font-semibold border border-emerald-700 text-emerald-300"
                                aria-label={`Open story ${story.key} for ${sset.name}`}
                              >
                                Open story
                              </button>
                            ) : (
                              <button
                                type="button"
                                onClick={() => setAssociatingSet(sset)}
                                className="px-2 py-1 rounded text-[10px] font-semibold border border-gray-600 text-gray-300"
                                aria-label={`Create story for ${sset.name}`}
                              >
                                Create story
                              </button>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {loading && uploads.length === 0 && (
            <div className="py-8 text-center text-sm text-gray-400">Loading study sets…</div>
          )}

          {!loading && uploads.length === 0 && (!workspace?.workspaces || workspace.workspaces.length === 0) && (
            <div className="py-12 text-center space-y-3">
              <BookOpen className="w-10 h-10 text-gray-600 mx-auto" />
              <p className="text-sm text-gray-300 font-medium">No study sets loaded yet</p>
              <p className="text-xs text-gray-500 max-w-sm mx-auto">
                Upload a ZIP archive with your learning outputs to start studying.
              </p>
              <button
                onClick={() => fileInputRef.current?.click()}
                className="mt-2 inline-flex items-center space-x-1.5 px-4 py-2 rounded-lg text-xs font-semibold bg-emerald-600 hover:bg-emerald-500 text-white shadow-xs transition"
              >
                <Upload className="w-3.5 h-3.5" />
                <span>Upload Study Set ZIP</span>
              </button>
            </div>
          )}
        </div>
      </div>
      <AssociateStoryModal
        isOpen={associatingSet !== null}
        studySet={associatingSet}
        onClose={() => setAssociatingSet(null)}
        onSuccess={loadData}
        onOpenStory={onOpenStory}
        projectId={projectId}
      />
    </div>
  );
};
