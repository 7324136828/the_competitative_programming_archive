import React, { useState, useEffect } from "react";
import { X, Link2, Plus, ExternalLink, Unlink, CheckCircle2, AlertCircle } from "lucide-react";
import {
  associateStoryWithStudySet,
  createStoryForStudySet,
  unlinkStory,
} from "./lib/api";
import type { StudySet, WorkspaceOption } from "./types";

interface AssociateStoryModalProps {
  isOpen: boolean;
  studySet: StudySet | WorkspaceOption | null;
  onClose: () => void;
  onSuccess: () => void;
  onOpenStory?: (storyId: string) => void;
  projectId?: string | null;
}

export const AssociateStoryModal: React.FC<AssociateStoryModalProps> = ({
  isOpen,
  studySet,
  onClose,
  onSuccess,
  onOpenStory,
  projectId,
}) => {
  const [mode, setMode] = useState<"create" | "link">("create");
  const [summary, setSummary] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [existingIssues, setExistingIssues] = useState<any[]>([]);
  const [selectedIssueId, setSelectedIssueId] = useState("");
  const [loadingIssues, setLoadingIssues] = useState(false);

  useEffect(() => {
    if (isOpen && studySet) {
      setSummary(`Study: ${studySet.name}`);
      setError(null);
      if (mode === "link") {
        fetchIssues();
      }
    }
  }, [isOpen, studySet, mode]);

  const fetchIssues = async () => {
    setLoadingIssues(true);
    try {
      const res = await fetch("/api/issues?type=Story&limit=50");
      if (res.ok) {
        const data = await res.json();
        const list = Array.isArray(data) ? data : data.issues || [];
        setExistingIssues(list);
        if (list.length > 0 && !selectedIssueId) {
          setSelectedIssueId(list[0].id);
        }
      }
    } catch {
      // Fallback
    } finally {
      setLoadingIssues(false);
    }
  };

  if (!isOpen || !studySet) return null;

  const currentStory = (studySet as any).story;

  const handleCreateStory = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!summary.trim()) return;
    setLoading(true);
    setError(null);
    try {
      await createStoryForStudySet(studySet.id, summary.trim(), projectId || undefined);
      onSuccess();
      onClose();
    } catch (err: any) {
      setError(err.message || "Failed to create story");
    } finally {
      setLoading(false);
    }
  };

  const handleLinkStory = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedIssueId) return;
    setLoading(true);
    setError(null);
    try {
      await associateStoryWithStudySet(studySet.id, selectedIssueId);
      onSuccess();
      onClose();
    } catch (err: any) {
      setError(err.message || "Failed to link story");
    } finally {
      setLoading(false);
    }
  };

  const handleUnlink = async () => {
    setLoading(true);
    setError(null);
    try {
      await unlinkStory(studySet.id);
      onSuccess();
      onClose();
    } catch (err: any) {
      setError(err.message || "Failed to unlink story");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4">
      <div className="bg-[#1f2937] text-white border border-gray-700 rounded-xl shadow-2xl w-full max-w-md overflow-hidden animate-in fade-in zoom-in-95 duration-150">
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-700 bg-[#111827]">
          <div className="flex items-center space-x-2.5">
            <Link2 className="w-5 h-5 text-emerald-400" />
            <h3 className="font-semibold text-lg">Associate Jira Story</h3>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white p-1 rounded-lg hover:bg-gray-800 transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-6 space-y-4">
          <div>
            <span className="text-xs uppercase tracking-wider text-gray-400 font-bold">Study Set</span>
            <p className="text-base font-medium text-emerald-300 mt-0.5">{studySet.name}</p>
          </div>

          {currentStory ? (
            <div className="p-4 rounded-lg bg-emerald-950/30 border border-emerald-700/60 space-y-3">
              <div className="flex items-start justify-between">
                <div>
                  <span className="text-xs text-emerald-400 font-semibold uppercase">Currently Linked Story</span>
                  <p className="font-medium text-white text-sm mt-0.5">
                    {currentStory.key}: {currentStory.summary}
                  </p>
                  <span className="inline-block mt-1 px-2 py-0.5 text-xs rounded bg-gray-700 text-gray-300">
                    Status: {currentStory.status}
                  </span>
                </div>
              </div>
              <div className="flex items-center space-x-2 pt-2 border-t border-emerald-800/40">
                {onOpenStory && (
                  <button
                    type="button"
                    onClick={() => {
                      onOpenStory(currentStory.id);
                      onClose();
                    }}
                    className="flex-1 inline-flex items-center justify-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-emerald-600 hover:bg-emerald-500 text-white transition"
                  >
                    <ExternalLink className="w-3.5 h-3.5" />
                    <span>Open Story</span>
                  </button>
                )}
                <button
                  type="button"
                  onClick={handleUnlink}
                  disabled={loading}
                  className="inline-flex items-center justify-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-rose-600/80 hover:bg-rose-500 text-white transition disabled:opacity-50"
                >
                  <Unlink className="w-3.5 h-3.5" />
                  <span>Unlink</span>
                </button>
              </div>
            </div>
          ) : (
            <>
              <div className="flex rounded-lg bg-gray-800 p-1 border border-gray-700">
                <button
                  type="button"
                  className={`flex-1 py-1.5 text-xs font-semibold rounded-md transition ${
                    mode === "create" ? "bg-emerald-600 text-white shadow-xs" : "text-gray-400 hover:text-white"
                  }`}
                  onClick={() => setMode("create")}
                >
                  Create New Story
                </button>
                <button
                  type="button"
                  className={`flex-1 py-1.5 text-xs font-semibold rounded-md transition ${
                    mode === "link" ? "bg-emerald-600 text-white shadow-xs" : "text-gray-400 hover:text-white"
                  }`}
                  onClick={() => {
                    setMode("link");
                    fetchIssues();
                  }}
                >
                  Link Existing Story
                </button>
              </div>

              {error && (
                <div className="p-3 bg-rose-950/70 border border-rose-800 text-rose-200 text-xs rounded-lg flex items-center space-x-2">
                  <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
                  <span>{error}</span>
                </div>
              )}

              {mode === "create" ? (
                <form onSubmit={handleCreateStory} className="space-y-4">
                  <div>
                    <label className="block text-xs font-medium text-gray-300 mb-1">Story Summary</label>
                    <input
                      type="text"
                      value={summary}
                      onChange={(e) => setSummary(e.target.value)}
                      required
                      placeholder="e.g. Master Binary Search Trees"
                      className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm text-white focus:outline-hidden focus:border-emerald-500"
                    />
                    <p className="text-[11px] text-gray-400 mt-1">
                      A study story (type: <span className="text-emerald-400 font-mono">study</span>) will be created in the selected Jira project.
                    </p>
                  </div>
                  <div className="flex justify-end space-x-2 pt-2">
                    <button
                      type="button"
                      onClick={onClose}
                      className="px-3.5 py-1.5 text-xs text-gray-400 hover:text-white bg-gray-800 hover:bg-gray-700 rounded-lg transition"
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      disabled={loading || !summary.trim()}
                      className="inline-flex items-center space-x-1.5 px-3.5 py-1.5 text-xs font-semibold bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg transition disabled:opacity-50"
                    >
                      <Plus className="w-3.5 h-3.5" />
                      <span>{loading ? "Creating..." : "Create & Link"}</span>
                    </button>
                  </div>
                </form>
              ) : (
                <form onSubmit={handleLinkStory} className="space-y-4">
                  <div>
                    <label className="block text-xs font-medium text-gray-300 mb-1">Select Story</label>
                    {loadingIssues ? (
                      <p className="text-xs text-gray-400 py-2">Loading stories...</p>
                    ) : existingIssues.length === 0 ? (
                      <p className="text-xs text-gray-400 py-2">No existing stories found.</p>
                    ) : (
                      <select
                        value={selectedIssueId}
                        onChange={(e) => setSelectedIssueId(e.target.value)}
                        className="w-full px-3 py-2 bg-gray-800 border border-gray-700 rounded-lg text-sm text-white focus:outline-hidden focus:border-emerald-500"
                      >
                        {existingIssues.map((iss) => (
                          <option key={iss.id} value={iss.id}>
                            {iss.key}: {iss.summary} ({iss.status})
                          </option>
                        ))}
                      </select>
                    )}
                  </div>
                  <div className="flex justify-end space-x-2 pt-2">
                    <button
                      type="button"
                      onClick={onClose}
                      className="px-3.5 py-1.5 text-xs text-gray-400 hover:text-white bg-gray-800 hover:bg-gray-700 rounded-lg transition"
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      disabled={loading || !selectedIssueId}
                      className="inline-flex items-center space-x-1.5 px-3.5 py-1.5 text-xs font-semibold bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg transition disabled:opacity-50"
                    >
                      <Link2 className="w-3.5 h-3.5" />
                      <span>{loading ? "Linking..." : "Link Story"}</span>
                    </button>
                  </div>
                </form>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
};
