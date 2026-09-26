import React, { useEffect, useRef, useState } from "react";
import {
  BookOpen,
  Upload,
  Link2,
  Trash2,
  ChevronDown,
  Layers,
  ArrowLeft,
  AlertCircle,
  ExternalLink,
  Maximize2,
  Minimize2,
} from "lucide-react";
import { QuizView } from "./views/QuizView";
import { MindmapView } from "./views/MindmapView";
import { FlashcardsView } from "./views/FlashcardsView";
import { ReportsView } from "./views/ReportsView";
import { SlidesView } from "./views/SlidesView";
import { DatatableView } from "./views/DatatableView";
import { InfographicView } from "./views/InfographicView";
import { QandaView } from "./views/QandaView";
import { PodcastView } from "./views/PodcastView";
import { HomeView } from "./views/HomeView";
import { AssociateStoryModal } from "./AssociateStoryModal";
import {
  getWorkspaceStatus,
  activateWorkspace as activateWorkspaceApi,
  listWorkspaceUploads,
  getUploadProgress,
  loadUploadedWorkspace,
  deleteStudySet,
  deleteStudyLibrary,
} from "./lib/api";
import type {
  StudySet,
  UploadedWorkspace,
  UploadProgress,
  WorkspaceOption,
  WorkspaceStatus,
} from "./types";
import "./styles.css";

const VIEWER_TABS = [
  { id: "home", label: "Overview", icon: "📚" },
  { id: "quizzes", label: "Quizzes", icon: "📝" },
  { id: "qanda", label: "Q&A", icon: "💬" },
  { id: "flashcards", label: "Flashcards", icon: "🗂️" },
  { id: "mindmaps", label: "Mind Maps", icon: "🧠" },
  { id: "reports", label: "Reports", icon: "📊" },
  { id: "slides", label: "Slides", icon: "📽️" },
  { id: "datatables", label: "Data Tables", icon: "📋" },
  { id: "infographics", label: "Infographics", icon: "🎨" },
  { id: "podcasts", label: "Podcasts", icon: "🎙️" },
];

type PendingDelete =
  | { kind: "studySet"; id: string; name: string }
  | { kind: "library"; id: string; name: string; workspaceCount: number };

interface StudySetAppProps {
  initialStudySetId?: string | null;
  initialTab?: string;
  onOpenStory?: (storyId: string) => void;
}

