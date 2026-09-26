import React, { useState, useEffect, useMemo } from 'react';
import { Gauge, Info } from 'lucide-react';
import { useProject } from '../../context/ProjectContext.js';
import { api } from '../../api/client.js';
import { Sprint, SprintMetrics, ProjectMetrics, ProjectIssueMetricRow } from '../../types/index.js';
import { StatusBadge, TypeIcon } from '../common/Badge.js';
import { formatDuration, formatDateTimeCompact, formatMinutes } from '../../utils/format.js';

const Sec: React.FC<{ seconds: number | null | undefined }> = ({ seconds }) => (
  <span title={seconds === null || seconds === undefined ? undefined : `${seconds}s`} className="whitespace-nowrap">
    {formatDuration(seconds)}
  </span>
);

const Ts: React.FC<{ iso: string | null | undefined }> = ({ iso }) => (
  <span title={iso || undefined} className="whitespace-nowrap">{formatDateTimeCompact(iso)}</span>
);

const Card: React.FC<{ label: string; value: React.ReactNode; sub?: React.ReactNode }> = ({ label, value, sub }) => (
  <div className="p-4 bg-white rounded-xl border border-gray-200 shadow-xs">
    <div className="text-[11px] font-bold text-gray-400 uppercase tracking-wider">{label}</div>
    <div className="text-2xl font-bold text-[#172B4D] mt-1">{value}</div>
    {sub && <div className="text-[11px] text-gray-500 mt-0.5">{sub}</div>}
  </div>
);

