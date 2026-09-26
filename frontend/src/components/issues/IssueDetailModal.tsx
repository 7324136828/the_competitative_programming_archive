import React, { useState, useEffect } from 'react';
import {
  X,
  Eye,
  EyeOff,
  Trash2,
  Clock,
  Paperclip,
  GitPullRequest,
  GitBranch,
  MessageSquare,
  Plus,
  Link as LinkIcon,
  CheckCircle2,
  ExternalLink,
  ChevronDown,
  Calendar,
  AlertCircle,
  FileText,
  BookOpen
} from 'lucide-react';
import { useProject } from '../../context/ProjectContext.js';
import { useAuth } from '../../context/AuthContext.js';
import { api } from '../../api/client.js';
import { 
  Issue, 
  Comment, 
  Worklog, 
  Attachment, 
  PullRequest, 
  Sprint, 
  Version,
  WorkflowTransition 
} from '../../types/index.js';
import { TypeIcon, PriorityIcon, StatusBadge, RoleBadge, StoryTypeBadge } from '../common/Badge.js';
import { IssueMetrics } from '../../types/index.js';
import { formatDuration, formatDateTime, formatMinutes } from '../../utils/format.js';

interface IssueDetailModalProps {
  onOpenProblem?: (problemId: number) => void | Promise<void>;
}

