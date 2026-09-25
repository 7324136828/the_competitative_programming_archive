export type UserRole = 'Admin' | 'Member' | 'Viewer';

export interface User {
  id: string;
  name: string;
  email: string;
  avatar: string;
  role: UserRole;
}

export interface Project {
  id: string;
  key: string;
  name: string;
  description?: string;
  lead_id?: string;
  lead_name?: string;
  lead_avatar?: string;
  total_issues?: number;
  completed_issues?: number;
}

export type IssueType = 'Story' | 'Bug' | 'Task' | 'Epic' | 'Feature' | 'Subtask';
export type StoryType = 'coding' | 'learning' | 'non-coding';
export type IssuePriority = 'Lowest' | 'Low' | 'Medium' | 'High' | 'Highest';

export interface IssueLink {
  link_id: string;
  id: string;
  key: string;
  summary: string;
  status: string;
  type: IssueType;
  priority: IssuePriority;
  direction: 'outward' | 'inward';
  link_type: 'blocks' | 'relates_to' | 'duplicates';
  displayRelation: string;
}

export interface Subtask {
  id: string;
  key: string;
  summary: string;
  status: string;
  type: IssueType;
  priority: IssuePriority;
  assignee_id?: string;
  assignee_name?: string;
  assignee_avatar?: string;
  story_points?: number;
}

export interface CustomFieldValue {
  id: string;
  name: string;
  field_type: 'text' | 'select' | 'number' | 'date' | 'checkbox';
  options_json?: string;
  value?: string;
}

export interface Issue {
  id: string;
  key: string;
  project_id: string;
  project_name?: string;
  project_key?: string;
  type: IssueType;
  story_type?: StoryType;
  summary: string;
  description: string;
  status: string;
  priority: IssuePriority;
  difficulty?: 'Easy' | 'Medium' | 'Hard';
  assignee_id?: string | null;
  assignee_name?: string;
  assignee_avatar?: string;
  reporter_id?: string;
  reporter_name?: string;
  reporter_avatar?: string;
  parent_id?: string | null;
  parent_key?: string;
  parent_summary?: string;
  sprint_id?: string | null;
  sprint_name?: string;
  version_id?: string | null;
  version_name?: string;
  rank: number;
  story_points?: number | null;
  start_date?: string | null;
  due_date?: string | null;
  totalTimeSpentMinutes?: number;
  problem_id?: number | null;
  archived_problem?: {
    id: number;
    title: string;
    problem_statements: string;
    language?: string;
    difficulty?: string;
    source?: string;
    archive_url?: string;
    audio?: { url?: string | null; status: string; updated_at?: string } | null;
  } | null;
  sample_input_output?: Array<{ input: string; output: string }>;
  hints?: string[];
  tags?: string[];
  submission_status?: string;
  created_at: string;
  updated_at: string;
  subtasks?: Subtask[];
  links?: IssueLink[];
  customFieldValues?: CustomFieldValue[];
  watchers?: User[];
}


export interface Comment {
  id: string;
  issue_id: string;
  author_id: string;
  author_name: string;
  author_avatar?: string;
  body: string;
  created_at: string;
}

export interface Worklog {
  id: string;
  issue_id: string;
  author_id: string;
  author_name: string;
  author_avatar?: string;
  time_spent_minutes: number;
  description?: string;
  started_at: string;
  created_at: string;
}

export interface Attachment {
  id: string;
  issue_id: string;
  filename: string;
  original_name: string;
  mime_type: string;
  size: number;
  uploaded_by: string;
  uploader_name?: string;
  created_at: string;
}

export interface Sprint {
  id: string;
  project_id: string;
  name: string;
  goal?: string;
  start_date?: string;
  end_date?: string;
  state: 'planned' | 'active' | 'closed';
  issue_count?: number;
  total_points?: number;
  completed_points?: number;
  created_at: string;
}