export const StudySetApp: React.FC<StudySetAppProps> = ({
  initialStudySetId,
  initialTab = "home",
  onOpenStory,
}) => {
  const [activeTab, setActiveTab] = useState(initialTab);
  const [workspace, setWorkspace] = useState<WorkspaceStatus | null>(null);
  const [workspaceError, setWorkspaceError] = useState("");
  const [workspaceAction, setWorkspaceAction] = useState<string | null>(null);
  const [uploads, setUploads] = useState<UploadedWorkspace[]>([]);
  const [showUploads, setShowUploads] = useState(false);
  const [loadingUploads, setLoadingUploads] = useState(true);
  const [uploadProgress, setUploadProgress] = useState<UploadProgress | null>(null);
  const [pendingDelete, setPendingDelete] = useState<PendingDelete | null>(null);
  const [associatingSet, setAssociatingSet] = useState<StudySet | WorkspaceOption | null>(null);
  const [isAssociateModalOpen, setIsAssociateModalOpen] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);

  const uploadInput = useRef<HTMLInputElement>(null);

  const refreshUploads = async () => {
    setLoadingUploads(true);
    try {
      const data = await listWorkspaceUploads();
      setUploads(data.uploads || []);
    } catch (e: any) {
      console.error("Failed to list study uploads:", e);
    } finally {
      setLoadingUploads(false);
    }
  };

  const refreshWorkspace = async () => {
    try {
      const data = await getWorkspaceStatus();
      setWorkspace(data);
      return data;
    } catch (e: any) {
      setWorkspaceError(e.message || "Failed to load workspace status");
      return null;
    }
  };

  useEffect(() => {
    Promise.all([refreshWorkspace(), refreshUploads()]);
  }, []);

  useEffect(() => {
    if (!isFullscreen) return;
    const restoreOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        setIsFullscreen(false);
      }
    };
    window.addEventListener("keydown", restoreOnEscape);
    return () => window.removeEventListener("keydown", restoreOnEscape);
  }, [isFullscreen]);

  // When initialStudySetId is passed or changed, activate it
  useEffect(() => {
    if (initialStudySetId && workspace) {
      const currentActive = workspace.workspaces.find(
        (w) => w.id === workspace.activeWorkspace || w.databaseWorkspaceId === workspace.activeWorkspace,
      );
      if (currentActive?.id !== initialStudySetId && currentActive?.databaseWorkspaceId !== initialStudySetId) {
        handleActivateWorkspace(initialStudySetId);
      }
    }
  }, [initialStudySetId, workspace]);

  const handleActivateWorkspace = async (workspaceId: string, navigateToQuiz = false) => {
    setWorkspaceAction("switch");
    setWorkspaceError("");
    try {
      const updated = await activateWorkspaceApi(workspaceId);
      setWorkspace(updated);
      await refreshUploads();
      if (navigateToQuiz) {
        setActiveTab("quizzes");
      }
    } catch (e: any) {
      setWorkspaceError(e.message || "Failed to activate study set");
    } finally {
      setWorkspaceAction(null);
    }
  };

  const handleLoadSavedWorkspace = async (uploadId: string, workspaceKey: string) => {
    setWorkspaceAction("switch");
    setWorkspaceError("");
    try {
      const updated = await loadUploadedWorkspace(uploadId, workspaceKey);
      setWorkspace(updated);
      await refreshUploads();
      setActiveTab("quizzes");
    } catch (e: any) {
      setWorkspaceError(e.message || "Failed to load study set");
    } finally {
      setWorkspaceAction(null);
    }
  };

  const handleUploadFile = async (file: File) => {
    if (!file.name.toLowerCase().endsWith(".zip")) {
      setWorkspaceError("Please select a .zip study set archive.");
      return;
    }
    if (file.size > 512 * 1024 * 1024) {
      setWorkspaceError("Please choose a ZIP archive smaller than 512 MB.");
      return;
    }

    setWorkspaceAction("upload");
    setWorkspaceError("");
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

    let polling = true;
    const pollTimer = window.setInterval(async () => {
      if (!polling) return;
      try {
        const prog = await getUploadProgress(progressId);
        setUploadProgress(prog);
      } catch {
        // Polling failure is safe to ignore
      }
    }, 250);

    try {
      const response = await fetch("/api/workspace/upload", {
        method: "POST",
        headers: {
          "Content-Type": "application/zip",
          "X-File-Name": encodeURIComponent(file.name),
          "X-Upload-ID": progressId,
          "X-File-Size": String(file.size),
        },
        body: file,
      });

      if (!response.ok) {
        let msg = `Upload failed (${response.status})`;
        try {
          const body = await response.json();
          if (body.detail) msg = body.detail;
          else if (body.error) msg = body.error;
        } catch {}
        throw new Error(msg);
      }

      const resData = await response.json();
      setWorkspace(resData);
      await refreshUploads();
      setActiveTab("home");
    } catch (err: any) {
      setWorkspaceError(err.message || "Upload failed");
    } finally {
      polling = false;
      window.clearInterval(pollTimer);
      setUploadProgress(null);
      setWorkspaceAction(null);
    }
  };

  const handleConfirmDelete = async () => {
    if (!pendingDelete) return;
    setWorkspaceAction("delete");
    setWorkspaceError("");
    try {
      if (pendingDelete.kind === "studySet") {
        const updated = await deleteStudySet(pendingDelete.id);
        setWorkspace(updated);
      } else {
        const updated = await deleteStudyLibrary(pendingDelete.id);
        setWorkspace(updated);
      }
      await refreshUploads();
      setPendingDelete(null);
    } catch (e: any) {
      setWorkspaceError(e.message || "Failed to delete");
    } finally {
      setWorkspaceAction(null);
    }
  };

  const activeOption = workspace?.workspaces.find((w) => w.id === workspace?.activeWorkspace) || workspace?.workspaces[0];
  const activeStory = activeOption?.story;

  return (
    <div
      className={`study-set-scope flex flex-col w-full bg-[#111827] text-gray-100 overflow-hidden font-sans ${
        isFullscreen ? "fixed inset-0 z-40 h-screen" : "h-full"
      }`}
    >
      {/* Top Header & Sub-Navigation */}
      <header className="flex-none bg-[#1f2937] border-b border-gray-700/80 px-4 py-2.5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          {/* Left: Study Set switcher */}
          <div className="flex items-center space-x-3">
            <div className="flex items-center space-x-2 text-emerald-400 font-bold text-sm tracking-wide">
              <BookOpen className="w-5 h-5 text-emerald-400" />
              <span>Study Set</span>
            </div>

            {workspace?.workspaces && workspace.workspaces.length > 0 && (
              <div className="relative flex items-center">
                <select
                  value={workspace.activeWorkspace}
                  disabled={workspaceAction !== null}
                  onChange={(e) => handleActivateWorkspace(e.target.value)}
                  className="bg-gray-900 border border-gray-700 text-white rounded-lg px-2.5 py-1 text-xs font-semibold focus:outline-none focus:ring-1 focus:ring-emerald-500 max-w-[220px] truncate"
                  title="Switch active study set"
                >
                  {workspace.workspaces.map((w) => (
                    <option key={w.id} value={w.id}>
                      {w.name}
                    </option>
                  ))}
                </select>
              </div>
            )}

            {/* Linked Jira Story Badge */}
            {activeStory ? (
              <button
                type="button"
                onClick={() => onOpenStory?.(activeStory.id)}
                className="hidden sm:inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-semibold rounded-md bg-emerald-950/80 border border-emerald-700 text-emerald-300 hover:bg-emerald-900 transition"
                title={`Linked Story: ${activeStory.summary} (${activeStory.status})`}
              >
                <Link2 className="w-3.5 h-3.5 text-emerald-400" />
                <span>{activeStory.key}</span>
                <span className="text-[10px] text-emerald-400/70">({activeStory.status})</span>
              </button>
            ) : activeOption ? (
              <button
                type="button"
                onClick={() => {
                  setAssociatingSet(activeOption);
                  setIsAssociateModalOpen(true);
                }}
                className="hidden sm:inline-flex items-center gap-1 px-2 py-0.5 text-xs rounded border border-gray-700 hover:border-gray-500 text-gray-400 hover:text-white transition"
                title="Link Jira story to current study set"
              >
                <Link2 className="w-3 h-3" />
                <span>Link Story</span>
              </button>
            ) : null}
          </div>

          {/* Right: Upload Button & Quick Action */}
          <div className="flex items-center space-x-2">
            <button
              type="button"
              onClick={() => setIsFullscreen((current) => !current)}
              className="inline-flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold border border-gray-600 bg-gray-800 hover:bg-gray-700 text-gray-100 transition"
              aria-label={isFullscreen ? "Exit study set full screen" : "Open study set full screen"}
              aria-pressed={isFullscreen}
              title={isFullscreen ? "Exit full screen (Esc)" : "Open full screen"}
            >
              {isFullscreen ? <Minimize2 className="w-3.5 h-3.5" /> : <Maximize2 className="w-3.5 h-3.5" />}
              <span>{isFullscreen ? "Exit full screen" : "Full screen"}</span>
            </button>
            <input
              ref={uploadInput}
              type="file"
              accept=".zip"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) handleUploadFile(file);
                e.target.value = "";
              }}
            />
            <button
              type="button"
              disabled={workspaceAction !== null}
              onClick={() => uploadInput.current?.click()}
              className="inline-flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white shadow-xs transition"
              title="Upload study set ZIP archive"
            >
              <Upload className="w-3.5 h-3.5" />
              <span>Upload ZIP</span>
            </button>
          </div>
        </div>

        {/* Sub-Navigation Tabs */}
        <div className="flex items-center space-x-1 overflow-x-auto mt-2 pt-2 border-t border-gray-800/60 scrollbar-none">
          {VIEWER_TABS.map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => setActiveTab(tab.id)}
              className={`px-3 py-1 rounded-full text-xs font-semibold transition whitespace-nowrap flex items-center space-x-1.5 ${
                activeTab === tab.id
                  ? "bg-emerald-500 text-white shadow-xs"
                  : "text-gray-400 hover:text-white hover:bg-gray-800"
              }`}
            >
              <span>{tab.icon}</span>
              <span>{tab.label}</span>
            </button>
          ))}
        </div>
      </header>

      {/* Progress & Error Notification */}
      {uploadProgress && (
        <div className="p-3 bg-emerald-950/80 border-b border-emerald-800 text-emerald-200 text-xs flex items-center justify-between">
          <div className="space-y-1 flex-1 max-w-xl">
            <div className="flex justify-between font-semibold">
              <span>{uploadProgress.message}...</span>
              <span>{uploadProgress.percent}%</span>
            </div>
            <div className="w-full h-1.5 bg-gray-800 rounded-full overflow-hidden">
              <div
                className="h-full bg-emerald-400 transition-all duration-200"
                style={{ width: `${uploadProgress.percent}%` }}
              />
            </div>
          </div>
        </div>
      )}

      {workspaceError && (
        <div className="p-2.5 bg-rose-950/80 border-b border-rose-800 text-rose-200 text-xs flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
            <span>{workspaceError}</span>
          </div>
          <button
            type="button"
            onClick={() => setWorkspaceError("")}
            className="text-rose-400 hover:text-white font-bold text-xs"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Content View Container */}
      <div className="study-set-content flex flex-1 min-h-0 min-w-0 overflow-hidden relative">
        {activeTab === "home" && (
          <HomeView
            workspace={workspace}
            uploads={uploads}
            loadingUploads={loadingUploads}
            busy={workspaceAction !== null}
            error={workspaceError}
            onChooseCurrent={(wid) => handleActivateWorkspace(wid, true)}
            onChooseSaved={handleLoadSavedWorkspace}
            onDeleteSaved={(_uid, sset) => setPendingDelete({ kind: "studySet", id: sset.id, name: sset.name })}
            onDeleteLibrary={(upload) =>
              setPendingDelete({
                kind: "library",
                id: upload.id,
                name: upload.name,
                workspaceCount: upload.workspaceCount,
              })
            }
            onUpload={() => uploadInput.current?.click()}
            onAssociateStory={(set) => {
              setAssociatingSet(set);
              setIsAssociateModalOpen(true);
            }}
            onOpenStory={onOpenStory}
            onNavigateTab={(tab) => setActiveTab(tab)}
          />
        )}
        {activeTab === "quizzes" && <QuizView />}
        {activeTab === "qanda" && <QandaView />}
        {activeTab === "flashcards" && <FlashcardsView />}
        {activeTab === "mindmaps" && <MindmapView />}
        {activeTab === "reports" && <ReportsView />}
        {activeTab === "slides" && <SlidesView />}
        {activeTab === "datatables" && <DatatableView />}
        {activeTab === "infographics" && <InfographicView />}
        {activeTab === "podcasts" && <PodcastView />}
      </div>

      {/* Modals */}
      <AssociateStoryModal
        isOpen={isAssociateModalOpen}
        studySet={associatingSet}
        onClose={() => {
          setIsAssociateModalOpen(false);
          setAssociatingSet(null);
        }}
        onSuccess={() => {
          refreshWorkspace();
          refreshUploads();
        }}
        onOpenStory={onOpenStory}
      />

      {/* Delete Confirmation Modal */}
      {pendingDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4">
          <div className="bg-[#1f2937] text-white border border-gray-700 rounded-xl p-6 max-w-md w-full shadow-2xl space-y-4">
            <h3 className="text-lg font-semibold text-rose-400">
              {pendingDelete.kind === "studySet" ? "Delete Study Set?" : "Delete Library Archive?"}
            </h3>
            <p className="text-sm text-gray-300">
              Are you sure you want to delete <strong>{pendingDelete.name}</strong>?
              {pendingDelete.kind === "library"
                ? ` This will delete all ${pendingDelete.workspaceCount} study sets in this archive.`
                : " This cannot be undone."}
            </p>
            <div className="flex justify-end space-x-3 pt-2">
              <button
                type="button"
                onClick={() => setPendingDelete(null)}
                className="px-4 py-2 text-sm text-gray-300 hover:text-white bg-gray-800 hover:bg-gray-700 rounded-lg transition"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={workspaceAction !== null}
                onClick={handleConfirmDelete}
                className="px-4 py-2 text-sm font-semibold text-white bg-rose-600 hover:bg-rose-500 rounded-lg transition"
              >
                {workspaceAction === "delete" ? "Deleting..." : "Delete"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
