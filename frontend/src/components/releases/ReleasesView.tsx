import React, { useState, useEffect } from 'react';
import { Tag, Plus, CheckCircle, Clock, Archive } from 'lucide-react';
import { useProject } from '../../context/ProjectContext.js';
import { useAuth } from '../../context/AuthContext.js';
import { api } from '../../api/client.js';
import { Version, Issue } from '../../types/index.js';

export const ReleasesView: React.FC = () => {
  const { currentProject, openIssueDetail, refreshKey, triggerRefresh } = useProject();
  const { canEdit } = useAuth();

  const [versions, setVersions] = useState<Version[]>([]);
  const [selectedVersion, setSelectedVersion] = useState<Version | null>(null);
  const [versionIssues, setVersionIssues] = useState<Issue[]>([]);
  const [isCreating, setIsCreating] = useState(false);
  const [name, setName] = useState('');
  const [desc, setDesc] = useState('');
  const [releaseDate, setReleaseDate] = useState('');

  const loadVersions = async () => {
    if (!currentProject) return;
    try {
      const list = await api.getVersions(currentProject.id);
      setVersions(list);
      if (list.length > 0 && !selectedVersion) {
        setSelectedVersion(list[0]);
      }
    } catch (e) {
      console.error(e);
    }
  };

  useEffect(() => {
    loadVersions();
  }, [currentProject, refreshKey]);

  useEffect(() => {
    if (selectedVersion) {
      api.getIssues({ versionId: selectedVersion.id })
        .then(setVersionIssues)
        .catch(console.error);
    }
  }, [selectedVersion, refreshKey]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!currentProject || !name.trim()) return;
    try {
      await api.createVersion(currentProject.id, {
        name: name.trim(),
        description: desc.trim(),
        releaseDate: releaseDate || null,
      });
      setIsCreating(false);
      setName('');
      setDesc('');
      setReleaseDate('');
      triggerRefresh();
    } catch (e) {
      console.error(e);
    }
  };

  const handleStatusChange = async (verId: string, status: string) => {
    if (!canEdit) return;
    try {
      await api.updateVersionStatus(verId, status);
      triggerRefresh();
    } catch (e) {
      console.error(e);
    }
  };

  return (
    <div className="flex-1 overflow-y-auto p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center space-x-2">
            <h1 className="text-xl font-bold text-[#172B4D]">Releases & Versions</h1>
            <span className="text-xs bg-blue-100 text-blue-800 font-mono px-2 py-0.5 rounded">J-18</span>
          </div>
          <p className="text-xs text-gray-500 mt-0.5">Track version milestones, release readiness, and attached scope</p>
        </div>

        {canEdit && (
          <button
            onClick={() => setIsCreating(true)}
            className="px-3 py-1.5 bg-[#0052CC] hover:bg-[#0065FF] text-white rounded-md text-xs font-semibold shadow-xs flex items-center space-x-1"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>Create version</span>
          </button>
        )}
      </div>

      {/* Inline Create Version Form */}
      {isCreating && (
        <form onSubmit={handleCreate} className="p-4 bg-white rounded-xl border border-blue-200 shadow-sm space-y-3 text-xs">
          <div className="font-semibold text-blue-900">New Release Version</div>
          <div className="grid grid-cols-3 gap-3">
            <input
              type="text"
              required
              autoFocus
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="Version name (e.g. v2.0.0)"
              className="px-3 py-1.5 border border-gray-300 rounded outline-none"
            />
            <input
              type="text"
              value={desc}
              onChange={e => setDesc(e.target.value)}
              placeholder="Release summary / milestone..."
              className="px-3 py-1.5 border border-gray-300 rounded outline-none"
            />
            <input
              type="date"
              value={releaseDate}
              onChange={e => setReleaseDate(e.target.value)}
              className="px-3 py-1.5 border border-gray-300 rounded outline-none"
            />
          </div>
          <div className="flex justify-end space-x-2">
            <button type="button" onClick={() => setIsCreating(false)} className="px-3 py-1 text-gray-500">Cancel</button>
            <button type="submit" className="px-3 py-1 bg-[#0052CC] text-white font-semibold rounded hover:bg-[#0065FF]">Create</button>
          </div>
        </form>
      )}

      {/* Versions List */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {versions.map(ver => {
          const totalPoints = ver.total_points || 0;
          const donePoints = ver.done_points || 0;
          const percent = totalPoints > 0 ? Math.round((donePoints / totalPoints) * 100) : 0;
          const isSelected = selectedVersion?.id === ver.id;

          return (
            <div
              key={ver.id}
              onClick={() => setSelectedVersion(ver)}
              className={`p-5 rounded-xl border cursor-pointer transition shadow-xs ${
                isSelected ? 'bg-white border-[#0052CC] ring-1 ring-blue-500' : 'bg-white border-gray-200 hover:border-gray-300'
              }`}
            >
              <div className="flex items-start justify-between">
                <div>
                  <div className="flex items-center space-x-2">
                    <Tag className="w-4 h-4 text-[#0052CC]" />
                    <h3 className="font-bold text-sm text-gray-900">{ver.name}</h3>
                    <span
                      className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${
                        ver.status === 'released'
                          ? 'bg-emerald-100 text-emerald-800'
                          : (ver.status === 'unreleased' ? 'bg-blue-100 text-blue-800' : 'bg-gray-100 text-gray-600')
                      }`}
                    >
                      {ver.status}
                    </span>
                  </div>
                  {ver.description && <p className="text-xs text-gray-600 mt-1">{ver.description}</p>}
                </div>

                {/* Status action toggle */}
                {canEdit && (
                  <select
                    onClick={e => e.stopPropagation()}
                    value={ver.status}
                    onChange={e => handleStatusChange(ver.id, e.target.value)}
                    className="text-xs bg-gray-50 border border-gray-200 rounded px-2 py-1 outline-none font-semibold text-gray-700"
                  >
                    <option value="unreleased">Unreleased</option>
                    <option value="released">Released</option>
                    <option value="archived">Archived</option>
                  </select>
                )}
              </div>

              {/* Progress bar */}
              <div className="mt-4 space-y-1">
                <div className="flex items-center justify-between text-xs text-gray-600">
                  <span>Release Progress</span>
                  <span className="font-mono font-semibold">{percent}% ({donePoints}/{totalPoints} pts)</span>
                </div>
                <div className="w-full bg-gray-100 rounded-full h-2 overflow-hidden">
                  <div className="bg-emerald-500 h-2 rounded-full transition-all duration-300" style={{ width: `${percent}%` }} />
                </div>
              </div>

              <div className="mt-3 flex items-center justify-between text-[11px] text-gray-400">
                <span>{ver.total_issues || 0} issues associated</span>
                <span>{ver.release_date ? `Target: ${ver.release_date}` : 'No target date'}</span>
              </div>
            </div>
          );
        })}
      </div>

      {/* Selected Version Issue Scope */}
      {selectedVersion && (
        <div className="bg-white rounded-xl border border-gray-200 shadow-xs p-5 space-y-3">
          <div className="flex items-center justify-between border-b border-gray-100 pb-3">
            <h3 className="font-bold text-xs text-gray-800 uppercase tracking-wider">
              Issues in {selectedVersion.name} ({versionIssues.length})
            </h3>
            <span className="text-xs text-gray-500 font-mono">
              Total Points: {versionIssues.reduce((s, i) => s + (Number(i.story_points) || 0), 0)} pts
            </span>
          </div>

          <div className="divide-y divide-gray-100">
            {versionIssues.map(issue => (
              <div
                key={issue.id}
                onClick={() => openIssueDetail(issue.id)}
                className="py-2.5 flex items-center justify-between hover:bg-gray-50 px-2 rounded cursor-pointer transition text-xs"
              >
                <div className="flex items-center space-x-3">
                  <span className="font-semibold text-[#0052CC] font-mono text-[11px]">{issue.key}</span>
                  <span className="text-gray-900">{issue.summary}</span>
                </div>

                <div className="flex items-center space-x-3">
                  <span className="font-mono text-gray-500">{issue.story_points || 0} pts</span>
                  <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-gray-100 text-gray-700">
                    {issue.status}
                  </span>
                </div>
              </div>
            ))}
            {versionIssues.length === 0 && (
              <div className="py-6 text-center text-xs text-gray-400">
                No issues associated with this version yet.
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

