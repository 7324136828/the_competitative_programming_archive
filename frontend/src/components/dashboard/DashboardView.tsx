import React, { useState, useEffect } from 'react';
import { LayoutDashboard, PieChart, BarChart3, Users, MessageSquare, Clock } from 'lucide-react';
import { useProject } from '../../context/ProjectContext.js';
import { api } from '../../api/client.js';
import { DashboardMetrics } from '../../types/index.js';
import { StatusBadge } from '../common/Badge.js';

export const DashboardView: React.FC = () => {
  const { currentProject, openIssueDetail, refreshKey } = useProject();
  const [metrics, setMetrics] = useState<DashboardMetrics | null>(null);

  useEffect(() => {
    if (!currentProject) { setMetrics(null); return; }
    api.getDashboard(currentProject.id).then(setMetrics).catch(console.error);
  }, [currentProject, refreshKey]);

  if (!currentProject) {
    return (
      <div className="flex-1 flex items-center justify-center p-8">
        <div className="text-center space-y-2">
          <LayoutDashboard className="w-8 h-8 text-gray-300 mx-auto" />
          <div className="text-xs text-gray-400">No project yet. Create a project to see the dashboard.</div>
        </div>
      </div>
    );
  }

  if (!metrics) {
    return <div className="p-8 text-center text-xs text-gray-400">Loading project dashboard...</div>;
  }

  const totalStatusCount = metrics.statusCounts.reduce((acc, s) => acc + s.count, 0) || 1;
  const totalPriorityCount = metrics.priorityCounts.reduce((acc, p) => acc + p.count, 0) || 1;

  return (
    <div className="flex-1 overflow-y-auto p-6 space-y-6">
      {/* Header */}
      <div>
        <div className="flex items-center space-x-2">
          <h1 className="text-xl font-bold text-[#172B4D]">Project Status Dashboard</h1>
          <span className="text-xs bg-blue-100 text-blue-800 font-mono px-2 py-0.5 rounded">J-16</span>
        </div>
        <p className="text-xs text-gray-500 mt-0.5">Real-time status distribution and team capacity widgets</p>
      </div>

      {/* Widgets Grid */}
      <div className="grid grid-cols-2 gap-6">
        
        {/* WIDGET 1: Status Distribution (J-16 primary criterion) */}
        <div className="p-5 bg-white rounded-xl border border-gray-200 shadow-xs space-y-4">
          <div className="flex items-center space-x-2 border-b border-gray-100 pb-3">
            <PieChart className="w-4 h-4 text-[#0052CC]" />
            <h3 className="font-bold text-xs text-gray-800 uppercase tracking-wider">Status Distribution Widget (J-16)</h3>
          </div>

          <div className="space-y-3">
            {metrics.statusCounts.map(st => {
              const percent = Math.round((st.count / totalStatusCount) * 100);
              let barColor = 'bg-slate-400';
              if (st.status === 'In Progress') barColor = 'bg-blue-600';
              if (st.status === 'In Review') barColor = 'bg-purple-600';
              if (st.status === 'Done') barColor = 'bg-emerald-500';

              return (
                <div key={st.status} className="space-y-1">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-semibold text-gray-700">{st.status}</span>
                    <span className="text-gray-500 font-mono">{st.count} ({percent}%)</span>
                  </div>
                  <div className="w-full bg-gray-100 rounded-full h-2 overflow-hidden">
                    <div className={`${barColor} h-2 rounded-full transition-all duration-300`} style={{ width: `${percent}%` }} />
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* WIDGET 2: Priority Breakdown */}
        <div className="p-5 bg-white rounded-xl border border-gray-200 shadow-xs space-y-4">
          <div className="flex items-center space-x-2 border-b border-gray-100 pb-3">
            <BarChart3 className="w-4 h-4 text-rose-600" />
            <h3 className="font-bold text-xs text-gray-800 uppercase tracking-wider">Priority Distribution</h3>
          </div>

          <div className="space-y-3">
            {metrics.priorityCounts.map(pr => {
              const percent = Math.round((pr.count / totalPriorityCount) * 100);
              let barColor = 'bg-yellow-500';
              if (pr.priority === 'High' || pr.priority === 'Highest') barColor = 'bg-rose-500';
              if (pr.priority === 'Low' || pr.priority === 'Lowest') barColor = 'bg-blue-400';

              return (
                <div key={pr.priority} className="space-y-1">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-semibold text-gray-700">{pr.priority}</span>
                    <span className="text-gray-500 font-mono">{pr.count} ({percent}%)</span>
                  </div>
                  <div className="w-full bg-gray-100 rounded-full h-2 overflow-hidden">
                    <div className={`${barColor} h-2 rounded-full transition-all duration-300`} style={{ width: `${percent}%` }} />
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* WIDGET 3: Assignee Workload */}
        <div className="p-5 bg-white rounded-xl border border-gray-200 shadow-xs space-y-4">
          <div className="flex items-center space-x-2 border-b border-gray-100 pb-3">
            <Users className="w-4 h-4 text-emerald-600" />
            <h3 className="font-bold text-xs text-gray-800 uppercase tracking-wider">Assignee Workload</h3>
          </div>

          <div className="space-y-2.5">
            {metrics.assigneeWorkload.map(assignee => (
              <div key={assignee.id} className="p-2.5 bg-gray-50 rounded-lg border border-gray-100 flex items-center justify-between text-xs">
                <div className="flex items-center space-x-2.5">
                  <img src={assignee.avatar} alt={assignee.name} className="w-6 h-6 rounded-full object-cover" />
                  <span className="font-semibold text-gray-800">{assignee.name}</span>
                </div>
                <div className="flex items-center space-x-3">
                  <span className="text-gray-500 font-mono">{assignee.issue_count} open issues</span>
                  <span className="px-2 py-0.5 bg-blue-100 text-blue-800 rounded font-bold font-mono text-[10px]">
                    {assignee.total_points} pts
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* WIDGET 4: Recent Activity Stream */}
        <div className="p-5 bg-white rounded-xl border border-gray-200 shadow-xs space-y-4">
          <div className="flex items-center space-x-2 border-b border-gray-100 pb-3">
            <MessageSquare className="w-4 h-4 text-purple-600" />
            <h3 className="font-bold text-xs text-gray-800 uppercase tracking-wider">Recent Activity Feed</h3>
          </div>

          <div className="space-y-3">
            {metrics.recentComments.map(c => (
              <div key={c.id} className="p-2.5 bg-gray-50 rounded-lg border border-gray-100 text-xs">
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center space-x-1.5 font-semibold text-gray-800">
                    <img src={c.author_avatar} alt={c.author_name} className="w-4 h-4 rounded-full object-cover" />
                    <span>{c.author_name}</span>
                  </div>
                  <span className="font-mono text-[#0052CC] font-semibold text-[10px]">{c.issue_key}</span>
                </div>
                <p className="text-gray-600 line-clamp-1 italic">{c.body}</p>
              </div>
            ))}
            {metrics.recentComments.length === 0 && (
              <div className="text-center py-4 text-xs text-gray-400">No recent activity.</div>
            )}
          </div>
        </div>

      </div>
    </div>
  );
};

