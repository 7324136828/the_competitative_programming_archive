import type {
  StudySet,
  StudySetStory,
  UploadedWorkspace,
  WorkspaceOption,
  WorkspaceStatus,
} from "../types";

interface HomeViewProps {
  workspace: WorkspaceStatus | null;
  uploads: UploadedWorkspace[];
  loadingUploads: boolean;
  busy: boolean;
  error: string;
  onChooseCurrent: (workspaceId: string) => void | Promise<void>;
  onChooseSaved: (uploadId: string, workspaceId: string) => void | Promise<void>;
  onDeleteSaved: (uploadId: string, studySet: StudySet) => void;
  onDeleteLibrary: (upload: UploadedWorkspace) => void;
  onUpload: () => void;
  onAssociateStory?: (studySet: StudySet | WorkspaceOption) => void;
  onOpenStory?: (storyId: string) => void;
  onNavigateTab?: (tab: string) => void;
}

function StudySetCard({
  name,
  detail,
  active = false,
  disabled,
  story,
  onClick,
  onDelete,
  onAssociateStory,
  onOpenStory,
}: {
  name: string;
  detail: string;
  active?: boolean;
  disabled: boolean;
  story?: StudySetStory | null;
  onClick: () => void;
  onDelete?: () => void;
  onAssociateStory?: () => void;
  onOpenStory?: (storyId: string) => void;
}) {
  const hasActions = Boolean(onDelete || onAssociateStory || (story && onOpenStory));

  return (
    <div className={hasActions ? "study-set-card has-actions" : "study-set-card"}>
      <button className="study-set-open" type="button" disabled={disabled} onClick={onClick}>
        <span className="study-set-mark" aria-hidden="true">
          {name.trim().slice(0, 1).toUpperCase() || "S"}
        </span>
        <span className="study-set-copy">
          <strong>{name}</strong>
          <span>{detail}</span>
        </span>
        <span className="study-set-action">{active ? "Continue" : "Study"} →</span>
      </button>

      {hasActions ? (
        <div className="study-set-card-actions">
          {story && onOpenStory ? (
            <button
              className="study-set-story linked"
              type="button"
              disabled={disabled}
              aria-label={`Open story ${story.key} for ${name}`}
              title={story.summary}
              onClick={() => onOpenStory(story.id)}
            >
              Open {story.key}
            </button>
          ) : onAssociateStory ? (
            <button
              className="study-set-story"
              type="button"
              disabled={disabled}
              aria-label={`Create story for ${name}`}
              onClick={onAssociateStory}
            >
              Create story
            </button>
          ) : null}

          {onDelete ? (
            <button
              className="study-set-delete"
              type="button"
              disabled={disabled}
              aria-label={`Delete ${name}`}
              onClick={onDelete}
            >
              Delete
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

export function HomeView({
  workspace,
  uploads,
  loadingUploads,
  busy,
  error,
  onChooseCurrent,
  onChooseSaved,
  onDeleteSaved,
  onDeleteLibrary,
  onUpload,
  onAssociateStory,
  onOpenStory,
}: HomeViewProps) {
  const hasSavedSets = uploads.some((upload) => (upload.studySets ?? []).length > 0);

  return (
    <main className="home-view scroll">
      <section className="home-hero">
        <p className="home-eyebrow">Your learning library</p>
        <h2>Choose a study set</h2>
        <p>Pick up where you left off, open a saved set, or import a new workspace ZIP.</p>
        <button className="primary big" type="button" disabled={busy} onClick={onUpload}>
          {busy ? "Working…" : "Upload a workspace ZIP"}
        </button>
        {error ? <p className="home-error error-text" role="alert">{error}</p> : null}
      </section>

      {workspace?.exists ? (
        <section className="study-section" aria-labelledby="current-study-sets">
          <div className="study-section-heading">
            <div>
              <p className="home-eyebrow">Open now</p>
              <h3 id="current-study-sets">Current study sets</h3>
            </div>
            <span>{workspace.workspaces.length} available</span>
          </div>
          <div className="study-set-grid">
            {workspace.workspaces.map((option) => (
              <StudySetCard
                key={option.id}
                name={option.name}
                detail={option.id === workspace.activeWorkspace ? "Active study set" : "Current library"}
                active={option.id === workspace.activeWorkspace}
                disabled={busy}
                story={option.story}
                onClick={() => onChooseCurrent(option.id)}
                onAssociateStory={() => onAssociateStory?.(option)}
                onOpenStory={onOpenStory}
              />
            ))}
          </div>
        </section>
      ) : null}

      <section className="study-section" aria-labelledby="saved-study-sets">
        <div className="study-section-heading">
          <div>
            <p className="home-eyebrow">Saved locally</p>
            <h3 id="saved-study-sets">Study libraries</h3>
          </div>
          {hasSavedSets ? <span>{uploads.length} {uploads.length === 1 ? "library" : "libraries"}</span> : null}
        </div>

        {loadingUploads ? (
          <div className="home-empty muted">Loading saved study sets…</div>
        ) : hasSavedSets ? (
          <div className="saved-libraries">
            {uploads.map((upload) => (
              <article className="saved-library" key={upload.id}>
                <header>
                  <div>
                    <h4>{upload.name}</h4>
                    <p>{upload.originalFilename}</p>
                  </div>
                  <div className="saved-library-actions">
                    <span>{upload.workspaceCount} {upload.workspaceCount === 1 ? "set" : "sets"}</span>
                    <button type="button" disabled={busy} onClick={() => onDeleteLibrary(upload)}>
                      Delete ZIP
                    </button>
                  </div>
                </header>
                <div className="study-set-grid">
                  {(upload.studySets ?? []).map((studySet) => (
                    <StudySetCard
                      key={studySet.id}
                      name={studySet.name}
                      detail={`From ${upload.name}`}
                      disabled={busy}
                      story={studySet.story}
                      onClick={() => onChooseSaved(upload.id, studySet.key)}
                      onDelete={() => onDeleteSaved(upload.id, studySet)}
                      onAssociateStory={() => onAssociateStory?.(studySet)}
                      onOpenStory={onOpenStory}
                    />
                  ))}
                </div>
              </article>
            ))}
          </div>
        ) : (
          <div className="home-empty">
            <strong>No saved study sets yet</strong>
            <p className="muted">Upload a ZIP containing an output folder to add one.</p>
          </div>
        )}
      </section>
    </main>
  );
}