export interface Version {
  id: string;
  project_id: string;
  name: string;
  description?: string;
  release_date?: string;
  status: 'unreleased' | 'released' | 'archived';
  total_issues?: number;
  done_issues?: number;
  total_points?: number;
  done_points?: number;
}

export interface WorkflowTransition {
  id: string;
  workflow_id: string;
  from_status: string;
  to_status: string;
  name: string;
}

export interface WorkflowStatus {
  id: string;
  workflow_id: string;
  name: string;
  category: 'TODO' | 'IN_PROGRESS' | 'DONE';
  position: number;
}

export interface AutomationRule {
  id: string;
  project_id?: string;
  name: string;
  trigger_event: string;
  conditions_json: string;
  actions_json: string;
  is_enabled: number;
  created_at: string;
}

export interface AutomationLog {
  id: string;
  rule_id: string;
  rule_name: string;
  issue_id?: string;
  issue_key?: string;
  status: 'SUCCESS' | 'FAILED' | 'SKIPPED';
  details?: string;
  executed_at: string;
}

export interface PullRequest {
  id: string;
  issue_id: string;
  repo: string;
  pr_number: number;
  title: string;
  branch: string;
  status: 'OPEN' | 'MERGED' | 'CLOSED';
  url: string;
  created_at: string;
}

export interface Notification {
  id: string;
  user_id: string;
  title: string;
  message: string;
  issue_id?: string;
  issue_key?: string;
  is_read: number;
  created_at: string;
}

export interface SavedFilter {
  id: string;
  user_id: string;
  name: string;
  query_json: string;
  created_at: string;
}

export interface BurndownData {
  sprint: Sprint;
  totalPoints: number;
  completedPoints: number;
  remainingPoints: number;
  totalIssues: number;
  completedIssues: number;
  timeline: Array<{
    day: number;
    date: string;
    ideal: number;
    actual: number | null;
  }>;
}

export interface DashboardMetrics {
  statusCounts: Array<{ status: string; count: number }>;
  priorityCounts: Array<{ priority: string; count: number }>;
  assigneeWorkload: Array<{
    id: string;
    name: string;
    avatar: string;
    issue_count: number;
    total_points: number;
  }>;
  typeCounts: Array<{ type: string; count: number }>;
  recentComments: Array<{
    id: string;
    body: string;
    created_at: string;
    author_name: string;
    author_avatar: string;
    issue_key: string;
    issue_summary: string;
  }>;
}

export interface CrossTeamDependency {
  link_id: string;
  link_type: string;
  source_id: string;
  source_key: string;
  source_summary: string;
  source_status: string;
  source_project_id: string;
  source_project_key: string;
  source_project_name: string;
  target_id: string;
  target_key: string;
  target_summary: string;
  target_status: string;
  target_project_id: string;
  target_project_key: string;
  target_project_name: string;
}


export interface IssueMetrics {
  issueId: string;
  key: string;
  summary: string;
  type: IssueType;
  priority: IssuePriority;
  storyPoints?: number | null;
  currentStatus: string;
  currentStatusCategory: string;
  currentStatusSince: string;
  isResolved: boolean;
  createdAt: string;
  firstStartedAt: string | null;
  resolvedAt: string | null;
  leadTimeSeconds: number | null;
  cycleTimeSeconds: number | null;
  elapsedSeconds: number;
  activeTimeSeconds: number;
  waitTimeSeconds: number;
  doneTimeSeconds: number;
  timeInStatus: Record<string, number>;
  timeInCategory: Record<string, number>;
  reopenCount: number;
  transitionCount: number;
  loggedMinutes: number;
  originalEstimateMinutes: number;
  remainingEstimateMinutes: number;
  estimateAccuracy: number | null;
  timeline: Array<{
    status: string;
    category: string;
    from: string;
    to: string;
    seconds: number;
    changedByName: string | null;
    source: string;
  }>;
}