const outcomeBadge = (outcome: string) => {
  const map: Record<string, string> = {
    completed: 'bg-emerald-100 text-emerald-800',
    carried_over: 'bg-amber-100 text-amber-800',
    removed: 'bg-red-100 text-red-700',
    in_progress: 'bg-blue-100 text-blue-800',
    todo: 'bg-gray-100 text-gray-600',
  };
  return (
    <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${map[outcome] || 'bg-gray-100 text-gray-600'}`}>
      {outcome.replace('_', ' ')}
    </span>
  );
};

export const MetricsView: React.FC = () => {
  const { currentProject, refreshKey, openIssueDetail } = useProject();
  const [sprints, setSprints] = useState<Sprint[]>([]);
  const [projectMetrics, setProjectMetrics] = useState<ProjectMetrics | null>(null);
  const [sprintMetrics, setSprintMetrics] = useState<SprintMetrics | null>(null);
  const [selectedSprintId, setSelectedSprintId] = useState<string>('');
  const [allIssues, setAllIssues] = useState<ProjectIssueMetricRow[]>([]);
  const [issueFilter, setIssueFilter] = useState<'all' | 'open' | 'resolved'>('all');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!currentProject) return;
    setLoading(true);
    setError(null);
    Promise.all([
      api.getSprints(currentProject.id),
      api.getProjectMetrics(currentProject.id),
      api.getProjectIssueMetrics(currentProject.id),
    ]).then(([spr, pm, rows]) => {
      setSprints(spr);
      setProjectMetrics(pm);
      setAllIssues(rows);
      const active = spr.find((s: Sprint) => s.state === 'active');
      const latestClosed = spr.filter((s: Sprint) => s.state === 'closed').pop();
      const pick = active || latestClosed || spr[0];
      setSelectedSprintId(pick ? pick.id : '');
    }).catch((e: any) => setError(e.message))
      .finally(() => setLoading(false));
  }, [currentProject, refreshKey]);

  useEffect(() => {
    if (!selectedSprintId) { setSprintMetrics(null); return; }
    api.getSprintMetrics(selectedSprintId)
      .then(setSprintMetrics)
      .catch(e => { console.error(e); setSprintMetrics(null); });
  }, [selectedSprintId, refreshKey]);

  const filteredIssues = useMemo(() => allIssues.filter(i =>
    issueFilter === 'all' ? true : issueFilter === 'resolved' ? i.isResolved : !i.isResolved
  ), [allIssues, issueFilter]);

  if (!currentProject) {
    return (
      <div className="flex-1 flex items-center justify-center p-8">
        <div className="text-center text-xs text-gray-400">No project selected.</div>
      </div>
    );
  }

  if (loading) {
    return <div className="p-8 text-center text-xs text-gray-400">Loading metrics...</div>;
  }

  const sm = sprintMetrics;
  const flow = projectMetrics?.flow;
  const vel = projectMetrics?.velocity;

  return (
    <div className="flex-1 overflow-y-auto p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center space-x-2">
            <h1 className="text-xl font-bold text-[#172B4D]">Task & Sprint Metrics</h1>
            <Gauge className="w-4 h-4 text-[#0052CC]" />
          </div>
          <p className="text-xs text-gray-500 mt-0.5">Historical timing and delivery metrics for {currentProject.name}</p>
        </div>
        {sprints.length > 0 && (
          <select
            value={selectedSprintId}
            onChange={e => setSelectedSprintId(e.target.value)}
            className="px-3 py-1.5 bg-white border border-gray-300 rounded-md text-xs font-semibold text-gray-700 outline-none shadow-xs"
          >
            {sprints.map(s => (
              <option key={s.id} value={s.id}>{s.name} ({s.state})</option>
            ))}
          </select>
        )}
      </div>

      {error && <div className="p-3 bg-red-50 border border-red-200 rounded text-xs text-red-700">{error}</div>}

      {/* Project summary cards */}
      <div className="grid grid-cols-3 xl:grid-cols-6 gap-4">
        <Card label="Avg velocity (last 3)" value={vel?.averageVelocityLast3 != null ? `${vel.averageVelocityLast3} pts` : '-'} sub="closed sprints" />
        <Card label="Open issues" value={flow?.openIssues ?? 0} />
        <Card label="Resolved issues" value={flow?.resolvedIssues ?? 0} sub={`${flow?.resolvedLast7Days ?? 0} in 7d / ${flow?.resolvedLast30Days ?? 0} in 30d`} />
        <Card label="Median cycle" value={<Sec seconds={flow?.medianCycleTimeSeconds} />} />
        <Card label="Median lead" value={<Sec seconds={flow?.medianLeadTimeSeconds} />} />
        <Card label="Sprints" value={sprints.length} />
      </div>

      {/* Sprint metrics */}
      {!sm ? (
        <div className="p-8 bg-white rounded-xl border border-gray-200 text-center text-xs text-gray-400">
          {sprints.length === 0
            ? 'No sprints yet for this project. Create and start a sprint to see sprint metrics.'
            : 'Select a sprint to see its metrics.'}
        </div>
      ) : (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-6 gap-4">
            <Card label="Sprint state" value={<span className="capitalize">{sm.state}</span>} sub={sm.name} />
            <Card label="Duration" value={<Sec seconds={sm.durationSeconds} />} sub={`${sm.plannedDurationDays ?? '-'} days planned`} />
            <Card
              label="Committed"
              value={sm.committedPoints != null ? `${sm.committedPoints} pts` : '-'}
              sub={sm.committedIssueCount != null ? `${sm.committedIssueCount} issues` : 'not started'}
            />
            <Card
              label="Scope change"
              value={`+${sm.addedAfterStart.points} / -${sm.removedAfterStart.points}`}
              sub={`${sm.addedAfterStart.issues} added, ${sm.removedAfterStart.issues} removed`}
            />
            <Card label="Completed (velocity)" value={`${sm.completedPoints} pts`} sub={`${sm.completedIssueCount} issues`} />
            <Card
              label="Carried over"
              value={sm.carriedOver ? `${sm.carriedOver.points} pts` : '-'}
              sub={sm.carriedOver ? `${sm.carriedOver.issues} issues` : 'sprint open'}
            />
            <Card label="Completion" value={sm.completionRatePercent != null ? `${sm.completionRatePercent}%` : '-'} sub="of committed points" />
            <Card label="Scope completion" value={`${sm.scopeCompletionPercent ?? 0}%`} sub={`of ${sm.finalScopePoints} pts final scope`} />
            <Card
              label="Cycle time"
              value={<Sec seconds={sm.cycleTime.avg} />}
              sub={sm.cycleTime.min != null ? `med ${formatDuration(sm.cycleTime.median)} · ${formatDuration(sm.cycleTime.min)}–${formatDuration(sm.cycleTime.max)}` : 'no completed issues'}
            />
            <Card
              label="Lead time"
              value={<Sec seconds={sm.leadTime.avg} />}
              sub={sm.leadTime.median != null ? `median ${formatDuration(sm.leadTime.median)}` : undefined}
            />
            <Card label="Active time in sprint" value={<Sec seconds={sm.activeSecondsInSprint} />} sub="In-Progress-category time" />
            <Card label="Logged work" value={formatMinutes(sm.loggedMinutes)} sub="inside sprint window" />
          </div>
          <div className="text-[11px] text-gray-400 -mt-2">
            Started <Ts iso={sm.startedAt} /> · Completed <Ts iso={sm.completedAt} />
          </div>

          {/* Per-task table */}
          <div className="bg-white rounded-xl border border-gray-200 shadow-xs overflow-hidden">
            <div className="px-4 py-3 border-b border-gray-200 text-xs font-bold text-gray-700 uppercase tracking-wider">
              Sprint tasks ({sm.issues.length})
            </div>
            {sm.issues.length === 0 ? (
              <div className="p-6 text-center text-xs text-gray-400">No tasks in this sprint.</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-xs text-left">
                  <thead>
                    <tr className="border-b border-gray-200 text-gray-400 font-semibold">
                      <th className="px-3 py-2">Key</th>
                      <th className="px-3 py-2">Summary</th>
                      <th className="px-3 py-2">Type</th>
                      <th className="px-3 py-2">Status</th>
                      <th className="px-3 py-2">Pts</th>
                      <th className="px-3 py-2">Assignee</th>
                      <th className="px-3 py-2">Outcome</th>
                      <th className="px-3 py-2">Created</th>
                      <th className="px-3 py-2">Started</th>
                      <th className="px-3 py-2">Resolved</th>
                      <th className="px-3 py-2">Cycle</th>
                      <th className="px-3 py-2">Lead</th>
                      <th className="px-3 py-2">Active</th>
                      <th className="px-3 py-2">Logged</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {sm.issues.map(i => (
                      <tr key={i.id} className="hover:bg-gray-50">
                        <td className="px-3 py-2 whitespace-nowrap">
                          <button onClick={() => openIssueDetail(i.key)} className="font-semibold text-[#0052CC] hover:underline">
                            {i.key}
                          </button>
                          {i.addedAfterStart && (
                            <span className="ml-1 px-1 py-0.5 rounded bg-amber-100 text-amber-700 text-[9px] font-bold uppercase" title="Added after sprint start">
                              added
                            </span>
                          )}
                        </td>
                        <td className="px-3 py-2 max-w-[220px] truncate" title={i.summary}>{i.summary}</td>
                        <td className="px-3 py-2"><TypeIcon type={i.type} /></td>
                        <td className="px-3 py-2"><StatusBadge status={i.status} /></td>
                        <td className="px-3 py-2 font-mono">{i.storyPoints ?? '-'}</td>
                        <td className="px-3 py-2">{i.assigneeName || 'Unassigned'}</td>
                        <td className="px-3 py-2">{outcomeBadge(i.outcome)}</td>
                        <td className="px-3 py-2"><Ts iso={i.metrics.createdAt} /></td>
                        <td className="px-3 py-2"><Ts iso={i.metrics.firstStartedAt} /></td>
                        <td className="px-3 py-2"><Ts iso={i.metrics.resolvedAt} /></td>
                        <td className="px-3 py-2"><Sec seconds={i.metrics.cycleTimeSeconds} /></td>
                        <td className="px-3 py-2"><Sec seconds={i.metrics.leadTimeSeconds} /></td>
                        <td className="px-3 py-2"><Sec seconds={i.metrics.activeTimeSeconds} /></td>
                        <td className="px-3 py-2">{formatMinutes(i.metrics.loggedMinutes)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* By assignee */}
          <div className="bg-white rounded-xl border border-gray-200 shadow-xs overflow-hidden">
            <div className="px-4 py-3 border-b border-gray-200 text-xs font-bold text-gray-700 uppercase tracking-wider">
              By assignee
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs text-left">
                <thead>
                  <tr className="border-b border-gray-200 text-gray-400 font-semibold">
                    <th className="px-3 py-2">Assignee</th>
                    <th className="px-3 py-2">Completed issues</th>
                    <th className="px-3 py-2">Completed points</th>
                    <th className="px-3 py-2">Active time in sprint</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100">
                  {sm.byAssignee.map(a => (
                    <tr key={a.assigneeId ?? 'unassigned'} className="hover:bg-gray-50">
                      <td className="px-3 py-2 font-medium text-gray-800">{a.assigneeName}</td>
                      <td className="px-3 py-2">{a.completedIssues}</td>
                      <td className="px-3 py-2">{a.completedPoints}</td>
                      <td className="px-3 py-2"><Sec seconds={a.activeSeconds} /></td>
                    </tr>
                  ))}
                  {sm.byAssignee.length === 0 && (
                    <tr><td colSpan={4} className="px-3 py-4 text-center text-gray-400">No assignee data.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {/* Velocity history */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-xs overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-200 text-xs font-bold text-gray-700 uppercase tracking-wider">
          Sprint velocity history
        </div>
        {sprints.length === 0 ? (
          <div className="p-6 text-center text-xs text-gray-400">No sprints yet.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs text-left">
              <thead>
                <tr className="border-b border-gray-200 text-gray-400 font-semibold">
                  <th className="px-3 py-2">Sprint</th>
                  <th className="px-3 py-2">State</th>
                  <th className="px-3 py-2">Started</th>
                  <th className="px-3 py-2">Completed</th>
                  <th className="px-3 py-2">Committed pts</th>
                  <th className="px-3 py-2">Completed pts</th>
                  <th className="px-3 py-2">Completion</th>
                  <th className="px-3 py-2">Throughput</th>
                  <th className="px-3 py-2">Avg cycle</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {(projectMetrics?.sprints || []).map(s => (
                  <tr key={s.id} className="hover:bg-gray-50 cursor-pointer" onClick={() => setSelectedSprintId(s.id)}>
                    <td className="px-3 py-2 font-medium text-[#0052CC]">{s.name}</td>
                    <td className="px-3 py-2 capitalize">{s.state}</td>
                    <td className="px-3 py-2"><Ts iso={s.startedAt} /></td>
                    <td className="px-3 py-2"><Ts iso={s.completedAt} /></td>
                    <td className="px-3 py-2 font-mono">{s.committedPoints ?? '-'}</td>
                    <td className="px-3 py-2 font-mono">{s.completedPoints}</td>
                    <td className="px-3 py-2">{s.completionRatePercent != null ? `${s.completionRatePercent}%` : '-'}</td>
                    <td className="px-3 py-2">{s.throughput}</td>
                    <td className="px-3 py-2"><Sec seconds={s.avgCycleTimeSeconds} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* All tasks table */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-xs overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-200 flex items-center justify-between">
          <span className="text-xs font-bold text-gray-700 uppercase tracking-wider">All tasks ({filteredIssues.length})</span>
          <div className="flex space-x-1">
            {(['all', 'open', 'resolved'] as const).map(f => (
              <button
                key={f}
                onClick={() => setIssueFilter(f)}
                className={`px-2.5 py-1 rounded text-[11px] font-semibold capitalize transition ${
                  issueFilter === f ? 'bg-[#0052CC] text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                }`}
              >
                {f}
              </button>
            ))}
          </div>
        </div>
        {filteredIssues.length === 0 ? (
          <div className="p-6 text-center text-xs text-gray-400">No tasks match this filter.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs text-left">
              <thead>
                <tr className="border-b border-gray-200 text-gray-400 font-semibold">
                  <th className="px-3 py-2">Key</th>
                  <th className="px-3 py-2">Summary</th>
                  <th className="px-3 py-2">Type</th>
                  <th className="px-3 py-2">Status</th>
                  <th className="px-3 py-2">Created</th>
                  <th className="px-3 py-2">Started</th>
                  <th className="px-3 py-2">Resolved</th>
                  <th className="px-3 py-2">Cycle</th>
                  <th className="px-3 py-2">Lead</th>
                  <th className="px-3 py-2">Active</th>
                  <th className="px-3 py-2">Wait</th>
                  <th className="px-3 py-2">Reopens</th>
                  <th className="px-3 py-2">Logged</th>
                  <th className="px-3 py-2">Est. accuracy</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {filteredIssues.map(i => (
                  <tr key={i.id} className="hover:bg-gray-50">
                    <td className="px-3 py-2 whitespace-nowrap">
                      <button onClick={() => openIssueDetail(i.key)} className="font-semibold text-[#0052CC] hover:underline">
                        {i.key}
                      </button>
                    </td>
                    <td className="px-3 py-2 max-w-[220px] truncate" title={i.summary}>{i.summary}</td>
                    <td className="px-3 py-2"><TypeIcon type={i.type} /></td>
                    <td className="px-3 py-2"><StatusBadge status={i.currentStatus} /></td>
                    <td className="px-3 py-2"><Ts iso={i.createdAt} /></td>
                    <td className="px-3 py-2"><Ts iso={i.firstStartedAt} /></td>
                    <td className="px-3 py-2"><Ts iso={i.resolvedAt} /></td>
                    <td className="px-3 py-2"><Sec seconds={i.cycleTimeSeconds} /></td>
                    <td className="px-3 py-2"><Sec seconds={i.leadTimeSeconds} /></td>
                    <td className="px-3 py-2"><Sec seconds={i.activeTimeSeconds} /></td>
                    <td className="px-3 py-2"><Sec seconds={i.waitTimeSeconds} /></td>
                    <td className="px-3 py-2">{i.reopenCount}</td>
                    <td className="px-3 py-2">{formatMinutes(i.loggedMinutes)}</td>
                    <td className="px-3 py-2">{i.estimateAccuracy != null ? `${Math.round(i.estimateAccuracy * 100)}%` : '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div className="flex items-start space-x-2 text-[11px] text-gray-400">
        <Info className="w-3.5 h-3.5 shrink-0 mt-0.5" />
        <span>
          All durations are wall-clock time. Cycle = first transition into an In-Progress-category status until resolution.
          Lead = creation until resolution. Active = time spent in In-Progress-category statuses.
        </span>
      </div>
    </div>
  );
};
