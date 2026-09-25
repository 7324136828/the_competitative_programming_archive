import React, { useState, useEffect } from 'react';
import {
  Plus,
  Play,
  CheckCircle,
  MoreHorizontal,
  ChevronDown,
  ChevronRight,
  ArrowUp,
  ArrowDown,
  GripVertical
} from 'lucide-react';
import confetti from 'canvas-confetti';
import { useProject } from '../../context/ProjectContext.js';
import { useAuth } from '../../context/AuthContext.js';
import { api } from '../../api/client.js';
import { Issue, Sprint } from '../../types/index.js';
import { TypeIcon, PriorityIcon, StatusBadge, StoryTypeBadge } from '../common/Badge.js';

export const BacklogView: React.FC = () => {
  const { currentProject, openIssueDetail, openCreateModal, openActivity, refreshKey, triggerRefresh } = useProject();
  const { canEdit } = useAuth();

  const [sprints, setSprints] = useState<Sprint[]>([]);
  const [issues, setIssues] = useState<Issue[]>([]);
  const [expandedSprints, setExpandedSprints] = useState<Record<string, boolean>>({ backlog: true });
  const [isCreatingSprint, setIsCreatingSprint] = useState(false);
  const [newSprintName, setNewSprintName] = useState('');
  const [newSprintGoal, setNewSprintGoal] = useState('');
  const [backlogPage, setBacklogPage] = useState(1);
  const [backlogTotal, setBacklogTotal] = useState(0);
  const [backlogTotalPages, setBacklogTotalPages] = useState(1);
  const backlogPageSize = 25;

  const loadData = async () => {
    if (!currentProject) return;
    try {
      const [sprintList, sprintIssueList, backlogResult] = await Promise.all([
        api.getSprints(currentProject.id),
        api.getIssues({
          projectId: currentProject.id,
          type: 'Story',
          sprintAssigned: true,
          compact: true,
        }),
        api.getIssues({
          projectId: currentProject.id,
          type: 'Story',
          sprintId: 'none',
          compact: true,
          page: backlogPage,
          limit: backlogPageSize,
        }),
      ]);
      setSprints(sprintList);
      setIssues([...sprintIssueList, ...backlogResult.issues]);
      setBacklogTotal(backlogResult.total);
      setBacklogTotalPages(backlogResult.totalPages);
      if (backlogPage > backlogResult.totalPages) {
        setBacklogPage(backlogResult.totalPages);
      }

      const expandedMap: Record<string, boolean> = { backlog: true };
      sprintList.forEach((s: Sprint) => {
        expandedMap[s.id] = true;
      });
      setExpandedSprints(expandedMap);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    loadData();
  }, [currentProject, refreshKey, backlogPage]);

  useEffect(() => {
    setBacklogPage(1);
  }, [currentProject?.id]);

  const toggleSprintExpand = (sprintId: string) => {
    setExpandedSprints(prev => ({ ...prev, [sprintId]: !prev[sprintId] }));
  };

  // J-05: Reorder rank (move item up or down)
  const handleMoveRank = async (issue: Issue, direction: 'up' | 'down', list: Issue[]) => {
    if (!canEdit) return;
    const currentIndex = list.findIndex(i => i.id === issue.id);
    if (currentIndex === -1) return;

    const targetIndex = direction === 'up' ? currentIndex - 1 : currentIndex + 1;
    if (targetIndex < 0 || targetIndex >= list.length) return;

    const targetIssue = list[targetIndex];
    // Calculate new rank
    let newRank: number;
    if (direction === 'up') {
      const prevIssue = targetIndex > 0 ? list[targetIndex - 1] : null;
      newRank = prevIssue ? (prevIssue.rank + targetIssue.rank) / 2 : targetIssue.rank - 1.0;
    } else {
      const nextIssue = targetIndex < list.length - 1 ? list[targetIndex + 1] : null;
      newRank = nextIssue ? (targetIssue.rank + nextIssue.rank) / 2 : targetIssue.rank + 1.0;
    }

    try {
      await api.reorderRank(issue.id, newRank);
      triggerRefresh();
    } catch (e) {
      console.error(e);
    }
  };

  // J-06: Inline Story Points update
  const handleUpdatePoints = async (e: React.MouseEvent, issue: Issue) => {
    e.stopPropagation();
    if (!canEdit) return;
    const input = prompt(`Update Story Points for ${issue.key}:`, issue.story_points?.toString() || '');
    if (input === null) return;
    const points = input.trim() === '' ? null : Number(input);
    if (points !== null && (isNaN(points) || points < 0)) {
      alert('Story points must be a valid non-negative number.');
      return;
    }
    try {
      await api.setStoryPoints(issue.id, points);
      triggerRefresh();
    } catch (err: any) {
      alert(err.message);
    }
  };

  // J-07: Move issue to sprint
  const handleMoveToSprint = async (issueId: string, sprintId: string | null) => {
    if (!canEdit) return;
    try {
      await api.setSprint(issueId, sprintId);
      triggerRefresh();
    } catch (e) {
      console.error(e);
    }
  };

  // Create sprint
  const handleCreateSprint = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!currentProject || !newSprintName.trim()) return;
    try {
      await api.createSprint(currentProject.id, {
        name: newSprintName.trim(),
        goal: newSprintGoal.trim(),
      });
      setIsCreatingSprint(false);
      setNewSprintName('');
      setNewSprintGoal('');
      triggerRefresh();
    } catch (e) {
      console.error(e);
    }
  };

  // Start sprint
  const handleStartSprint = async (sprintId: string) => {
    if (!canEdit) return;
    try {
      await api.startSprint(sprintId);
      triggerRefresh();
    } catch (e: any) {
      alert(e.message || 'Failed to start sprint');
    }
  };

  // Complete sprint
  const handleCompleteSprint = async (sprintId: string) => {
    if (!canEdit) return;
    if (confirm('Complete this sprint? Unfinished work will be moved back to the backlog.')) {
      try {
        await api.completeSprint(sprintId, { moveIncompleteToNextSprint: false });
        confetti({ particleCount: 100, spread: 70, origin: { y: 0.6 } });
        triggerRefresh();
      } catch (e: any) {
        alert(e.message || 'Failed to complete sprint');
      }
    }
  };

  const activeSprint = sprints.find(s => s.state === 'active');
  const plannedSprints = sprints.filter(s => s.state === 'planned');
  const backlogIssues = issues.filter(i => !i.sprint_id && i.type !== 'Subtask');

  const renderIssueRow = (issue: Issue, index: number, list: Issue[]) => (
    <div
      key={issue.id}
      onClick={() => openIssueDetail(issue.id)}
      className="group flex items-center justify-between px-3 py-2 bg-white hover:bg-[#F4F5F7] border-b border-gray-100 cursor-pointer transition text-xs select-none"
    >
      <div className="flex items-center space-x-3 min-w-0">
        {/* Reordering Controls (J-05) */}
        {canEdit && (
          <div className="flex items-center space-x-0.5 opacity-0 group-hover:opacity-100 transition" onClick={e => e.stopPropagation()}>
            <button
              onClick={() => handleMoveRank(issue, 'up', list)}
              disabled={index === 0}
              className="p-1 hover:bg-gray-200 rounded text-gray-400 hover:text-gray-700 disabled:opacity-20"
              title="Move up in rank (J-05)"
            >
              <ArrowUp className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => handleMoveRank(issue, 'down', list)}
              disabled={index === list.length - 1}
              className="p-1 hover:bg-gray-200 rounded text-gray-400 hover:text-gray-700 disabled:opacity-20"
              title="Move down in rank (J-05)"
            >
              <ArrowDown className="w-3.5 h-3.5" />
            </button>
          </div>
        )}

        <TypeIcon type={issue.type} />
        {issue.story_type && <StoryTypeBadge storyType={issue.story_type} />}
        <span className="font-semibold text-gray-500 hover:text-[#0052CC] shrink-0 font-mono text-[11px]">
          {issue.key}
        </span>
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            openActivity(issue);
          }}
          className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-blue-50 hover:bg-blue-100 text-[#0052CC] transition shrink-0"
          title="Open Activity Screen"
        >
          Activity ↗
        </button>
        <span className="text-gray-900 font-medium truncate">{issue.summary}</span>
      </div>

      <div className="flex items-center space-x-3 shrink-0 ml-4">
        {/* Sprint Mover (J-07) */}
        {canEdit && (
          <select
            onClick={e => e.stopPropagation()}
            value={issue.sprint_id || ''}
            onChange={e => handleMoveToSprint(issue.id, e.target.value || null)}
            className="text-[10px] bg-transparent hover:bg-gray-100 border border-transparent hover:border-gray-300 rounded px-1 py-0.5 text-gray-600 outline-none"
          >
            <option value="">Backlog</option>
            {sprints.filter(s => s.state !== 'closed').map(s => (
              <option key={s.id} value={s.id}>{s.name}</option>
            ))}
          </select>
        )}

        {/* Priority */}
        <PriorityIcon priority={issue.priority} />

        {/* Story Points (J-06) */}
        <button
          onClick={e => handleUpdatePoints(e, issue)}
          className={`w-6 h-5 rounded-full flex items-center justify-center font-bold text-[10px] transition ${
            issue.story_points !== null && issue.story_points !== undefined
              ? 'bg-gray-200 text-gray-800 hover:bg-blue-200 hover:text-blue-800'
              : 'border border-dashed border-gray-300 text-gray-400 hover:border-blue-400'
          }`}
          title="Click to record Story Points estimate (J-06)"
        >
          {issue.story_points !== null && issue.story_points !== undefined ? issue.story_points : '-'}
        </button>

        {/* Status */}
        <StatusBadge status={issue.status} />

        {/* Assignee Avatar */}
        {issue.assignee_avatar ? (
          <img src={issue.assignee_avatar} alt={issue.assignee_name} className="w-5 h-5 rounded-full object-cover" title={issue.assignee_name} />
        ) : (
          <div className="w-5 h-5 rounded-full bg-gray-200 border border-gray-300 flex items-center justify-center text-[9px] text-gray-500 font-bold" title="Unassigned">
            ?
          </div>
        )}
      </div>
    </div>
  );

  return (
    <div className="flex-1 overflow-y-auto p-6 space-y-6">
      
      {/* Top Controls */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-[#172B4D]">Backlog</h1>
          <p className="text-xs text-gray-500 mt-0.5">All stories are planned here; unsprinted work is paged below.</p>
        </div>

        {canEdit && (
          <div className="flex items-center space-x-2">
            <button
              onClick={() => setIsCreatingSprint(true)}
              className="px-3 py-1.5 bg-white border border-gray-300 hover:bg-gray-50 rounded-md text-xs font-semibold text-gray-700 shadow-xs transition"
            >
              Create sprint
            </button>
            <button
              onClick={() => openCreateModal()}
              className="px-3 py-1.5 bg-[#0052CC] hover:bg-[#0065FF] text-white rounded-md text-xs font-semibold shadow-xs transition"
            >
              Create issue
            </button>
          </div>
        )}
      </div>

      {/* Inline Create Sprint Form */}
      {isCreatingSprint && (
        <form onSubmit={handleCreateSprint} className="p-4 bg-white rounded-xl border border-blue-200 shadow-sm space-y-3 animate-in fade-in duration-100">
          <div className="font-semibold text-xs text-blue-900">New Sprint</div>
          <div className="grid grid-cols-2 gap-3 text-xs">
            <input
              type="text"
              autoFocus
              required
              value={newSprintName}
              onChange={e => setNewSprintName(e.target.value)}
              placeholder="Sprint name (e.g. Sprint 16 - Scalability)"
              className="px-3 py-1.5 border border-gray-300 rounded outline-none focus:ring-1 focus:ring-blue-500"
            />
            <input
              type="text"
              value={newSprintGoal}
              onChange={e => setNewSprintGoal(e.target.value)}
              placeholder="Sprint goal..."
              className="px-3 py-1.5 border border-gray-300 rounded outline-none focus:ring-1 focus:ring-blue-500"
            />
          </div>
          <div className="flex justify-end space-x-2">
            <button type="button" onClick={() => setIsCreatingSprint(false)} className="px-3 py-1 text-xs text-gray-500">Cancel</button>
            <button type="submit" className="px-3 py-1 bg-[#0052CC] text-white text-xs font-semibold rounded hover:bg-[#0065FF]">Create Sprint</button>
          </div>
        </form>
      )}

      {/* ACTIVE SPRINT */}
      {activeSprint && (
        <div className="bg-white rounded-xl border border-gray-200 shadow-xs overflow-hidden">
          <div className="px-4 py-3 bg-[#F4F5F7] border-b border-gray-200 flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <button onClick={() => toggleSprintExpand(activeSprint.id)} className="text-gray-500">
                {expandedSprints[activeSprint.id] ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
              </button>
              <span className="font-bold text-xs text-[#172B4D]">{activeSprint.name}</span>
              <span className="px-2 py-0.5 bg-blue-100 text-[#0052CC] rounded-full text-[10px] font-bold uppercase tracking-wider">
                Active
              </span>
              <span className="text-[11px] text-gray-500 font-normal">
                {issues.filter(i => i.sprint_id === activeSprint.id).length} issues
              </span>
              {activeSprint.goal && (
                <span className="text-[11px] text-gray-400 italic">Goal: {activeSprint.goal}</span>
              )}
            </div>

            <div className="flex items-center space-x-3">
              <span className="text-xs font-semibold text-gray-600">
                {issues
                  .filter(i => i.sprint_id === activeSprint.id)
                  .reduce((sum, i) => sum + (Number(i.story_points) || 0), 0)}{' '}
                pts
              </span>
              {canEdit && (
                <button
                  onClick={() => handleCompleteSprint(activeSprint.id)}
                  className="px-3 py-1 bg-emerald-600 hover:bg-emerald-700 text-white rounded text-xs font-semibold shadow-xs flex items-center space-x-1"
                >
                  <CheckCircle className="w-3.5 h-3.5" />
                  <span>Complete sprint</span>
                </button>
              )}
            </div>
          </div>

          {expandedSprints[activeSprint.id] && (
            <div>
              {issues.filter(i => i.sprint_id === activeSprint.id).length === 0 ? (
                <div className="py-8 text-center text-xs text-gray-400">Plan work into this sprint.</div>
              ) : (
                issues
                  .filter(i => i.sprint_id === activeSprint.id)
                  .map((issue, idx, arr) => renderIssueRow(issue, idx, arr))
              )}
            </div>
          )}
        </div>
      )}

      {/* PLANNED SPRINTS */}
      {plannedSprints.map(s => {
        const sIssues = issues.filter(i => i.sprint_id === s.id);
        const sPoints = sIssues.reduce((sum, i) => sum + (Number(i.story_points) || 0), 0);
        return (
          <div key={s.id} className="bg-white rounded-xl border border-gray-200 shadow-xs overflow-hidden">
            <div className="px-4 py-3 bg-[#FAFBFC] border-b border-gray-200 flex items-center justify-between">
              <div className="flex items-center space-x-3">
                <button onClick={() => toggleSprintExpand(s.id)} className="text-gray-500">
                  {expandedSprints[s.id] ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                </button>
                <span className="font-bold text-xs text-[#172B4D]">{s.name}</span>
                <span className="px-2 py-0.5 bg-gray-200 text-gray-700 rounded-full text-[10px] font-bold uppercase tracking-wider">
                  Planned
                </span>
                <span className="text-[11px] text-gray-500 font-normal">{sIssues.length} issues</span>
                {s.goal && <span className="text-[11px] text-gray-400 italic">Goal: {s.goal}</span>}
              </div>

              <div className="flex items-center space-x-3">
                <span className="text-xs font-semibold text-gray-600">{sPoints} pts</span>
                {canEdit && (
                  <button
                    onClick={() => handleStartSprint(s.id)}
                    className="px-3 py-1 bg-[#0052CC] hover:bg-[#0065FF] text-white rounded text-xs font-semibold shadow-xs flex items-center space-x-1"
                  >
                    <Play className="w-3.5 h-3.5" />
                    <span>Start sprint</span>
                  </button>
                )}
              </div>
            </div>

            {expandedSprints[s.id] && (
              <div>
                {sIssues.length === 0 ? (
                  <div className="py-6 text-center text-xs text-gray-400">
                    No work items planned in this sprint yet. Use dropdown on backlog items to add work.
                  </div>
                ) : (
                  sIssues.map((issue, idx, arr) => renderIssueRow(issue, idx, arr))
                )}
              </div>
            )}
          </div>
        );
      })}

      {/* BACKLOG POOL */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-xs overflow-hidden">
        <div className="px-4 py-3 bg-[#FAFBFC] border-b border-gray-200 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <button onClick={() => toggleSprintExpand('backlog')} className="text-gray-500">
              {expandedSprints['backlog'] ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
            </button>
            <span className="font-bold text-xs text-[#172B4D]">Backlog</span>
            <span className="text-[11px] text-gray-500 font-normal">{backlogTotal} stories</span>
          </div>

          <span className="text-xs font-semibold text-gray-600">
            {backlogIssues.reduce((sum, i) => sum + (Number(i.story_points) || 0), 0)} pts on this page
          </span>
        </div>

        {expandedSprints['backlog'] && (
          <div>
            {backlogIssues.length === 0 ? (
              <div className="py-8 text-center text-xs text-gray-400">Your backlog is clear!</div>
            ) : (
              backlogIssues.map((issue, idx, arr) => renderIssueRow(issue, idx, arr))
            )}
            {backlogTotalPages > 1 && (
              <div className="flex items-center justify-between px-4 py-3 border-t border-gray-200 bg-gray-50 text-xs text-gray-600">
                <span>Page {backlogPage} of {backlogTotalPages}</span>
                <div className="flex items-center space-x-2">
                  <button
                    type="button"
                    disabled={backlogPage <= 1}
                    onClick={() => setBacklogPage(page => Math.max(1, page - 1))}
                    className="px-3 py-1 bg-white border border-gray-300 rounded disabled:opacity-40 hover:bg-gray-100"
                  >
                    Previous
                  </button>
                  <button
                    type="button"
                    disabled={backlogPage >= backlogTotalPages}
                    onClick={() => setBacklogPage(page => Math.min(backlogTotalPages, page + 1))}
                    className="px-3 py-1 bg-white border border-gray-300 rounded disabled:opacity-40 hover:bg-gray-100"
                  >
                    Next
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>

    </div>
  );
};

