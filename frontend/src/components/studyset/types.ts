/**
 * TypeScript ports of the pydantic models in
 * python/ollama_learning/schemas.py. Field names match exactly so the same
 * JSON files feed both the tkinter launchers and this app.
 */

export type Kind =
  | "quizzes"
  | "qandas"
  | "mindmaps"
  | "flashcards"
  | "reports"
  | "slides"
  | "datatables"
  | "infographics"
  | "podcasts";

export interface ManifestEntry {
  file: string;
  stem: string;
  title: string;
  sidecars: string[];
  /** Subject folder under new_output/ this document came from, or null for the
   * legacy flat output/ layout. */
  subject: string | null;
}

export interface Manifest {
  generatedAt: string;
  kinds: Record<Kind, ManifestEntry[]>;
}

// -- Quiz ------------------------------------------------------------------

export const DIFFICULTIES = [
  "recall",
  "understanding",
  "application",
  "analysis",
  "expert",
] as const;
export type Difficulty = (typeof DIFFICULTIES)[number];

export interface QuizQuestion {
  question: string;
  options: string[];
  correct: number;
  explanation: string;
  difficulty: Difficulty;
  sources: string[];
}

export interface Quiz {
  title: string;
  description: string;
  questions: QuizQuestion[];
}

// -- Free-text Q&A ---------------------------------------------------------

export interface QAPrompt {
  id: string;
  question: string;
  placeholder: string;
  required: boolean;
}

export interface QASet {
  title: string;
  description: string;
  questions: QAPrompt[];
}

// -- Mind map --------------------------------------------------------------

export interface MindMapNode {
  name: string;
  children: MindMapNode[];
}

export type MindMap = MindMapNode;

// -- Flashcards ------------------------------------------------------------

export const CARD_TYPES = ["basic", "cloze", "definition", "concept"] as const;
export type CardType = (typeof CARD_TYPES)[number];

export interface Flashcard {
  type: CardType;
  front: string;
  back: string;
  tags: string[];
  source_ids: string[];
}

export interface FlashcardSet {
  title: string;
  description: string;
  cards: Flashcard[];
}

// -- Reports ---------------------------------------------------------------

export interface Citation {
  source_id: string;
  page: number | null;
  chunk_id: string | null;
}

export interface Claim {
  claim: string;
  citations: Citation[];
}

export interface ReportSection {
  title: string;
  content: string;
  claims: Claim[];
}

export interface Report {
  title: string;
  executive_summary: string;
  sections: ReportSection[];
  conclusions: string;
}

// -- Slides ----------------------------------------------------------------

export interface Slide {
  title: string;
  subtitle: string | null;
  bullets: string[];
  speaker_notes: string;
  image_query: string | null;
  source_ids: string[];
}

export interface Presentation {
  title: string;
  slides: Slide[];
}

// -- Data tables -----------------------------------------------------------

export interface StudyField {
  name: string;
  description: string;
  example: string | null;
}

export interface DataTable {
  title: string;
  fields: StudyField[];
  data: Record<string, string>[];
}

// -- Infographics ----------------------------------------------------------

export const SECTION_TYPES = [
  "stat",
  "flow",
  "chart",
  "quote",
  "comparison",
  "svg",
] as const;
export type SectionType = (typeof SECTION_TYPES)[number];

export interface InfographicSection {
  type: SectionType;
  title: string | null;
  value: string | null;
  label: string | null;
  items: string[];
  panel: string | null;
  span: "full" | "half";
}

export interface Infographic {
  title: string;
  subtitle: string | null;
  sections: InfographicSection[];
}

// -- Podcasts --------------------------------------------------------------

export interface PodcastCastMember {
  speaker_id: string;
  host_id: string;
  name: string;
  voice_file: string;
  style: string;
}

export interface PodcastScene {
  speaker_id: string;
  dialogue: string;
  directions: string;
}

export interface PodcastSegment {
  segment_name: string;
  scenes: PodcastScene[];
}

export interface PodcastEpisode {
  episode_title: string;
  podcast_show: string;
  cast: PodcastCastMember[];
  script: PodcastSegment[];
}

// -- Workspace & Study Set Management --------------------------------------

export interface StudySetStory {
  id: string;
  key: string;
  summary: string;
  status: string;
  story_type?: string;
  priority?: string;
}

export interface WorkspaceOption {
  id: string;
  name: string;
  path?: string;
  databaseWorkspaceId?: string;
  story?: StudySetStory | null;
  exists?: boolean;
}

export interface WorkspaceStatus {
  activeWorkspace: string | null;
  workspaces: WorkspaceOption[];
  exists: boolean;
}

export interface StudySet {
  id: string;
  key: string;
  name: string;
  story?: StudySetStory | null;
}

export interface UploadedWorkspace {
  id: string;
  name: string;
  originalFilename: string;
  uploadedAt: string;
  workspaceCount: number;
  studySets: StudySet[];
}

export interface UploadProgress {
  uploadId?: string;
  id?: string;
  state?: string;
  phase?: string;
  percent: number;
  detail?: string;
  message?: string;
  error?: string | null;
  done?: boolean;
  currentWorkspace?: string | null;
  completedWorkspaces?: number;
  totalWorkspaces?: number;
}

