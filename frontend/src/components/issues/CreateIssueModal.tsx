import React, { useState, useEffect } from 'react';
import { X, AlertCircle } from 'lucide-react';
import { useProject } from '../../context/ProjectContext.js';
import { useAuth } from '../../context/AuthContext.js';
import { api } from '../../api/client.js';
import { IssueType, IssuePriority, Sprint, Version } from '../../types/index.js';
import { TypeIcon, PriorityIcon } from '../common/Badge.js';

export const CreateIssueModal: React.FC = () => {
  const { isCreateModalOpen, closeCreateModal, currentProject, projects, triggerRefresh, createModalDefaults } = useProject();
  const { users, currentUser } = useAuth();

  const [projectId, setProjectId] = useState(currentProject?.id || projects[0]?.id || '');
  const [type, setType] = useState<IssueType>('Story');
  const [storyType, setStoryType] = useState<'coding' | 'learning' | 'non-coding'>('coding');
  const [difficulty, setDifficulty] = useState<'Easy' | 'Medium' | 'Hard'>('Medium');
  const [parentId, setParentId] = useState<string>('');
  const [parentOptions, setParentOptions] = useState<any[]>([]);
  const [summary, setSummary] = useState('');
  const [description, setDescription] = useState('');
  const [priority, setPriority] = useState<IssuePriority>('Medium');
  const [assigneeId, setAssigneeId] = useState<string>('');
  const [storyPoints, setStoryPoints] = useState<string>('');
  const [sprintId, setSprintId] = useState<string>('');
  const [versionId, setVersionId] = useState<string>('');
  const [startDate, setStartDate] = useState('');
  const [dueDate, setDueDate] = useState('');

  const [sprints, setSprints] = useState<Sprint[]>([]);
  const [versions, setVersions] = useState<Version[]>([]);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (isCreateModalOpen) {
      setProjectId(createModalDefaults?.projectId || currentProject?.id || projects[0]?.id || '');
      setType(createModalDefaults?.type || 'Story');
      setStoryType(createModalDefaults?.story_type || 'coding');
      setDifficulty(createModalDefaults?.difficulty || 'Medium');
      setParentId(createModalDefaults?.parentId || '');
      setSummary(createModalDefaults?.summary || '');
      setDescription('');
      setPriority(createModalDefaults?.priority || 'Medium');
      setAssigneeId(createModalDefaults?.assigneeId || '');
      setStoryPoints(createModalDefaults?.storyPoints ? String(createModalDefaults.storyPoints) : '');
      setSprintId(createModalDefaults?.sprintId || '');
      setVersionId('');
      setStartDate('');
      setDueDate('');
      setErrorMsg(null);
    }
  }, [isCreateModalOpen, currentProject, createModalDefaults]);

  useEffect(() => {
    if (projectId) {
      api.getSprints(projectId).then(setSprints).catch(() => {});
      api.getVersions(projectId).then(setVersions).catch(() => {});
      api.getIssues({ projectId }).then(issues => {
        const potentialParents = issues.filter((i: any) => i.type === 'Epic' || i.type === 'Feature');
        setParentOptions(potentialParents);
      }).catch(() => {});
    }
  }, [projectId]);

  if (!isCreateModalOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!summary.trim()) {
      setErrorMsg('Validation message: Summary is a required field.');
      return;
    }

    setIsSubmitting(true);
    setErrorMsg(null);

    try {
      await api.createIssue({
        projectId,
        type,
        story_type: type === 'Story' ? storyType : undefined,
        difficulty: type === 'Story' && storyType === 'coding' ? difficulty : undefined,
        parentId: parentId || null,
        summary: summary.trim(),
        description,
        priority,
        assigneeId: assigneeId || null,
        storyPoints: storyPoints ? Number(storyPoints) : null,
        sprintId: sprintId || null,
        versionId: versionId || null,
        startDate: startDate || null,
        dueDate: dueDate || null,
      });

      triggerRefresh();
      closeCreateModal();
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to create work item');
    } finally {
      setIsSubmitting(false);
    }
  };

  // Eligible users (exclude Viewers for J-02)
  const eligibleUsers = users.filter(u => u.role !== 'Viewer');

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-xs animate-in fade-in duration-100">
      <div className="bg-white rounded-xl shadow-2xl border border-gray-200 w-full max-w-2xl max-h-[90vh] flex flex-col overflow-hidden animate-in zoom-in-95 duration-100">
        {/* Header */}
        <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <span className="font-bold text-base text-[#172B4D]">Create work item</span>
            <span className="text-xs px-2 py-0.5 bg-blue-100 text-blue-800 rounded font-mono">J-01</span>
          </div>
          <button onClick={closeCreateModal} className="text-gray-400 hover:text-gray-600 p-1 rounded-md">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Form Body */}
        <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto p-6 space-y-4 text-xs">
          {errorMsg && (
            <div className="p-3 bg-red-50 border border-red-200 rounded-md flex items-center space-x-2 text-red-700">
              <AlertCircle className="w-4 h-4 shrink-0 text-red-600" />
              <span>{errorMsg}</span>
            </div>
          )}

          {/* Project & Issue Type */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block font-semibold text-gray-700 mb-1">Project *</label>
              <select
                value={projectId}
                onChange={e => setProjectId(e.target.value)}
                className="w-full px-3 py-2 bg-gray-50 border border-gray-300 rounded-md text-gray-800 text-xs focus:ring-2 focus:ring-blue-500 outline-none"
              >
                {projects.map(p => (
                  <option key={p.id} value={p.id}>{p.name} ({p.key})</option>
                ))}
              </select>
            </div>

            <div>
              <label className="block font-semibold text-gray-700 mb-1">Issue Type *</label>
              <select
                value={type}
                onChange={e => setType(e.target.value as IssueType)}
                className="w-full px-3 py-2 bg-gray-50 border border-gray-300 rounded-md text-gray-800 text-xs focus:ring-2 focus:ring-blue-500 outline-none"
              >
                <option value="Story">Story (Problem / Task)</option>
                <option value="Feature">Feature (Problem Set)</option>
                <option value="Epic">Epic (Set of Problem Sets)</option>
                <option value="Task">Task</option>
                <option value="Bug">Bug</option>
              </select>
            </div>
          </div>

          {/* Story Configuration (if Story) */}
          {type === 'Story' && (
            <div className="grid grid-cols-2 gap-4 p-3 bg-blue-50/50 border border-blue-200/60 rounded-lg">
              <div>
                <label className="block font-semibold text-gray-700 mb-1">Story Type *</label>
                <select
                  value={storyType}
                  onChange={e => setStoryType(e.target.value as any)}
                  className="w-full px-3 py-2 bg-white border border-gray-300 rounded-md text-gray-800 text-xs focus:ring-2 focus:ring-blue-500 outline-none"
                >
                  <option value="coding">Coding Problem (CodeJudge)</option>
                  <option value="learning">Learning Guide & Concepts</option>
                  <option value="non-coding">Non-Coding / System Design</option>
                </select>
              </div>

              {storyType === 'coding' ? (
                <div>
                  <label className="block font-semibold text-gray-700 mb-1">Difficulty</label>
                  <select
                    value={difficulty}
                    onChange={e => setDifficulty(e.target.value as any)}
                    className="w-full px-3 py-2 bg-white border border-gray-300 rounded-md text-gray-800 text-xs focus:ring-2 focus:ring-blue-500 outline-none"
                  >
                    <option value="Easy">Easy</option>
                    <option value="Medium">Medium</option>
                    <option value="Hard">Hard</option>
                  </select>
                </div>
              ) : (
                <div className="flex items-center text-[11px] text-gray-500 pt-5">
                  Extensible interactive activity mode enabled.
                </div>
              )}
            </div>
          )}

          {/* Parent (Epic or Feature) */}
          {parentOptions.length > 0 && (
            <div>
              <label className="block font-semibold text-gray-700 mb-1">Parent (Epic or Feature)</label>
              <select
                value={parentId}
                onChange={e => setParentId(e.target.value)}
                className="w-full px-3 py-2 bg-gray-50 border border-gray-300 rounded-md text-gray-800 text-xs focus:ring-2 focus:ring-blue-500 outline-none"
              >
                <option value="">None (Top Level)</option>
                {parentOptions.map((parent: any) => (
                  <option key={parent.id} value={parent.id}>
                    [{parent.type}] {parent.key}: {parent.summary}
                  </option>
                ))}
              </select>
            </div>
          )}

          {/* Summary */}
          <div>
            <label className="block font-semibold text-gray-700 mb-1">
              Summary <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              required
              value={summary}
              onChange={e => setSummary(e.target.value)}
              placeholder="e.g. Implement OAuth2 Token Introspection"
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-gray-800 text-xs focus:ring-2 focus:ring-blue-500 outline-none"
            />
          </div>

          {/* Description */}
          <div>
            <label className="block font-semibold text-gray-700 mb-1">Description</label>
            <textarea
              rows={4}
              value={description}
              onChange={e => setDescription(e.target.value)}
              placeholder="Provide background, steps to reproduce, or acceptance criteria..."
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-gray-800 text-xs focus:ring-2 focus:ring-blue-500 outline-none resize-y"
            />
          </div>

          {/* Priority & Story Points */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block font-semibold text-gray-700 mb-1">Priority</label>
              <select
                value={priority}
                onChange={e => setPriority(e.target.value as IssuePriority)}
                className="w-full px-3 py-2 bg-gray-50 border border-gray-300 rounded-md text-gray-800 text-xs focus:ring-2 focus:ring-blue-500 outline-none"
              >
                <option value="Highest">Highest</option>
                <option value="High">High</option>
                <option value="Medium">Medium</option>
                <option value="Low">Low</option>
                <option value="Lowest">Lowest</option>
              </select>
            </div>

            <div>
              <label className="block font-semibold text-gray-700 mb-1">Story Points (J-06)</label>
              <input
                type="number"
                min="0"
                step="1"
                value={storyPoints}
                onChange={e => setStoryPoints(e.target.value)}
                placeholder="e.g. 1, 2, 3, 5, 8"
                className="w-full px-3 py-2 border border-gray-300 rounded-md text-gray-800 text-xs focus:ring-2 focus:ring-blue-500 outline-none"
              />
            </div>
          </div>

          {/* Assignee & Sprint */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block font-semibold text-gray-700 mb-1">Assignee (J-02)</label>
              <select
                value={assigneeId}
                onChange={e => setAssigneeId(e.target.value)}
                className="w-full px-3 py-2 bg-gray-50 border border-gray-300 rounded-md text-gray-800 text-xs focus:ring-2 focus:ring-blue-500 outline-none"
              >
                <option value="">Unassigned</option>
                {eligibleUsers.map(u => (
                  <option key={u.id} value={u.id}>{u.name} ({u.role})</option>
                ))}
              </select>
            </div>

            <div>
              <label className="block font-semibold text-gray-700 mb-1">Sprint (J-07)</label>
              <select
                value={sprintId}
                onChange={e => setSprintId(e.target.value)}
                className="w-full px-3 py-2 bg-gray-50 border border-gray-300 rounded-md text-gray-800 text-xs focus:ring-2 focus:ring-blue-500 outline-none"
              >
                <option value="">Backlog (No Sprint)</option>
                {sprints.map(s => (
                  <option key={s.id} value={s.id}>{s.name} ({s.state})</option>
                ))}
              </select>
            </div>
          </div>

          {/* Version & Timeline Dates */}
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="block font-semibold text-gray-700 mb-1">Release Version (J-18)</label>
              <select
                value={versionId}
                onChange={e => setVersionId(e.target.value)}
                className="w-full px-3 py-2 bg-gray-50 border border-gray-300 rounded-md text-gray-800 text-xs focus:ring-2 focus:ring-blue-500 outline-none"
              >
                <option value="">None</option>
                {versions.map(v => (
                  <option key={v.id} value={v.id}>{v.name}</option>
                ))}
              </select>
            </div>

            <div>
              <label className="block font-semibold text-gray-700 mb-1">Start Date (J-17)</label>
              <input
                type="date"
                value={startDate}
                onChange={e => setStartDate(e.target.value)}
                className="w-full px-3 py-1.5 border border-gray-300 rounded-md text-gray-800 text-xs outline-none"
              />
            </div>

            <div>
              <label className="block font-semibold text-gray-700 mb-1">Due Date (J-17)</label>
              <input
                type="date"
                value={dueDate}
                onChange={e => setDueDate(e.target.value)}
                className="w-full px-3 py-1.5 border border-gray-300 rounded-md text-gray-800 text-xs outline-none"
              />
            </div>
          </div>

          {/* Footer Actions */}
          <div className="pt-4 border-t border-gray-200 flex items-center justify-end space-x-3">
            <button
              type="button"
              onClick={closeCreateModal}
              className="px-4 py-2 rounded-md hover:bg-gray-100 text-gray-600 font-medium text-xs transition"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              className="px-5 py-2 rounded-md bg-[#0052CC] hover:bg-[#0065FF] text-white font-semibold text-xs transition disabled:opacity-50"
            >
              {isSubmitting ? 'Creating...' : 'Create'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