export interface SprintMetrics {
  id: string;
  projectId: string;
  name: string;
  goal?: string;
  state: string;
  plannedStart?: string;
  plannedEnd?: string;
  startedAt: string | null;
  completedAt: string | null;
  durationSeconds: number | null;
  plannedDurationDays: number | null;
  committedIssueCount: number | null;
  committedPoints: number | null;
  addedAfterStart: { issues: number; points: number };
  removedAfterStart: { issues: number; points: number };
  completedIssueCount: number;
  completedPoints: number;
  carriedOver: { issues: number; points: number } | null;
  finalScopePoints: number;
  velocityPoints: number;
  throughput: number;
  completionRatePercent: number | null;
  scopeCompletionPercent: number | null;
  activeSecondsInSprint: number | null;
  loggedMinutes: number | null;
  cycleTime: { avg: number | null; median: number | null; min: number | null; max: number | null };
  leadTime: { avg: number | null; median: number | null; min: number | null; max: number | null };
  issues: Array<{
    id: string;
    key: string;
    summary: string;
    type: IssueType;
    status: string;
    statusCategory: string;
    storyPoints?: number | null;
    assigneeId?: string | null;
    assigneeName?: string | null;
    addedAfterStart: boolean;
    outcome: string;
    metrics: {
      createdAt: string;
      firstStartedAt: string | null;
      resolvedAt: string | null;
      cycleTimeSeconds: number | null;
      leadTimeSeconds: number | null;
      activeTimeSeconds: number;
      loggedMinutes: number;
    };
  }>;
  byAssignee: Array<{
    assigneeId: string | null;
    assigneeName: string;
    completedIssues: number;
    completedPoints: number;
    activeSeconds: number;
  }>;
}

export interface ProjectMetrics {
  projectId: string;
  sprints: Array<{
    id: string;
    name: string;
    state: string;
    startedAt: string | null;
    completedAt: string | null;
    durationSeconds: number | null;
    committedPoints: number | null;
    completedPoints: number;
    completionRatePercent: number | null;
    throughput: number;
    avgCycleTimeSeconds: number | null;
  }>;
  velocity: {
    averageVelocityLast3: number | null;
    lastClosedSprints: Array<{ id: string; name: string; completedPoints: number; completedAt: string | null }>;
  };
  flow: {
    openIssues: number;
    resolvedIssues: number;
    avgCycleTimeSeconds: number | null;
    medianCycleTimeSeconds: number | null;
    avgLeadTimeSeconds: number | null;
    medianLeadTimeSeconds: number | null;
    resolvedLast7Days: number;
    resolvedLast30Days: number;
  };
}

export interface ProjectIssueMetricRow {
  id: string;
  key: string;
  summary: string;
  type: IssueType;
  priority: IssuePriority;
  storyPoints?: number | null;
  assigneeId?: string | null;
  currentStatus: string;
  currentStatusCategory: string;
  isResolved: boolean;
  createdAt: string;
  firstStartedAt: string | null;
  resolvedAt: string | null;
  leadTimeSeconds: number | null;
  cycleTimeSeconds: number | null;
  elapsedSeconds: number;
  activeTimeSeconds: number;
  waitTimeSeconds: number;
  reopenCount: number;
  transitionCount: number;
  loggedMinutes: number;
  estimateAccuracy: number | null;
}

export interface AiStatus {
  enabled: boolean;
  connectorUrl: string;
  model: string;
  modelSource: string;
  connector: { reachable: boolean; version?: string; error?: string };
  models: string[];
  tools: {
    registered: boolean | null;
    names: string[];
    lastRegistration: { at: string; registered: number; failed: number } | null;
  };
  autoRegister: boolean;
}

export interface AiRequestRow {
  id: string;
  feature: string;
  user_id?: string | null;
  model?: string | null;
  latency_ms?: number | null;
  status: string;
  error?: string | null;
  request_id?: string | null;
  created_at: string;
}