export const IssueDetailModal: React.FC<IssueDetailModalProps> = ({ onOpenProblem }) => {
  const { selectedIssueId, closeIssueDetail, openIssueDetail, triggerRefresh, refreshKey, openActivity, openStudySet } = useProject();
  const { users, currentUser, canEdit } = useAuth();

  const [issue, setIssue] = useState<Issue | null>(null);
  const [comments, setComments] = useState<Comment[]>([]);
  const [worklogs, setWorklogs] = useState<Worklog[]>([]);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [pullRequests, setPullRequests] = useState<PullRequest[]>([]);
  const [allowedTransitions, setAllowedTransitions] = useState<Array<{ to_status: string; name: string }>>([]);
  const [allIssues, setAllIssues] = useState<Issue[]>([]);
  const [sprints, setSprints] = useState<Sprint[]>([]);
  const [versions, setVersions] = useState<Version[]>([]);

  const [activeTab, setActiveTab] = useState<'comments' | 'worklogs' | 'attachments' | 'dev' | 'metrics'>('comments');
  const [issueMetrics, setIssueMetrics] = useState<IssueMetrics | null>(null);
  const [newComment, setNewComment] = useState('');
  const [isSubmittingComment, setIsSubmittingComment] = useState(false);

  // Subtask creation state
  const [isAddingSubtask, setIsAddingSubtask] = useState(false);
  const [subtaskSummary, setSubtaskSummary] = useState('');

  // Link creation state
  const [isAddingLink, setIsAddingLink] = useState(false);
  const [linkTargetId, setLinkTargetId] = useState('');
  const [linkType, setLinkType] = useState<'blocks' | 'relates_to' | 'duplicates'>('blocks');

  // Worklog modal state
  const [isLoggingWork, setIsLoggingWork] = useState(false);
  const [workTimeInput, setWorkTimeInput] = useState('60'); // minutes
  const [workDesc, setWorkDesc] = useState('');

  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const fetchIssueData = async () => {
    if (!selectedIssueId) return;
    try {
      const data = await api.getIssue(selectedIssueId);
      setIssue(data);

      const [c, w, att, prs, trans, pIssues, pSprints, pVersions] = await Promise.all([
        api.getComments(data.id),
        api.getWorklogs(data.id),
        api.getAttachments(data.id),
        api.getPullRequests(data.id),
        api.getAllowedTransitions(data.project_id, data.status),
        api.getIssues({ projectId: data.project_id }),
        api.getSprints(data.project_id),
        api.getVersions(data.project_id),
      ]);

      setComments(c);
      setWorklogs(w);
      setAttachments(att);
      setPullRequests(prs);
      setAllowedTransitions(trans);
      setAllIssues(pIssues.filter((i: Issue) => i.id !== data.id));
      setSprints(pSprints);
      setVersions(pVersions);
    } catch (e: any) {
      console.error(e);
      setErrorMsg(e.message);
    }
  };

  useEffect(() => {
    if (selectedIssueId) {
      setErrorMsg(null);
      setSuccessMsg(null);
      setIssueMetrics(null);
      fetchIssueData();
    }
  }, [selectedIssueId]);

  useEffect(() => {
    if (activeTab === 'metrics' && selectedIssueId) {
      api.getIssueMetrics(selectedIssueId)
        .then(setIssueMetrics)
        .catch(e => { console.error(e); setIssueMetrics(null); });
    }
  }, [activeTab, selectedIssueId, refreshKey]);

  if (!selectedIssueId || !issue) return null;

  // J-08: Status transition
  const handleTransition = async (toStatus: string) => {
    try {
      setErrorMsg(null);
      await api.updateStatus(issue.id, toStatus);
      await fetchIssueData();
      triggerRefresh();
    } catch (err: any) {
      setErrorMsg(err.message);
    }
  };

  // J-02: Assignee change
  const handleAssigneeChange = async (userId: string) => {
    try {
      await api.assignIssue(issue.id, userId || null);
      await fetchIssueData();
      triggerRefresh();
    } catch (err: any) {
      setErrorMsg(err.message);
    }
  };

  // J-03: Subtask creation
  const handleCreateSubtask = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!subtaskSummary.trim()) return;
    try {
      await api.createSubtask(issue.id, { summary: subtaskSummary.trim() });
      setSubtaskSummary('');
      setIsAddingSubtask(false);
      await fetchIssueData();
      triggerRefresh();
    } catch (err: any) {
      setErrorMsg(err.message);
    }
  };

  // J-04: Issue Link creation
  const handleCreateLink = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!linkTargetId) return;
    try {
      await api.linkIssues(issue.id, linkTargetId, linkType);
      setIsAddingLink(false);
      setLinkTargetId('');
      await fetchIssueData();
      triggerRefresh();
    } catch (err: any) {
      setErrorMsg(err.message);
    }
  };

  const handleDeleteLink = async (linkId: string) => {
    try {
      await api.deleteLink(linkId);
      await fetchIssueData();
      triggerRefresh();
    } catch (err: any) {
      setErrorMsg(err.message);
    }
  };

  // J-06: Points
  const handlePointsChange = async (pointsStr: string) => {
    const val = pointsStr === '' ? null : Number(pointsStr);
    try {
      await api.setStoryPoints(issue.id, val);
      await fetchIssueData();
      triggerRefresh();
    } catch (err: any) {
      setErrorMsg(err.message);
    }
  };

  // J-07: Sprint
  const handleSprintChange = async (sprintId: string) => {
    try {
      await api.setSprint(issue.id, sprintId || null);
      await fetchIssueData();
      triggerRefresh();
    } catch (err: any) {
      setErrorMsg(err.message);
    }
  };

  // J-09: Add comment
  const handleAddComment = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newComment.trim()) return;
    setIsSubmittingComment(true);
    try {
      await api.addComment(issue.id, newComment.trim());
      setNewComment('');
      const c = await api.getComments(issue.id);
      setComments(c);
    } catch (err: any) {
      setErrorMsg(err.message);
    } finally {
      setIsSubmittingComment(false);
    }
  };

  // J-10: File upload
  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      setErrorMsg(null);
      await api.uploadAttachment(issue.id, file);
      const att = await api.getAttachments(issue.id);
      setAttachments(att);
    } catch (err: any) {
      setErrorMsg(err.message);
    }
  };

  // J-11: Watch / Unwatch
  const handleToggleWatch = async () => {
    try {
      await api.toggleWatch(issue.id);
      await fetchIssueData();
    } catch (err: any) {
      setErrorMsg(err.message);
    }
  };

  // J-12: Log work
  const handleLogWork = async (e: React.FormEvent) => {
    e.preventDefault();
    const mins = parseInt(workTimeInput, 10);
    if (isNaN(mins) || mins <= 0) return;
    try {
      await api.logWork(issue.id, {
        timeSpentMinutes: mins,
        description: workDesc,
      });
      setIsLoggingWork(false);
      setWorkDesc('');
      await fetchIssueData();
    } catch (err: any) {
      setErrorMsg(err.message);
    }
  };

  // J-17: Dates
  const handleDateChange = async (field: 'start' | 'due', val: string) => {
    const newStart = field === 'start' ? val : (issue.start_date || null);
    const newDue = field === 'due' ? val : (issue.due_date || null);
    try {
      await api.updateDates(issue.id, newStart || null, newDue || null);
      await fetchIssueData();
      triggerRefresh();
    } catch (err: any) {
      setErrorMsg(err.message);
    }
  };

  // J-18: Version
  const handleVersionChange = async (versionId: string) => {
    try {
      await api.setVersion(issue.id, versionId || null);
      await fetchIssueData();
      triggerRefresh();
    } catch (err: any) {
      setErrorMsg(err.message);
    }
  };

  // J-19: Custom field value
  const handleCustomFieldChange = async (fieldId: string, value: string) => {
    try {
      await api.setCustomField(issue.id, fieldId, value);
      await fetchIssueData();
    } catch (err: any) {
      setErrorMsg(err.message);
    }
  };

  // J-23: Simulate Pull Request Webhook
  const handleSimulatePR = async () => {
    try {
      await api.simulatePullRequest({ issueKey: issue.key });
      const prs = await api.getPullRequests(issue.id);
      setPullRequests(prs);
      setSuccessMsg('Git Pull Request simulated and linked successfully!');
      setTimeout(() => setSuccessMsg(null), 4000);
    } catch (err: any) {
      setErrorMsg(err.message);
    }
  };

  const isUserWatching = issue.watchers?.some(w => w.id === currentUser?.id);
  const eligibleUsers = users.filter(u => u.role !== 'Viewer');

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-xs animate-in fade-in duration-100">
      <div className="bg-white rounded-xl shadow-2xl border border-gray-200 w-full max-w-5xl h-[90vh] flex flex-col overflow-hidden animate-in zoom-in-95 duration-100">
        
        {/* Top Action Bar */}
        <div className="px-6 py-3 border-b border-gray-200 flex items-center justify-between bg-[#FAFBFC]">
          <div className="flex items-center space-x-3">
            <TypeIcon type={issue.type} className="w-5 h-5" />
            <span className="font-bold text-sm text-[#0052CC]">{issue.key}</span>
            <span className="text-gray-300">/</span>
            <span className="text-xs text-gray-500 font-medium">{issue.project_name}</span>
          </div>

          <div className="flex items-center space-x-3">
            {/* J-11: Watch / Unwatch button */}
            <button
              onClick={handleToggleWatch}
              className={`flex items-center space-x-1.5 px-3 py-1.5 rounded text-xs font-medium border transition ${
                isUserWatching
                  ? 'bg-blue-50 border-blue-200 text-[#0052CC]'
                  : 'bg-white border-gray-300 text-gray-600 hover:bg-gray-50'
              }`}
              title="Watch/Unwatch this work item for status notifications (J-11)"
            >
              {isUserWatching ? <Eye className="w-4 h-4 text-[#0052CC]" /> : <EyeOff className="w-4 h-4 text-gray-400" />}
              <span>{isUserWatching ? 'Watching' : 'Watch'}</span>
              <span className="text-[10px] bg-gray-200/80 px-1.5 rounded-full font-mono">
                {issue.watchers?.length || 0}
              </span>
            </button>

            {/* Open Activity Screen Button */}
            <button
              onClick={() => {
                closeIssueDetail();
                openActivity(issue);
              }}
              className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-bold bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 text-white shadow-xs transition"
              title="Open interactive Activity Screen"
            >
              <span>🚀 Open Activity</span>
            </button>

            {/* J-21: Delete Issue (Disabled for Viewers) */}
            <button
              onClick={async () => {
                if (confirm(`Are you sure you want to delete ${issue.key}?`)) {
                  try {
                    await api.deleteIssue(issue.id);
                    triggerRefresh();
                    closeIssueDetail();
                  } catch (e: any) {
                    setErrorMsg(e.message);
                  }
                }
              }}
              disabled={!canEdit}
              className="p-1.5 text-gray-400 hover:text-red-600 hover:bg-red-50 rounded transition disabled:opacity-30 disabled:hover:text-gray-400 disabled:hover:bg-transparent"
              title={!canEdit ? 'Viewers cannot delete issues' : 'Delete work item'}
            >
              <Trash2 className="w-4 h-4" />
            </button>

            <button
              onClick={closeIssueDetail}
              aria-label="Close"
              className="p-1 text-gray-400 hover:text-gray-600 rounded"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Notifications or Errors */}
        {errorMsg && (
          <div className="px-6 py-2 bg-red-50 border-b border-red-200 flex items-center justify-between text-xs text-red-700">
            <div className="flex items-center space-x-2">
              <AlertCircle className="w-4 h-4 text-red-600 shrink-0" />
              <span>{errorMsg}</span>
            </div>
            <button onClick={() => setErrorMsg(null)}><X className="w-3.5 h-3.5" /></button>
          </div>
        )}
        {successMsg && (
          <div className="px-6 py-2 bg-emerald-50 border-b border-emerald-200 flex items-center justify-between text-xs text-emerald-700">
            <div className="flex items-center space-x-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
              <span>{successMsg}</span>
            </div>
            <button onClick={() => setSuccessMsg(null)}><X className="w-3.5 h-3.5" /></button>
          </div>
        )}

        {/* Modal Main Content: Split Columns */}
        <div className="flex-1 flex overflow-hidden">
          
          {/* LEFT COLUMN: Summary, Description, Subtasks, Links, Activity */}
          <div className="flex-1 overflow-y-auto p-6 border-r border-gray-200 space-y-6">
            
            {/* Title / Summary */}
            <div className="space-y-2">
              <div className="flex items-center space-x-2 flex-wrap gap-y-1">
                {issue.story_type && <StoryTypeBadge storyType={issue.story_type} />}
                {issue.difficulty && (
                  <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${
                    issue.difficulty === 'Easy' ? 'bg-emerald-100 text-emerald-800' :
                    issue.difficulty === 'Hard' ? 'bg-rose-100 text-rose-800' :
                    'bg-amber-100 text-amber-800'
                  }`}>
                    {issue.difficulty}
                  </span>
                )}
                {issue.submission_status && (
                  <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                    issue.submission_status.toLowerCase() === 'accepted' ? 'bg-emerald-100 text-emerald-800' : 'bg-blue-100 text-blue-800'
                  }`}>
                    Submission: {issue.submission_status}
                  </span>
                )}
              </div>
              <h1 className="text-xl font-bold text-[#172B4D] leading-tight">{issue.summary}</h1>
            </div>

            {issue.problem_id && issue.archived_problem && (
              <div className="p-3.5 bg-amber-50 border border-amber-200 rounded-xl flex items-center justify-between">
                <div>
                  <div className="text-xs font-bold text-amber-900">
                    Archived Problem #{issue.archived_problem.id}
                  </div>
                  <div className="text-[11px] text-amber-700 mt-0.5">
                    {issue.archived_problem.title}
                    {issue.archived_problem.audio?.status === 'ready' ? ' · narration available' : ''}
                  </div>
                </div>
                <button
                  onClick={() => {
                    closeIssueDetail();
                    onOpenProblem?.(issue.problem_id as number);
                  }}
                  className="ml-3 px-3 py-1.5 bg-amber-600 hover:bg-amber-700 text-white rounded-lg text-xs font-semibold shrink-0"
                >
                  Open archived problem ↗
                </button>
              </div>
            )}

            {/* Associated Study Set Banner */}
            {(issue.story_type === 'study' || issue.study_set_id) && (
              <div className="p-3.5 bg-emerald-50 border border-emerald-200 rounded-xl flex items-center justify-between">
                <div>
                  <div className="text-xs font-bold text-emerald-900 flex items-center space-x-1.5">
                    <BookOpen className="w-4 h-4 text-emerald-600" />
                    <span>Associated Study Set {issue.study_set ? `· ${issue.study_set.title || issue.study_set.name}` : ''}</span>
                  </div>
                  <div className="text-[11px] text-emerald-700 mt-0.5">
                    Access 9 learning viewers: flashcards, quizzes, podcast studio, slides, mind maps, and interactive Q&A.
                  </div>
                </div>
                <button
                  onClick={() => {
                    closeIssueDetail();
                    if (issue.study_set_id) {
                      openStudySet(issue.study_set_id);
                    } else {
                      window.location.hash = '#studyset';
                    }
                  }}
                  className="ml-3 px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-semibold shrink-0 shadow-xs flex items-center space-x-1"
                >
                  <span>Open Study Set</span>
                  <ExternalLink className="w-3.5 h-3.5" />
                </button>
              </div>
            )}

            {/* Interactive Activity Banner */}
            <div className="p-3.5 bg-gradient-to-r from-blue-50 to-indigo-50 border border-blue-200 rounded-xl flex items-center justify-between">
              <div className="space-y-0.5">
                <span className="text-xs font-bold text-blue-900 flex items-center space-x-1.5">
                  <span>Interactive Activity Screen</span>
                </span>
                <p className="text-[11px] text-blue-700">
                  {issue.story_type === 'coding'
                    ? 'Code editor, test case runner, hints, and speech narration. Status changes to "Done" depend on Accepted code submissions.'
                    : issue.story_type === 'learning'
                    ? 'Interactive study guide, learning checklist, speech narration, and AI concept tutor.'
                    : issue.story_type === 'study'
                    ? 'Interactive Study Set viewer hub, progress tracker, and audio learning tools.'
                    : 'System design requirements, architecture proposal canvas, and AI design critique.'}
                </p>
              </div>
              <button
                onClick={() => {
                  closeIssueDetail();
                  openActivity(issue);
                }}
                className="ml-3 px-3 py-1.5 bg-[#0052CC] hover:bg-blue-700 text-white rounded-lg text-xs font-semibold shrink-0 shadow-xs transition"
              >
                Launch Screen ↗
              </button>
            </div>

            {/* Description */}
            <div>
              <h3 className="text-xs font-bold text-gray-700 uppercase tracking-wider mb-2">Description</h3>
              <div className="text-xs text-gray-800 whitespace-pre-wrap bg-gray-50/70 p-3 rounded-lg border border-gray-200 min-h-16">
                {issue.description || <span className="text-gray-400 italic">No description provided.</span>}
              </div>
            </div>

            {/* J-03: Subtasks section */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center space-x-2">
                  <h3 className="text-xs font-bold text-gray-700 uppercase tracking-wider">Subtasks</h3>
                  <span className="text-[10px] bg-blue-100 text-blue-800 px-1.5 py-0.2 rounded font-mono">J-03</span>
                </div>
                {canEdit && (
                  <button
                    onClick={() => setIsAddingSubtask(!isAddingSubtask)}
                    className="text-xs text-[#0052CC] hover:underline flex items-center space-x-1"
                  >
                    <Plus className="w-3.5 h-3.5" />
                    <span>Create subtask</span>
                  </button>
                )}
              </div>

              {/* Progress bar */}
              {issue.subtasks && issue.subtasks.length > 0 && (
                <div className="mb-3">
                  <div className="w-full bg-gray-200 rounded-full h-1.5 overflow-hidden">
                    <div
                      className="bg-emerald-500 h-1.5 rounded-full transition-all duration-300"
                      style={{
                        width: `${(issue.subtasks.filter(s => s.status === 'Done').length / issue.subtasks.length) * 100}%`
                      }}
                    />
                  </div>
                  <div className="text-[11px] text-gray-500 mt-1">
                    {issue.subtasks.filter(s => s.status === 'Done').length} of {issue.subtasks.length} subtasks done
                  </div>
                </div>
              )}

              {/* Add Subtask Inline Form */}
              {isAddingSubtask && (
                <form onSubmit={handleCreateSubtask} className="flex items-center space-x-2 mb-3">
                  <input
                    type="text"
                    autoFocus
                    value={subtaskSummary}
                    onChange={e => setSubtaskSummary(e.target.value)}
                    placeholder="What needs to be done?"
                    className="flex-1 px-3 py-1.5 border border-gray-300 rounded text-xs outline-none focus:ring-1 focus:ring-blue-500"
                  />
                  <button type="submit" className="px-3 py-1.5 bg-[#0052CC] text-white text-xs font-semibold rounded hover:bg-[#0065FF]">
                    Add
                  </button>
                  <button type="button" onClick={() => setIsAddingSubtask(false)} className="px-2 py-1.5 text-xs text-gray-500">
                    Cancel
                  </button>
                </form>
              )}

              {/* Subtasks List */}
              <div className="space-y-1.5">
                {issue.subtasks?.map(sub => (
                  <div
                    key={sub.id}
                    onClick={() => openIssueDetail(sub.id)}
                    className="flex items-center justify-between p-2 rounded-md hover:bg-[#F4F5F7] border border-gray-100 cursor-pointer transition text-xs"
                  >
                    <div className="flex items-center space-x-2">
                      <TypeIcon type="Subtask" />
                      <span className="font-semibold text-[#0052CC]">{sub.key}</span>
                      <span className="text-gray-800">{sub.summary}</span>
                    </div>
                    <div className="flex items-center space-x-2">
                      {sub.assignee_name && (
                        <span className="text-[11px] text-gray-500">{sub.assignee_name}</span>
                      )}
                      <StatusBadge status={sub.status} />
                    </div>
                  </div>
                ))}
                {(!issue.subtasks || issue.subtasks.length === 0) && !isAddingSubtask && (
                  <div className="text-xs text-gray-400 italic">No subtasks.</div>
                )}
              </div>
            </div>

            {/* J-04: Issue Links & Dependencies */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center space-x-2">
                  <h3 className="text-xs font-bold text-gray-700 uppercase tracking-wider">Issue Links & Dependencies</h3>
                  <span className="text-[10px] bg-blue-100 text-blue-800 px-1.5 py-0.2 rounded font-mono">J-04</span>
                </div>
                {canEdit && (
                  <button
                    onClick={() => setIsAddingLink(!isAddingLink)}
                    className="text-xs text-[#0052CC] hover:underline flex items-center space-x-1"
                  >
                    <LinkIcon className="w-3.5 h-3.5" />
                    <span>Link issue</span>
                  </button>
                )}
              </div>

              {/* Add Link Form */}
              {isAddingLink && (
                <form onSubmit={handleCreateLink} className="p-3 bg-gray-50 rounded-lg border border-gray-200 mb-3 space-y-2">
                  <div className="flex items-center space-x-2">
                    <select
                      value={linkType}
                      onChange={e => setLinkType(e.target.value as any)}
                      className="px-2 py-1.5 border border-gray-300 rounded text-xs bg-white outline-none"
                    >
                      <option value="blocks">blocks</option>
                      <option value="relates_to">relates to</option>
                      <option value="duplicates">duplicates</option>
                    </select>

                    <select
                      value={linkTargetId}
                      onChange={e => setLinkTargetId(e.target.value)}
                      className="flex-1 px-2 py-1.5 border border-gray-300 rounded text-xs bg-white outline-none"
                    >
                      <option value="">Select target issue...</option>
                      {allIssues.map(i => (
                        <option key={i.id} value={i.id}>
                          {i.key} - {i.summary} ({i.status})
                        </option>
                      ))}
                    </select>

                    <button type="submit" className="px-3 py-1.5 bg-[#0052CC] text-white text-xs font-semibold rounded hover:bg-[#0065FF]">
                      Link
                    </button>
                    <button type="button" onClick={() => setIsAddingLink(false)} className="px-2 py-1.5 text-xs text-gray-500">
                      Cancel
                    </button>
                  </div>
                </form>
              )}

              {/* Links List */}
              <div className="space-y-1.5">
                {issue.links?.map(l => (
                  <div
                    key={l.link_id}
                    className="flex items-center justify-between p-2 rounded-md bg-gray-50 hover:bg-[#F4F5F7] border border-gray-200 text-xs transition"
                  >
                    <div className="flex items-center space-x-2">
                      <span className="font-semibold text-gray-500 capitalize">{l.displayRelation}</span>
                      <TypeIcon type={l.type} />
                      <button
                        onClick={() => openIssueDetail(l.id)}
                        className="font-semibold text-[#0052CC] hover:underline"
                      >
                        {l.key}
                      </button>
                      <span className="text-gray-800 truncate max-w-xs">{l.summary}</span>
                    </div>

                    <div className="flex items-center space-x-3">
                      <StatusBadge status={l.status} />
                      {canEdit && (
                        <button
                          onClick={() => handleDeleteLink(l.link_id)}
                          className="text-gray-400 hover:text-red-600 p-0.5"
                          title="Remove link"
                        >
                          <X className="w-3.5 h-3.5" />
                        </button>
                      )}
                    </div>
                  </div>
                ))}
                {(!issue.links || issue.links.length === 0) && !isAddingLink && (
                  <div className="text-xs text-gray-400 italic">No linked issues.</div>
                )}
              </div>
            </div>

            {/* ACTIVITY TABS: Comments (J-09), Worklogs (J-12), Attachments (J-10), Dev Tools (J-23) */}
            <div className="pt-4 border-t border-gray-200">
              <div className="flex items-center space-x-4 border-b border-gray-200 mb-4">
                <button
                  onClick={() => setActiveTab('comments')}
                  className={`pb-2 text-xs font-semibold flex items-center space-x-1.5 border-b-2 transition ${
                    activeTab === 'comments'
                      ? 'border-[#0052CC] text-[#0052CC]'
                      : 'border-transparent text-gray-500 hover:text-gray-700'
                  }`}
                >
                  <MessageSquare className="w-3.5 h-3.5" />
                  <span>Comments ({comments.length})</span>
                </button>

                <button
                  onClick={() => setActiveTab('worklogs')}
                  className={`pb-2 text-xs font-semibold flex items-center space-x-1.5 border-b-2 transition ${
                    activeTab === 'worklogs'
                      ? 'border-[#0052CC] text-[#0052CC]'
                      : 'border-transparent text-gray-500 hover:text-gray-700'
                  }`}
                >
                  <Clock className="w-3.5 h-3.5" />
                  <span>Work Log ({worklogs.length})</span>
                </button>

                <button
                  onClick={() => setActiveTab('attachments')}
                  className={`pb-2 text-xs font-semibold flex items-center space-x-1.5 border-b-2 transition ${
                    activeTab === 'attachments'
                      ? 'border-[#0052CC] text-[#0052CC]'
                      : 'border-transparent text-gray-500 hover:text-gray-700'
                  }`}
                >
                  <Paperclip className="w-3.5 h-3.5" />
                  <span>Attachments ({attachments.length})</span>
                </button>

                <button
                  onClick={() => setActiveTab('dev')}
                  className={`pb-2 text-xs font-semibold flex items-center space-x-1.5 border-b-2 transition ${
                    activeTab === 'dev'
                      ? 'border-[#0052CC] text-[#0052CC]'
                      : 'border-transparent text-gray-500 hover:text-gray-700'
                  }`}
                >
                  <GitPullRequest className="w-3.5 h-3.5" />
                  <span>Development ({pullRequests.length})</span>
                </button>

                <button
                  onClick={() => setActiveTab('metrics')}
                  className={`pb-2 text-xs font-semibold flex items-center space-x-1.5 border-b-2 transition ${
                    activeTab === 'metrics'
                      ? 'border-[#0052CC] text-[#0052CC]'
                      : 'border-transparent text-gray-500 hover:text-gray-700'
                  }`}
                >
                  <Clock className="w-3.5 h-3.5" />
                  <span>Time Metrics</span>
                </button>
              </div>

              {/* TAB 1: COMMENTS (J-09) */}
              {activeTab === 'comments' && (
                <div className="space-y-4">
                  {canEdit && (
                    <form onSubmit={handleAddComment} className="space-y-2">
                      <div className="flex items-start space-x-2">
                        <img
                          src={currentUser?.avatar}
                          alt={currentUser?.name}
                          className="w-7 h-7 rounded-full object-cover mt-1"
                        />
                        <div className="flex-1">
                          <textarea
                            rows={3}
                            value={newComment}
                            onChange={e => setNewComment(e.target.value)}
                            placeholder="Add a comment... (J-09)"
                            className="w-full p-2.5 border border-gray-300 rounded-lg text-xs outline-none focus:ring-1 focus:ring-blue-500"
                          />
                        </div>
                      </div>
                      <div className="flex justify-end">
                        <button
                          type="submit"
                          disabled={isSubmittingComment || !newComment.trim()}
                          className="px-4 py-1.5 bg-[#0052CC] hover:bg-[#0065FF] text-white text-xs font-semibold rounded-md transition disabled:opacity-50"
                        >
                          Save
                        </button>
                      </div>
                    </form>
                  )}

                  {/* Comment Feed */}
                  <div className="space-y-3">
                    {comments.map(c => (
                      <div key={c.id} className="p-3 rounded-lg bg-gray-50 border border-gray-100 flex items-start space-x-3 text-xs">
                        <img src={c.author_avatar} alt={c.author_name} className="w-6 h-6 rounded-full object-cover shrink-0 mt-0.5" />
                        <div className="flex-1">
                          <div className="flex items-center justify-between">
                            <span className="font-semibold text-gray-900">{c.author_name}</span>
                            <span className="text-[10px] text-gray-400">
                              {new Date(c.created_at).toLocaleString()}
                            </span>
                          </div>
                          <p className="mt-1 text-gray-700 whitespace-pre-wrap">{c.body}</p>
                        </div>
                      </div>
                    ))}
                    {comments.length === 0 && (
                      <div className="text-center py-4 text-xs text-gray-400">No comments yet.</div>
                    )}
                  </div>
                </div>
              )}

              {/* TAB 2: WORKLOGS (J-12) */}
              {activeTab === 'worklogs' && (
                <div className="space-y-4">
                  <div className="flex items-center justify-between bg-blue-50 p-3 rounded-lg border border-blue-100">
                    <div>
                      <div className="text-xs font-semibold text-blue-900">Total Time Logged</div>
                      <div className="text-lg font-bold text-[#0052CC]">
                        {Math.floor((issue.totalTimeSpentMinutes || 0) / 60)}h {(issue.totalTimeSpentMinutes || 0) % 60}m
                      </div>
                    </div>
                    {canEdit && (
                      <button
                        onClick={() => setIsLoggingWork(!isLoggingWork)}
                        className="px-3 py-1.5 bg-[#0052CC] text-white text-xs font-semibold rounded hover:bg-[#0065FF] flex items-center space-x-1"
                      >
                        <Clock className="w-3.5 h-3.5" />
                        <span>Log work (J-12)</span>
                      </button>
                    )}
                  </div>

                  {/* Log Work Form */}
                  {isLoggingWork && (
                    <form onSubmit={handleLogWork} className="p-4 bg-gray-50 border border-gray-200 rounded-lg space-y-3 text-xs">
                      <div className="grid grid-cols-2 gap-3">
                        <div>
                          <label className="block font-semibold text-gray-700 mb-1">Time spent (minutes) *</label>
                          <input
                            type="number"
                            min="1"
                            value={workTimeInput}
                            onChange={e => setWorkTimeInput(e.target.value)}
                            className="w-full px-3 py-1.5 border border-gray-300 rounded outline-none"
                            placeholder="e.g. 90"
                          />
                        </div>
                        <div>
                          <label className="block font-semibold text-gray-700 mb-1">Work description</label>
                          <input
                            type="text"
                            value={workDesc}
                            onChange={e => setWorkDesc(e.target.value)}
                            className="w-full px-3 py-1.5 border border-gray-300 rounded outline-none"
                            placeholder="What did you work on?"
                          />
                        </div>
                      </div>
                      <div className="flex justify-end space-x-2">
                        <button type="button" onClick={() => setIsLoggingWork(false)} className="px-3 py-1 text-gray-600">Cancel</button>
                        <button type="submit" className="px-3 py-1 bg-[#0052CC] text-white font-semibold rounded hover:bg-[#0065FF]">Save Worklog</button>
                      </div>
                    </form>
                  )}

                  {/* Worklogs List */}
                  <div className="space-y-2">
                    {worklogs.map(w => (
                      <div key={w.id} className="p-2.5 rounded bg-gray-50 border border-gray-200 flex items-center justify-between text-xs">
                        <div className="flex items-center space-x-2">
                          <img src={w.author_avatar} alt={w.author_name} className="w-6 h-6 rounded-full object-cover" />
                          <div>
                            <span className="font-semibold text-gray-800">{w.author_name}</span>
                            <span className="text-gray-500 ml-2">logged {Math.floor(w.time_spent_minutes / 60)}h {w.time_spent_minutes % 60}m</span>
                            {w.description && <p className="text-gray-600 text-[11px] mt-0.5">{w.description}</p>}
                          </div>
                        </div>
                        <span className="text-[10px] text-gray-400 font-mono">{w.started_at}</span>
                      </div>
                    ))}
                    {worklogs.length === 0 && !isLoggingWork && (
                      <div className="text-center py-4 text-xs text-gray-400">No work logged yet.</div>
                    )}
                  </div>
                </div>
              )}

              {/* TAB 3: ATTACHMENTS (J-10) */}
              {activeTab === 'attachments' && (
                <div className="space-y-4">
                  {canEdit && (
                    <div className="border-2 border-dashed border-gray-300 rounded-lg p-6 text-center hover:border-blue-400 transition bg-gray-50/50">
                      <Paperclip className="w-6 h-6 text-gray-400 mx-auto mb-2" />
                      <div className="text-xs text-gray-600 mb-1">
                        Upload screenshot or log file (Max 10 MB - J-10)
                      </div>
                      <input
                        type="file"
                        onChange={handleFileUpload}
                        className="text-xs text-gray-500 file:mr-3 file:py-1 file:px-3 file:rounded file:border-0 file:text-xs file:font-semibold file:bg-[#0052CC] file:text-white hover:file:bg-[#0065FF] cursor-pointer"
                      />
                    </div>
                  )}

                  <div className="grid grid-cols-2 gap-3">
                    {attachments.map(a => (
                      <div key={a.id} className="p-3 rounded-lg border border-gray-200 bg-white flex items-center justify-between text-xs shadow-xs">
                        <div className="flex items-center space-x-2 overflow-hidden">
                          <FileText className="w-5 h-5 text-blue-500 shrink-0" />
                          <div className="overflow-hidden">
                            <a
                              href={`/uploads/${a.filename}`}
                              target="_blank"
                              rel="noreferrer"
                              className="font-medium text-[#0052CC] hover:underline truncate block"
                            >
                              {a.original_name}
                            </a>
                            <span className="text-[10px] text-gray-400 font-mono">
                              {(a.size / 1024).toFixed(1)} KB • {a.uploader_name}
                            </span>
                          </div>
                        </div>
                      </div>
                    ))}
                    {attachments.length === 0 && (
                      <div className="col-span-2 text-center py-4 text-xs text-gray-400">No attachments uploaded.</div>
                    )}
                  </div>
                </div>
              )}

              {/* TAB 4: DEVELOPMENT ACTIVITY (J-23) */}
              {activeTab === 'dev' && (
                <div className="space-y-4">
                  <div className="flex items-center justify-between bg-gray-50 p-3 rounded-lg border border-gray-200">
                    <div>
                      <div className="text-xs font-semibold text-gray-800">Development Activity (J-23)</div>
                      <div className="text-[11px] text-gray-500">Pull requests, branches, and code reviews linked to {issue.key}</div>
                    </div>
                    {canEdit && (
                      <button
                        onClick={handleSimulatePR}
                        className="px-3 py-1.5 bg-gray-800 hover:bg-black text-white text-xs font-semibold rounded flex items-center space-x-1.5 shadow-sm transition"
                      >
                        <GitPullRequest className="w-3.5 h-3.5" />
                        <span>Simulate PR Webhook</span>
                      </button>
                    )}
                  </div>

                  <div className="space-y-2">
                    {pullRequests.map(pr => (
                      <div key={pr.id} className="p-3 rounded-lg border border-gray-200 bg-white flex items-center justify-between text-xs">
                        <div className="flex items-start space-x-3">
                          <GitPullRequest
                            className={`w-4 h-4 mt-0.5 ${
                              pr.status === 'MERGED' ? 'text-purple-600' : (pr.status === 'OPEN' ? 'text-emerald-600' : 'text-red-500')
                            }`}
                          />
                          <div>
                            <a
                              href={pr.url}
                              target="_blank"
                              rel="noreferrer"
                              className="font-semibold text-gray-900 hover:text-[#0052CC] flex items-center space-x-1"
                            >
                              <span>{pr.title}</span>
                              <ExternalLink className="w-3 h-3 text-gray-400" />
                            </a>
                            <div className="flex items-center space-x-2 text-[11px] text-gray-500 mt-0.5">
                              <span className="font-mono">#{pr.pr_number}</span>
                              <span>•</span>
                              <span className="flex items-center space-x-1">
                                <GitBranch className="w-3 h-3 text-gray-400" />
                                <span className="font-mono">{pr.branch}</span>
                              </span>
                              <span>•</span>
                              <span>{pr.repo}</span>
                            </div>
                          </div>
                        </div>

                        <span
                          className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${
                            pr.status === 'MERGED'
                              ? 'bg-purple-100 text-purple-800'
                              : (pr.status === 'OPEN' ? 'bg-emerald-100 text-emerald-800' : 'bg-red-100 text-red-800')
                          }`}
                        >
                          {pr.status}
                        </span>
                      </div>
                    ))}
                    {pullRequests.length === 0 && (
                      <div className="text-center py-6 text-xs text-gray-400">
                        No pull requests linked. Click "Simulate PR Webhook" to test git integration.
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* TAB 5: TIME METRICS */}
              {activeTab === 'metrics' && (
                <div className="space-y-4">
                  {!issueMetrics ? (
                    <div className="text-center py-6 text-xs text-gray-400">Loading time metrics...</div>
                  ) : (
                    <>
                      <div className="grid grid-cols-3 gap-3">
                        {[
                          { label: 'Created', value: formatDateTime(issueMetrics.createdAt), title: issueMetrics.createdAt },
                          { label: 'First started', value: formatDateTime(issueMetrics.firstStartedAt), title: issueMetrics.firstStartedAt || undefined },
                          { label: 'Resolved', value: formatDateTime(issueMetrics.resolvedAt), title: issueMetrics.resolvedAt || undefined },
                          { label: 'Lead time', value: formatDuration(issueMetrics.leadTimeSeconds), title: issueMetrics.leadTimeSeconds != null ? `${issueMetrics.leadTimeSeconds}s` : undefined },
                          { label: 'Cycle time', value: formatDuration(issueMetrics.cycleTimeSeconds), title: issueMetrics.cycleTimeSeconds != null ? `${issueMetrics.cycleTimeSeconds}s` : undefined },
                          { label: 'Active time', value: formatDuration(issueMetrics.activeTimeSeconds), title: `${issueMetrics.activeTimeSeconds}s` },
                          { label: 'Wait time', value: formatDuration(issueMetrics.waitTimeSeconds), title: `${issueMetrics.waitTimeSeconds}s` },
                          { label: 'Time Done (before reopen)', value: formatDuration(issueMetrics.doneTimeSeconds), title: `${issueMetrics.doneTimeSeconds}s` },
                          { label: 'Reopens', value: String(issueMetrics.reopenCount) },
                          { label: 'Transitions', value: String(issueMetrics.transitionCount) },
                          {
                            label: 'Logged vs original estimate',
                            value: `${formatMinutes(issueMetrics.loggedMinutes)} / ${formatMinutes(issueMetrics.originalEstimateMinutes)}`,
                          },
                          {
                            label: 'Estimate accuracy',
                            value: issueMetrics.estimateAccuracy != null ? `${Math.round(issueMetrics.estimateAccuracy * 100)}%` : '-',
                          },
                        ].map(c => (
                          <div key={c.label} className="p-3 bg-gray-50 border border-gray-200 rounded-lg" title={c.title}>
                            <div className="text-[10px] font-bold text-gray-400 uppercase tracking-wider">{c.label}</div>
                            <div className="text-sm font-bold text-[#172B4D] mt-0.5">{c.value}</div>
                          </div>
                        ))}
                      </div>

                      <div>
                        <div className="text-[11px] font-bold text-gray-500 uppercase tracking-wider mb-2">Status timeline</div>
                        <div className="space-y-1.5">
                          {issueMetrics.timeline.map((t, idx) => (
                            <div key={idx} className="flex items-center justify-between p-2 rounded-md bg-gray-50 border border-gray-100 text-xs">
                              <div className="flex items-center space-x-2">
                                <StatusBadge status={t.status} />
                                <span className="text-gray-500 font-mono text-[10px]" title={t.from}>
                                  {formatDateTime(t.from)}
                                </span>
                                <span className="text-gray-400">→</span>
                                <span className="text-gray-500 font-mono text-[10px]" title={t.to}>
                                  {formatDateTime(t.to)}
                                </span>
                              </div>
                              <div className="flex items-center space-x-2">
                                <span className="font-mono text-gray-700" title={`${t.seconds}s`}>{formatDuration(t.seconds)}</span>
                                {t.changedByName && <span className="text-[10px] text-gray-400">by {t.changedByName}</span>}
                                {t.source !== 'user' && (
                                  <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold uppercase ${
                                    t.source === 'ai' ? 'bg-purple-100 text-purple-700'
                                    : t.source === 'automation' ? 'bg-amber-100 text-amber-700'
                                    : 'bg-gray-200 text-gray-600'
                                  }`}>
                                    {t.source}
                                  </span>
                                )}
                              </div>
                            </div>
                          ))}
                          {issueMetrics.timeline.length === 0 && (
                            <div className="text-center py-4 text-xs text-gray-400">No status history.</div>
                          )}
                          <div className="flex items-center justify-between p-2 rounded-md bg-blue-50 border border-blue-100 text-xs">
                            <div className="flex items-center space-x-2">
                              <StatusBadge status={issueMetrics.currentStatus} />
                              <span className="text-[10px] font-bold uppercase text-blue-600">Current</span>
                            </div>
                            <span className="text-gray-500 font-mono text-[10px]" title={issueMetrics.isResolved ? issueMetrics.resolvedAt || undefined : issueMetrics.currentStatusSince}>
                              {issueMetrics.isResolved
                                ? `${issueMetrics.currentStatus}, resolved at ${formatDateTime(issueMetrics.resolvedAt)}`
                                : `since ${formatDateTime(issueMetrics.currentStatusSince)}`}
                            </span>
                          </div>
                        </div>
                      </div>
                    </>
                  )}
                </div>
              )}
            </div>

          </div>

          {/* RIGHT COLUMN: Details Sidebar (Status transitions, Assignee, Estimate, Dates, Custom Fields) */}
          <div className="w-72 bg-[#FAFBFC] overflow-y-auto p-5 space-y-5 text-xs">
            
            {/* Status Transition Control (J-08 & J-20) */}
            <div>
              <label className="block text-[11px] font-bold text-gray-400 uppercase tracking-wider mb-1.5">
                Status & Transitions (J-08/20)
              </label>
              
              <div className="space-y-1.5">
                <div className="p-2 bg-white rounded border border-gray-200 flex items-center justify-between">
                  <span className="text-xs text-gray-500">Current:</span>
                  <StatusBadge status={issue.status} />
                </div>

                {canEdit && (
                  <div className="mt-2">
                    <span className="text-[10px] text-gray-400 block mb-1">Permitted Transitions:</span>
                    <div className="space-y-1">
                      {allowedTransitions.map(tr => (
                        <button
                          key={tr.name}
                          onClick={() => handleTransition(tr.to_status)}
                          className="w-full text-left px-2.5 py-1.5 bg-white hover:bg-blue-50 border border-gray-200 hover:border-blue-300 rounded text-xs text-gray-800 flex items-center justify-between transition group"
                        >
                          <span className="font-medium group-hover:text-[#0052CC]">{tr.name}</span>
                          <span className="text-[10px] text-gray-400 font-mono">→ {tr.to_status}</span>
                        </button>
                      ))}
                      {allowedTransitions.length === 0 && (
                        <div className="text-[11px] text-gray-400 italic">No available transitions from this status.</div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Assignee (J-02) */}
            <div>
              <label className="block text-[11px] font-bold text-gray-400 uppercase tracking-wider mb-1.5">
                Assignee (J-02)
              </label>
              <select
                disabled={!canEdit}
                value={issue.assignee_id || ''}
                onChange={e => handleAssigneeChange(e.target.value)}
                className="w-full px-2.5 py-1.5 bg-white border border-gray-300 rounded text-xs text-gray-800 outline-none focus:ring-1 focus:ring-blue-500 disabled:bg-gray-100"
              >
                <option value="">Unassigned</option>
                {eligibleUsers.map(u => (
                  <option key={u.id} value={u.id}>
                    {u.name} ({u.role})
                  </option>
                ))}
              </select>
            </div>

            {/* Reporter */}
            <div>
              <label className="block text-[11px] font-bold text-gray-400 uppercase tracking-wider mb-1.5">
                Reporter
              </label>
              <div className="flex items-center space-x-2 px-2.5 py-1.5 bg-white rounded border border-gray-200">
                <img src={issue.reporter_avatar} alt={issue.reporter_name} className="w-5 h-5 rounded-full object-cover" />
                <span className="text-gray-800">{issue.reporter_name}</span>
              </div>
            </div>

            {/* Story Points (J-06) */}
            <div>
              <label className="block text-[11px] font-bold text-gray-400 uppercase tracking-wider mb-1.5">
                Story Points (J-06)
              </label>
              <input
                type="number"
                min="0"
                disabled={!canEdit}
                value={issue.story_points ?? ''}
                onChange={e => handlePointsChange(e.target.value)}
                placeholder="None"
                className="w-full px-2.5 py-1.5 bg-white border border-gray-300 rounded text-xs text-gray-800 outline-none focus:ring-1 focus:ring-blue-500 disabled:bg-gray-100"
              />
            </div>

            {/* Sprint (J-07) */}
            <div>
              <label className="block text-[11px] font-bold text-gray-400 uppercase tracking-wider mb-1.5">
                Sprint (J-07)
              </label>
              <select
                disabled={!canEdit}
                value={issue.sprint_id || ''}
                onChange={e => handleSprintChange(e.target.value)}
                className="w-full px-2.5 py-1.5 bg-white border border-gray-300 rounded text-xs text-gray-800 outline-none focus:ring-1 focus:ring-blue-500 disabled:bg-gray-100"
              >
                <option value="">Backlog (No Sprint)</option>
                {sprints.map(s => (
                  <option key={s.id} value={s.id}>{s.name} ({s.state})</option>
                ))}
              </select>
            </div>

            {/* Release Version (J-18) */}
            <div>
              <label className="block text-[11px] font-bold text-gray-400 uppercase tracking-wider mb-1.5">
                Release Version (J-18)
              </label>
              <select
                disabled={!canEdit}
                value={issue.version_id || ''}
                onChange={e => handleVersionChange(e.target.value)}
                className="w-full px-2.5 py-1.5 bg-white border border-gray-300 rounded text-xs text-gray-800 outline-none focus:ring-1 focus:ring-blue-500 disabled:bg-gray-100"
              >
                <option value="">None</option>
                {versions.map(v => (
                  <option key={v.id} value={v.id}>{v.name}</option>
                ))}
              </select>
            </div>

            {/* Dates (J-17) */}
            <div>
              <label className="block text-[11px] font-bold text-gray-400 uppercase tracking-wider mb-1.5">
                Timeline Dates (J-17)
              </label>
              <div className="space-y-2">
                <div>
                  <span className="text-[10px] text-gray-400 block mb-0.5">Start Date</span>
                  <input
                    type="date"
                    disabled={!canEdit}
                    value={issue.start_date || ''}
                    onChange={e => handleDateChange('start', e.target.value)}
                    className="w-full px-2.5 py-1 bg-white border border-gray-300 rounded text-xs text-gray-800 outline-none disabled:bg-gray-100"
                  />
                </div>
                <div>
                  <span className="text-[10px] text-gray-400 block mb-0.5">Due Date</span>
                  <input
                    type="date"
                    disabled={!canEdit}
                    value={issue.due_date || ''}
                    onChange={e => handleDateChange('due', e.target.value)}
                    className="w-full px-2.5 py-1 bg-white border border-gray-300 rounded text-xs text-gray-800 outline-none disabled:bg-gray-100"
                  />
                </div>
              </div>
            </div>

            {/* Custom Fields (J-19) */}
            {issue.customFieldValues && issue.customFieldValues.length > 0 && (
              <div>
                <label className="block text-[11px] font-bold text-gray-400 uppercase tracking-wider mb-1.5">
                  Custom Fields (J-19)
                </label>
                <div className="space-y-2.5">
                  {issue.customFieldValues.map(cf => (
                    <div key={cf.id}>
                      <span className="text-[10px] text-gray-500 font-medium block mb-0.5">{cf.name}</span>
                      {cf.field_type === 'select' && cf.options_json ? (
                        <select
                          disabled={!canEdit}
                          value={cf.value || ''}
                          onChange={e => handleCustomFieldChange(cf.id, e.target.value)}
                          className="w-full px-2.5 py-1 bg-white border border-gray-300 rounded text-xs text-gray-800 outline-none disabled:bg-gray-100"
                        >
                          <option value="">None</option>
                          {JSON.parse(cf.options_json).map((opt: string) => (
                            <option key={opt} value={opt}>{opt}</option>
                          ))}
                        </select>
                      ) : (
                        <input
                          type="text"
                          disabled={!canEdit}
                          value={cf.value || ''}
                          onChange={e => handleCustomFieldChange(cf.id, e.target.value)}
                          className="w-full px-2.5 py-1 bg-white border border-gray-300 rounded text-xs text-gray-800 outline-none disabled:bg-gray-100"
                        />
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Watchers list preview (J-11) */}
            <div>
              <label className="block text-[11px] font-bold text-gray-400 uppercase tracking-wider mb-1.5">
                Watchers ({issue.watchers?.length || 0})
              </label>
              <div className="flex flex-wrap gap-1.5">
                {issue.watchers?.map(w => (
                  <span key={w.id} className="inline-flex items-center space-x-1 px-2 py-0.5 bg-gray-200/70 text-gray-700 rounded text-[11px]">
                    <img src={w.avatar} alt={w.name} className="w-3.5 h-3.5 rounded-full object-cover" />
                    <span>{w.name}</span>
                  </span>
                ))}
              </div>
            </div>

          </div>

        </div>

      </div>
    </div>
  );
};

