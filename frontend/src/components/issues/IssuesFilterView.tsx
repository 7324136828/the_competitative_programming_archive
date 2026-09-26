import React, { useState, useEffect } from 'react';
import { Search, Filter, Bookmark, Plus, Trash2, ArrowUpDown } from 'lucide-react';
import { useProject } from '../../context/ProjectContext.js';
import { useAuth } from '../../context/AuthContext.js';
import { api } from '../../api/client.js';
import { Issue, SavedFilter } from '../../types/index.js';
import { TypeIcon, PriorityIcon, StatusBadge } from '../common/Badge.js';

export const IssuesFilterView: React.FC = () => {
  const { currentProject, openIssueDetail, refreshKey } = useProject();
  const { users, currentUser } = useAuth();

  const [query, setQuery] = useState('');
  const [assigneeId, setAssigneeId] = useState('');
  const [status, setStatus] = useState('');
  const [statusNot, setStatusNot] = useState('');
  const [priority, setPriority] = useState('');
  const [type, setType] = useState('');
  const [unassigned, setUnassigned] = useState(false);

  const [results, setResults] = useState<Issue[]>([]);
  const [savedFilters, setSavedFilters] = useState<SavedFilter[]>([]);
  const [filterName, setFilterName] = useState('');
  const [isSavingFilter, setIsSavingFilter] = useState(false);

  const loadSavedFilters = async () => {
    try {
      const data = await api.getFilters();
      setSavedFilters(data);
    } catch (e) {}
  };

  const executeSearch = async () => {
    try {
      const filter: Record<string, any> = {
        projectId: currentProject?.id,
        query: query || undefined,
        assigneeId: unassigned ? undefined : (assigneeId || undefined),
        status: status || undefined,
        statusNot: statusNot || undefined,
        priority: priority || undefined,
        type: type || undefined,
        unassigned: unassigned ? true : undefined,
      };
      const data = await api.getIssues(filter);
      setResults(data);
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    loadSavedFilters();
  }, []);

  useEffect(() => {
    executeSearch();
  }, [currentProject, query, assigneeId, status, statusNot, priority, type, unassigned, refreshKey]);

  // J-14: Save filter
  const handleSaveFilter = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!filterName.trim()) return;

    try {
      await api.saveFilter({
        name: filterName.trim(),
        query: {
          query,
          assigneeId,
          status,
          statusNot,
          priority,
          type,
          unassigned,
        },
      });
      setIsSavingFilter(false);
      setFilterName('');
      loadSavedFilters();
    } catch (e) {
      console.error(e);
    }
  };

  // J-14: Apply saved filter
  const handleApplySavedFilter = (sf: SavedFilter) => {
    try {
      const parsed = JSON.parse(sf.query_json);
      setQuery(parsed.query || '');
      setAssigneeId(parsed.assigneeId || '');
      setStatus(parsed.status || '');
      setStatusNot(parsed.statusNot || '');
      setPriority(parsed.priority || '');
      setType(parsed.type || '');
      setUnassigned(!!parsed.unassigned);
    } catch (e) {}
  };

  const handleDeleteSavedFilter = async (id: string) => {
    try {
      await api.deleteFilter(id);
      loadSavedFilters();
    } catch (e) {}
  };

  return (
    <div className="flex-1 flex overflow-hidden">
      
      {/* SAVED FILTERS SIDEBAR (J-14) */}
      <div className="w-64 bg-[#FAFBFC] border-r border-[#DFE1E6] p-4 flex flex-col justify-between select-none">
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-gray-500 uppercase tracking-wider">Saved Filters (J-14)</span>
            <button
              onClick={() => setIsSavingFilter(true)}
              className="text-[#0052CC] hover:text-[#0065FF] p-1 rounded hover:bg-gray-200"
              title="Save current search as reusable filter"
            >
              <Plus className="w-3.5 h-3.5" />
            </button>
          </div>

          {/* Quick presets (J-13) */}
          <div className="space-y-1">
            <button
              onClick={() => {
                setAssigneeId(currentUser?.id || '');
                setStatusNot('Done');
                setStatus('');
                setUnassigned(false);
              }}
              className="w-full text-left px-3 py-1.5 rounded text-xs hover:bg-gray-200 text-gray-700 font-medium transition"
            >
              My Unfinished Work (J-13)
            </button>

            <button
              onClick={() => {
                setQuery('');
                setAssigneeId('');
                setStatus('');
                setStatusNot('');
                setPriority('High');
                setType('Bug');
                setUnassigned(false);
              }}
              className="w-full text-left px-3 py-1.5 rounded text-xs hover:bg-gray-200 text-gray-700 font-medium transition"
            >
              High Priority Bugs
            </button>

            <button
              onClick={() => {
                setQuery('');
                setAssigneeId('');
                setStatus('');
                setStatusNot('');
                setPriority('');
                setType('');
                setUnassigned(true);
              }}
              className="w-full text-left px-3 py-1.5 rounded text-xs hover:bg-gray-200 text-gray-700 font-medium transition"
            >
              Unassigned Issues
            </button>
          </div>

          <div className="border-t border-gray-200 pt-3">
            <span className="text-[11px] font-bold text-gray-400 uppercase tracking-wider block mb-2">Custom Filters</span>
            <div className="space-y-1">
              {savedFilters.map(sf => (
                <div
                  key={sf.id}
                  onClick={() => handleApplySavedFilter(sf)}
                  className="flex items-center justify-between px-3 py-1.5 rounded text-xs hover:bg-gray-200 text-gray-700 cursor-pointer group transition"
                >
                  <div className="flex items-center space-x-2 truncate">
                    <Bookmark className="w-3.5 h-3.5 text-[#0052CC] shrink-0" />
                    <span className="truncate">{sf.name}</span>
                  </div>
                  <button
                    onClick={e => {
                      e.stopPropagation();
                      handleDeleteSavedFilter(sf.id);
                    }}
                    className="opacity-0 group-hover:opacity-100 p-0.5 text-gray-400 hover:text-red-600"
                  >
                    <Trash2 className="w-3 h-3" />
                  </button>
                </div>
              ))}
              {savedFilters.length === 0 && (
                <div className="text-[11px] text-gray-400 italic px-3">No custom saved filters.</div>
              )}
            </div>
          </div>
        </div>

        {/* Save filter modal/form */}
        {isSavingFilter && (
          <form onSubmit={handleSaveFilter} className="p-3 bg-white rounded-lg border border-blue-200 shadow-sm space-y-2 text-xs">
            <div className="font-semibold text-gray-800">Save Filter</div>
            <input
              type="text"
              autoFocus
              required
              value={filterName}
              onChange={e => setFilterName(e.target.value)}
              placeholder="Filter Name..."
              className="w-full px-2 py-1 border border-gray-300 rounded outline-none"
            />
            <div className="flex justify-end space-x-1">
              <button type="button" onClick={() => setIsSavingFilter(false)} className="px-2 py-0.5 text-gray-500">Cancel</button>
              <button type="submit" className="px-2 py-0.5 bg-[#0052CC] text-white font-semibold rounded">Save</button>
            </div>
          </form>
        )}
      </div>

      {/* MAIN SEARCH & RESULTS PANE */}
      <div className="flex-1 flex flex-col overflow-hidden p-6 space-y-4">
        <div>
          <div className="flex items-center space-x-2">
            <h1 className="text-xl font-bold text-[#172B4D]">Search & Filters</h1>
            <span className="text-xs bg-blue-100 text-blue-800 font-mono px-2 py-0.5 rounded">J-13 / J-14</span>
          </div>
          <p className="text-xs text-gray-500 mt-0.5">Filter work items by criteria or recall reusable saved searches</p>
        </div>

        {/* Filter Controls Bar (J-13) */}
        <div className="flex flex-wrap items-center gap-3 bg-white p-3 rounded-xl border border-gray-200 shadow-xs text-xs">
          <div className="relative min-w-48">
            <Search className="w-3.5 h-3.5 absolute left-2.5 top-2 text-gray-400" />
            <input
              type="text"
              value={query}
              onChange={e => setQuery(e.target.value)}
              placeholder="Search keyword..."
              className="pl-8 pr-2 py-1 bg-gray-50 border border-gray-300 rounded text-xs outline-none w-full"
            />
          </div>

          {/* Assignee */}
          <select
            value={unassigned ? 'unassigned' : assigneeId}
            onChange={e => {
              if (e.target.value === 'unassigned') {
                setUnassigned(true);
                setAssigneeId('');
              } else {
                setUnassigned(false);
                setAssigneeId(e.target.value);
              }
            }}
            className="px-2 py-1 bg-gray-50 border border-gray-300 rounded text-xs outline-none"
          >
            <option value="">All Assignees</option>
            <option value="unassigned">Unassigned</option>
            {users.map(u => (
              <option key={u.id} value={u.id}>{u.name}</option>
            ))}
          </select>

          {/* Status */}
          <select
            value={status}
            onChange={e => {
              setStatus(e.target.value);
              setStatusNot('');
            }}
            className="px-2 py-1 bg-gray-50 border border-gray-300 rounded text-xs outline-none"
          >
            <option value="">All Statuses</option>
            <option value="To Do">To Do</option>
            <option value="In Progress">In Progress</option>
            <option value="In Review">In Review</option>
            <option value="Done">Done</option>
          </select>

          {/* Type */}
          <select
            value={type}
            onChange={e => setType(e.target.value)}
            className="px-2 py-1 bg-gray-50 border border-gray-300 rounded text-xs outline-none"
          >
            <option value="">All Types</option>
            <option value="Story">Story</option>
            <option value="Bug">Bug</option>
            <option value="Task">Task</option>
            <option value="Epic">Epic</option>
          </select>

          {/* Priority */}
          <select
            value={priority}
            onChange={e => setPriority(e.target.value)}
            className="px-2 py-1 bg-gray-50 border border-gray-300 rounded text-xs outline-none"
          >
            <option value="">All Priorities</option>
            <option value="Highest">Highest</option>
            <option value="High">High</option>
            <option value="Medium">Medium</option>
            <option value="Low">Low</option>
          </select>

          <button
            onClick={() => {
              setQuery('');
              setAssigneeId('');
              setStatus('');
              setStatusNot('');
              setPriority('');
              setType('');
              setUnassigned(false);
            }}
            className="text-xs text-gray-500 hover:text-gray-800 underline ml-auto"
          >
            Reset
          </button>
        </div>

        {/* Results Table */}
        <div className="flex-1 bg-white rounded-xl border border-gray-200 shadow-xs overflow-hidden flex flex-col">
          <div className="px-4 py-3 bg-[#FAFBFC] border-b border-gray-200 flex items-center justify-between text-xs font-semibold text-gray-500">
            <span>Matching Issues ({results.length})</span>
          </div>

          <div className="flex-1 overflow-y-auto">
            <table className="w-full text-xs text-left">
              <thead>
                <tr className="border-b border-gray-200 bg-gray-50/50 text-gray-400 font-semibold uppercase text-[10px]">
                  <th className="py-2.5 px-4">Key</th>
                  <th className="py-2.5 px-4">Summary</th>
                  <th className="py-2.5 px-4">Status</th>
                  <th className="py-2.5 px-4">Assignee</th>
                  <th className="py-2.5 px-4">Priority</th>
                  <th className="py-2.5 px-4">Points</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {results.map(issue => (
                  <tr
                    key={issue.id}
                    onClick={() => openIssueDetail(issue.id)}
                    className="hover:bg-gray-50 cursor-pointer transition group"
                  >
                    <td className="py-3 px-4 font-mono font-semibold text-[#0052CC] group-hover:underline">
                      <div className="flex items-center space-x-2">
                        <TypeIcon type={issue.type} />
                        <span>{issue.key}</span>
                      </div>
                    </td>
                    <td className="py-3 px-4 text-gray-900 font-medium truncate max-w-md">{issue.summary}</td>
                    <td className="py-3 px-4"><StatusBadge status={issue.status} /></td>
                    <td className="py-3 px-4 text-gray-600">
                      {issue.assignee_avatar ? (
                        <div className="flex items-center space-x-2">
                          <img src={issue.assignee_avatar} alt={issue.assignee_name} className="w-5 h-5 rounded-full object-cover" />
                          <span>{issue.assignee_name}</span>
                        </div>
                      ) : (
                        <span className="text-gray-400 italic">Unassigned</span>
                      )}
                    </td>
                    <td className="py-3 px-4">
                      <div className="flex items-center space-x-1.5">
                        <PriorityIcon priority={issue.priority} />
                        <span>{issue.priority}</span>
                      </div>
                    </td>
                    <td className="py-3 px-4 font-mono font-bold text-gray-700">{issue.story_points ?? '-'}</td>
                  </tr>
                ))}
                {results.length === 0 && (
                  <tr>
                    <td colSpan={6} className="text-center py-12 text-xs text-gray-400">
                      No matching work items found for these search criteria.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

      </div>

    </div>
  );
};

