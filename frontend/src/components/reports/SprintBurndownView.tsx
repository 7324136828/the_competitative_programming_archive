import React, { useState, useEffect } from 'react';
import { BarChart2, TrendingDown, Info, Calendar } from 'lucide-react';
import { useProject } from '../../context/ProjectContext.js';
import { api } from '../../api/client.js';
import { Sprint, BurndownData } from '../../types/index.js';

export const SprintBurndownView: React.FC = () => {
  const { currentProject, refreshKey } = useProject();
  const [sprints, setSprints] = useState<Sprint[]>([]);
  const [selectedSprintId, setSelectedSprintId] = useState<string>('');
  const [burndownData, setBurndownData] = useState<BurndownData | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    if (!currentProject) return;
    setIsLoading(true);
    api.getSprints(currentProject.id).then(list => {
      setSprints(list);
      const active = list.find((s: Sprint) => s.state === 'active') || list[0];
      setSelectedSprintId(active ? active.id : '');
      if (!active) setBurndownData(null);
    }).catch(console.error).finally(() => {
      if (!selectedSprintId) setIsLoading(false);
    });
  }, [currentProject, refreshKey]);

  useEffect(() => {
    if (!selectedSprintId) return;
    setIsLoading(true);
    api.getBurndown(selectedSprintId)
      .then(setBurndownData)
      .catch(console.error)
      .finally(() => setIsLoading(false));
  }, [selectedSprintId, refreshKey]);

  if (!burndownData) {
    if (!isLoading && sprints.length === 0) {
      return (
        <div className="flex-1 flex items-center justify-center p-8">
          <div className="text-center space-y-2">
            <BarChart2 className="w-8 h-8 text-gray-300 mx-auto" />
            <div className="text-xs text-gray-400">
              No sprints yet for this project. Create and start a sprint to see the burndown.
            </div>
          </div>
        </div>
      );
    }
    return (
      <div className="p-8 text-center text-xs text-gray-400">Loading sprint burndown...</div>
    );
  }

  // SVG Chart Dimensions
  const width = 600;
  const height = 260;
  const padding = 40;

  const totalPoints = Math.max(1, burndownData.totalPoints);
  const timeline = burndownData.timeline;
  const numDays = Math.max(1, timeline.length - 1);

  const getX = (index: number) => padding + (index / numDays) * (width - 2 * padding);
  const getY = (val: number) => height - padding - (val / totalPoints) * (height - 2 * padding);

  // Build ideal path
  const idealPath = timeline.reduce((acc, point, idx) => {
    const x = getX(idx);
    const y = getY(point.ideal);
    return idx === 0 ? `M ${x} ${y}` : `${acc} L ${x} ${y}`;
  }, '');

  // Build actual path
  const actualPoints = timeline.filter(p => p.actual !== null);
  const actualPath = actualPoints.reduce((acc, point, idx) => {
    const origIdx = timeline.findIndex(t => t.date === point.date);
    const x = getX(origIdx);
    const y = getY(point.actual!);
    return idx === 0 ? `M ${x} ${y}` : `${acc} L ${x} ${y}`;
  }, '');

  return (
    <div className="flex-1 overflow-y-auto p-6 space-y-6">
      {/* Header and Sprint Picker */}
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center space-x-2">
            <h1 className="text-xl font-bold text-[#172B4D]">Sprint Burndown Chart</h1>
            <span className="text-xs bg-blue-100 text-blue-800 font-mono px-2 py-0.5 rounded">J-15</span>
          </div>
          <p className="text-xs text-gray-500 mt-0.5">Track remaining estimated effort across sprint timeline</p>
        </div>

        <select
          value={selectedSprintId}
          onChange={e => setSelectedSprintId(e.target.value)}
          className="px-3 py-1.5 bg-white border border-gray-300 rounded-md text-xs font-semibold text-gray-700 outline-none shadow-xs"
        >
          {sprints.map(s => (
            <option key={s.id} value={s.id}>{s.name} ({s.state})</option>
          ))}
        </select>
      </div>

      {/* Metric Stat Cards */}
      <div className="grid grid-cols-4 gap-4">
        <div className="p-4 bg-white rounded-xl border border-gray-200 shadow-xs">
          <div className="text-[11px] font-bold text-gray-400 uppercase tracking-wider">Total Committed</div>
          <div className="text-2xl font-bold text-[#172B4D] mt-1">{burndownData.totalPoints} pts</div>
          <div className="text-[11px] text-gray-500 mt-0.5">{burndownData.totalIssues} work items</div>
        </div>

        <div className="p-4 bg-white rounded-xl border border-gray-200 shadow-xs">
          <div className="text-[11px] font-bold text-gray-400 uppercase tracking-wider">Completed Work</div>
          <div className="text-2xl font-bold text-emerald-600 mt-1">{burndownData.completedPoints} pts</div>
          <div className="text-[11px] text-emerald-600 font-medium mt-0.5">{burndownData.completedIssues} issues done</div>
        </div>

        <div className="p-4 bg-white rounded-xl border border-gray-200 shadow-xs">
          <div className="text-[11px] font-bold text-gray-400 uppercase tracking-wider">Remaining Work</div>
          <div className="text-2xl font-bold text-[#0052CC] mt-1">{burndownData.remainingPoints} pts</div>
          <div className="text-[11px] text-gray-500 mt-0.5">In progress & review</div>
        </div>

        <div className="p-4 bg-white rounded-xl border border-gray-200 shadow-xs">
          <div className="text-[11px] font-bold text-gray-400 uppercase tracking-wider">Sprint Velocity</div>
          <div className="text-2xl font-bold text-purple-600 mt-1">
            {((burndownData.completedPoints / totalPoints) * 100).toFixed(0)}%
          </div>
          <div className="text-[11px] text-gray-500 mt-0.5">Completion rate</div>
        </div>
      </div>

      {/* SVG Interactive Burndown Graph */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-xs p-6">
        <div className="flex items-center justify-between mb-4">
          <span className="text-xs font-bold text-gray-700 uppercase tracking-wider">Guideline vs Actual Burndown</span>
          
          <div className="flex items-center space-x-5 text-xs">
            <div className="flex items-center space-x-2">
              <span className="w-4 h-0.5 border-t-2 border-dashed border-gray-400" />
              <span className="text-gray-500 font-medium">Ideal Guideline</span>
            </div>
            <div className="flex items-center space-x-2">
              <span className="w-4 h-1 bg-[#0052CC] rounded-full" />
              <span className="text-gray-800 font-bold">Remaining Work</span>
            </div>
          </div>
        </div>

        {/* SVG Canvas */}
        <div className="w-full overflow-x-auto flex justify-center">
          <svg viewBox={`0 0 ${width} ${height}`} className="w-full max-w-2xl h-auto">
            {/* Grid lines */}
            {[0, 0.25, 0.5, 0.75, 1].map(ratio => {
              const y = getY(totalPoints * ratio);
              return (
                <g key={ratio}>
                  <line x1={padding} y1={y} x2={width - padding} y2={y} stroke="#F0F0F2" strokeWidth="1" />
                  <text x={padding - 8} y={y + 3} textAnchor="end" fontSize="10" fill="#9CA3AF" fontFamily="sans-serif">
                    {Math.round(totalPoints * ratio)}
                  </text>
                </g>
              );
            })}

            {/* Ideal Guideline Path */}
            <path d={idealPath} fill="none" stroke="#9CA3AF" strokeWidth="2" strokeDasharray="4 4" />

            {/* Actual Remaining Points Path */}
            <path d={actualPath} fill="none" stroke="#0052CC" strokeWidth="2.5" />

            {/* Actual Data Points */}
            {actualPoints.map(p => {
              const origIdx = timeline.findIndex(t => t.date === p.date);
              const cx = getX(origIdx);
              const cy = getY(p.actual!);
              return (
                <circle key={p.date} cx={cx} cy={cy} r="4" fill="#0052CC" stroke="#FFFFFF" strokeWidth="2">
                  <title>{`${p.date}: ${p.actual} pts remaining`}</title>
                </circle>
              );
            })}
          </svg>
        </div>

        {/* Daily Breakdown Table */}
        <div className="mt-6 border-t border-gray-100 pt-4">
          <div className="text-[11px] font-bold text-gray-500 uppercase tracking-wider mb-2">Daily Progress Record</div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs text-left">
              <thead>
                <tr className="border-b border-gray-200 text-gray-400 font-semibold">
                  <th className="pb-2">Date</th>
                  <th className="pb-2">Ideal Remaining</th>
                  <th className="pb-2">Actual Remaining</th>
                  <th className="pb-2">Burn Variance</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {timeline.map(row => {
                  const variance = row.actual !== null ? (row.actual - row.ideal).toFixed(1) : '-';
                  return (
                    <tr key={row.date} className="hover:bg-gray-50">
                      <td className="py-2 text-gray-700 font-mono text-[11px]">{row.date}</td>
                      <td className="py-2 text-gray-500 font-mono">{row.ideal} pts</td>
                      <td className="py-2 font-bold text-[#0052CC] font-mono">{row.actual !== null ? `${row.actual} pts` : '-'}</td>
                      <td className="py-2 font-mono">
                        {variance === '-' ? '-' : (
                          <span className={Number(variance) > 0 ? 'text-amber-600' : 'text-emerald-600 font-semibold'}>
                            {Number(variance) > 0 ? `+${variance}` : variance} pts
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
};

