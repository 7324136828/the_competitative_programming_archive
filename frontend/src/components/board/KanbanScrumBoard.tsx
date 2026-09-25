import React, { useState, useEffect } from 'react';
import {
  Search,
  Filter,
  AlertCircle,
  CheckCircle2,
  X,
  ChevronDown
} from 'lucide-react';
import { useProject } from '../../context/ProjectContext.js';
import { useAuth } from '../../context/AuthContext.js';
import { api } from '../../api/client.js';
import { Issue, WorkflowStatus } from '../../types/index.js';
import { TypeIcon, PriorityIcon, StoryTypeBadge } from '../common/Badge.js';

export const KanbanScrumBoard: React.FC = () => {
  const { currentProject, openIssueDetail, openActivity, refreshKey, triggerRefresh } = useProject();
  const { currentUser, canEdit } = useAuth();

  const [issues, setIssues] = useState<Issue[]>([]);
  const [statuses, setStatuses] = useState<WorkflowStatus[]>([]);
  const [filterText, setFilterText] = useState('');
  const [onlyMyIssues, setOnlyMyIssues] = useState(false);
  const [draggedIssueId, setDraggedIssueId] = useState<string | null>(null);
  const [dragOverColumn, setDragOverColumn] = useState<string | null>(null);

  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const loadBoardData = async () => {
    if (!currentProject) return;
    try {
      const [wfData, issueList] = await Promise.all([
        api.getWorkflow(currentProject.id),
        api.getIssues({ projectId: currentProject.id }),
      ]);
      setStatuses(wfData.statuses || []);
      setIssues(issueList.filter((i: Issue) => i.type !== 'Subtask'));
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    loadBoardData();
  }, [currentProject, refreshKey]);

  // J-08: Drag-and-drop status update with workflow enforcement
  const handleDragStart = (e: React.DragEvent, issueId: string) => {
    if (!canEdit) return;
    setDraggedIssueId(issueId);
    e.dataTransfer.setData('text/plain', issueId);
  };

  const handleDragOver = (e: React.DragEvent, statusName: string) => {
    e.preventDefault();
    setDragOverColumn(statusName);
  };

  const handleDrop = async (e: React.DragEvent, newStatus: string) => {
    e.preventDefault();
    setDragOverColumn(null);
    const issueId = e.dataTransfer.getData('text/plain') || draggedIssueId;
    if (!issueId) return;

    const issue = issues.find(i => i.id === issueId);
    if (!issue || issue.status === newStatus) return;

    // Enforce coding story submission requirement
    if (newStatus === 'Done' && issue.type === 'Story' && issue.story_type === 'coding' && (issue.submission_status || '').toLowerCase() !== 'accepted') {
      setErrorMessage(`Cannot move coding story "${issue.key}" to "Done". Status depends completely on an Accepted code submission!`);
      setTimeout(() => setErrorMessage(null), 6000);
      setDraggedIssueId(null);
      return;
    }

    try {
      setErrorMessage(null);
      await api.updateStatus(issueId, newStatus);
      triggerRefresh();
    } catch (err: any) {
      // J-08: A transition not permitted by the workflow is rejected with an explanation!
      setErrorMessage(err.message || `Transition from "${issue.status}" to "${newStatus}" is forbidden by workflow.`);
      setTimeout(() => setErrorMessage(null), 5000);
    } finally {
      setDraggedIssueId(null);
    }
  };

  // Filter issues
  const filteredIssues = issues.filter(issue => {
    if (onlyMyIssues && issue.assignee_id !== currentUser?.id) return false;
    if (filterText.trim()) {
      const q = filterText.toLowerCase();
      return (
        issue.key.toLowerCase().includes(q) ||
        issue.summary.toLowerCase().includes(q) ||
        (issue.assignee_name && issue.assignee_name.toLowerCase().includes(q))
      );
    }
    return true;
  });

  const columns = statuses.length > 0 ? statuses : [
    { id: 'todo', name: 'To Do', category: 'TODO', position: 0 },
    { id: 'prog', name: 'In Progress', category: 'IN_PROGRESS', position: 1 },
    { id: 'rev', name: 'In Review', category: 'IN_PROGRESS', position: 2 },
    { id: 'done', name: 'Done', category: 'DONE', position: 3 },
  ];

  return (
    <div className="flex-1 flex flex-col overflow-hidden p-6 space-y-4">
      {/* Header and Filters */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold text-[#172B4D]">Active Board</h1>
          <p className="text-xs text-gray-500 mt-0.5">Kanban & Scrum execution with workflow transition enforcement (J-08)</p>
        </div>

        {/* Filter controls */}
        <div className="flex items-center space-x-3">
          <div className="relative">
            <Search className="w-3.5 h-3.5 absolute left-2.5 top-2.5 text-gray-400" />
            <input
              type="text"
              value={filterText}
              onChange={e => setFilterText(e.target.value)}
              placeholder="Search board..."
              className="pl-8 pr-3 py-1.5 bg-white border border-gray-300 rounded-md text-xs text-gray-800 outline-none focus:ring-1 focus:ring-blue-500 w-44"
            />
          </div>

          <button
            onClick={() => setOnlyMyIssues(!onlyMyIssues)}
            className={`px-3 py-1.5 rounded-md text-xs font-semibold border transition ${
              onlyMyIssues
                ? 'bg-blue-50 border-blue-300 text-[#0052CC]'
                : 'bg-white border-gray-300 text-gray-700 hover:bg-gray-50'
            }`}
          >
            Only my issues
          </button>

          {(filterText || onlyMyIssues) && (
            <button
              onClick={() => {
                setFilterText('');
                setOnlyMyIssues(false);
              }}
              className="text-xs text-gray-500 hover:text-gray-800 underline"
            >
              Clear filters
            </button>
          )}
        </div>
      </div>

      {/* Workflow Error Banner (J-08 rejection feedback) */}
      {errorMessage && (
        <div className="p-3 bg-red-50 border border-red-200 rounded-lg flex items-center justify-between text-xs text-red-700 animate-in fade-in duration-100">
          <div className="flex items-center space-x-2">
            <AlertCircle className="w-4 h-4 text-red-600 shrink-0" />
            <span className="font-medium">{errorMessage}</span>
          </div>
          <button onClick={() => setErrorMessage(null)} className="text-red-500 hover:text-red-700">
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Columns Board */}
      <div className="flex-1 flex space-x-4 overflow-x-auto pb-4">
        {columns.map(col => {
          const colIssues = filteredIssues.filter(i => i.status === col.name);
          const totalColPoints = colIssues.reduce((sum, i) => sum + (Number(i.story_points) || 0), 0);
          const isOver = dragOverColumn === col.name;

          return (
            <div
              key={col.name}
              onDragOver={e => handleDragOver(e, col.name)}
              onDrop={e => handleDrop(e, col.name)}
              className={`w-72 shrink-0 bg-[#F4F5F7] rounded-xl flex flex-col max-h-full border transition-all duration-150 ${
                isOver ? 'border-[#0052CC] bg-blue-50/40 ring-2 ring-blue-100' : 'border-gray-200'
              }`}
            >
              {/* Column Header */}
              <div className="p-3 border-b border-gray-200/80 flex items-center justify-between">
                <div className="flex items-center space-x-2">
                  <span className="text-xs font-bold text-gray-700 uppercase tracking-wider">{col.name}</span>
                  <span className="text-[10px] bg-gray-200 px-1.5 py-0.5 rounded-full text-gray-600 font-bold">
                    {colIssues.length}
                  </span>
                </div>
                <span className="text-[10px] font-semibold text-gray-400 font-mono">{totalColPoints} pts</span>
              </div>

              {/* Column Cards Dropzone */}
              <div className="flex-1 overflow-y-auto p-2.5 space-y-2.5">
                {colIssues.map(issue => (
                  <div
                    key={issue.id}
                    draggable={canEdit}
                    onDragStart={e => handleDragStart(e, issue.id)}
                    onClick={() => openIssueDetail(issue.id)}
                    className={`p-3 bg-white hover:bg-gray-50/90 rounded-lg border border-gray-200 shadow-xs cursor-pointer select-none transition group hover:shadow-sm ${
                      draggedIssueId === issue.id ? 'opacity-40 scale-98 border-dashed border-gray-400' : ''
                    }`}
                  >
                    {/* Badges & Meta */}
                    <div className="flex items-center space-x-1.5 flex-wrap gap-y-1 mb-1.5">
                      {issue.story_type && <StoryTypeBadge storyType={issue.story_type} />}
                      {issue.difficulty && (
                        <span className={`px-1.5 py-0.2 rounded text-[9px] font-bold uppercase ${
                          issue.difficulty === 'Easy' ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' :
                          issue.difficulty === 'Hard' ? 'bg-rose-50 text-rose-700 border border-rose-200' :
                          'bg-amber-50 text-amber-700 border border-amber-200'
                        }`}>
                          {issue.difficulty}
                        </span>
                      )}
                      {issue.submission_status && (
                        <span className={`px-1.5 py-0.2 rounded text-[9px] font-bold ${
                          issue.submission_status.toLowerCase() === 'accepted' ? 'bg-emerald-100 text-emerald-800' : 'bg-blue-50 text-blue-700'
                        }`}>
                          {issue.submission_status}
                        </span>
                      )}
                    </div>

                    {/* Summary */}
                    <div className="text-xs text-gray-900 font-medium line-clamp-2 leading-snug mb-3">
                      {issue.summary}
                    </div>

                    {/* Footer Info */}
                    <div className="flex items-center justify-between pt-1 border-t border-gray-100">
                      <div className="flex items-center space-x-1.5">
                        <TypeIcon type={issue.type} />
                        <span className="text-[11px] font-bold text-gray-500 group-hover:text-[#0052CC] font-mono">
                          {issue.key}
                        </span>

                        {/* Direct Activity Launcher */}
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            openActivity(issue);
                          }}
                          className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-blue-50 hover:bg-blue-100 text-[#0052CC] transition ml-1"
                          title="Open Activity Screen"
                        >
                          Activity ↗
                        </button>
                      </div>

                      <div className="flex items-center space-x-2">
                        <PriorityIcon priority={issue.priority} />
                        
                        {issue.story_points !== null && issue.story_points !== undefined && (
                          <span className="w-4 h-4 bg-gray-100 text-gray-700 rounded-full flex items-center justify-center text-[9px] font-bold">
                            {issue.story_points}
                          </span>
                        )}

                        {issue.assignee_avatar ? (
                          <img
                            src={issue.assignee_avatar}
                            alt={issue.assignee_name}
                            className="w-5 h-5 rounded-full object-cover border border-gray-200"
                            title={issue.assignee_name}
                          />
                        ) : (
                          <div className="w-5 h-5 rounded-full bg-gray-100 text-gray-400 flex items-center justify-center text-[9px] font-bold">
                            ?
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                ))}

                {colIssues.length === 0 && (
                  <div className="h-24 flex items-center justify-center text-[11px] text-gray-400 border border-dashed border-gray-300 rounded-lg">
                    Drop items here
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

