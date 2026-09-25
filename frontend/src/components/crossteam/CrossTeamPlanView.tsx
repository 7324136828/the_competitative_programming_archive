import React, { useState, useEffect } from 'react';
import { Network, AlertTriangle, ArrowRight, ShieldAlert, Layers } from 'lucide-react';
import { api } from '../../api/client.js';
import { CrossTeamDependency } from '../../types/index.js';
import { useProject } from '../../context/ProjectContext.js';
import { StatusBadge } from '../common/Badge.js';

export const CrossTeamPlanView: React.FC = () => {
  const { openIssueDetail, projects } = useProject();
  const [dependencies, setDependencies] = useState<CrossTeamDependency[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    api.getCrossTeamDependencies()
      .then(setDependencies)
      .catch(console.error)
      .finally(() => setIsLoading(false));
  }, []);

  return (
    <div className="flex-1 overflow-y-auto p-6 space-y-6">
      {/* Header */}
      <div>
        <div className="flex items-center space-x-2">
          <h1 className="text-xl font-bold text-[#172B4D]">Cross-Team Dependencies & Advanced Plans</h1>
          <span className="text-xs bg-purple-100 text-purple-800 font-mono px-2 py-0.5 rounded">J-24</span>
        </div>
        <p className="text-xs text-gray-500 mt-0.5">
          Coordinate multi-team delivery and identify upstream/downstream blockers across projects.
        </p>
      </div>

      {/* Projects Overview Cards */}
      <div className="grid grid-cols-2 gap-4">
        {projects.map(p => (
          <div key={p.id} className="p-4 bg-white rounded-xl border border-gray-200 shadow-xs flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <div className="w-9 h-9 rounded-lg bg-gradient-to-tr from-blue-700 to-indigo-600 text-white font-bold flex items-center justify-center text-sm shadow-xs">
                {p.key}
              </div>
              <div>
                <h3 className="font-bold text-xs text-gray-900">{p.name}</h3>
                <span className="text-[11px] text-gray-400">Led by {p.lead_name || 'Alex Chen'}</span>
              </div>
            </div>
            <span className="text-xs px-2.5 py-1 bg-gray-100 rounded-md font-semibold text-gray-700">
              {p.total_issues || 0} work items
            </span>
          </div>
        ))}
      </div>

      {/* Cross-Team Dependency Matrix */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-xs overflow-hidden">
        <div className="px-5 py-3.5 bg-[#FAFBFC] border-b border-gray-200 flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <Network className="w-4 h-4 text-purple-600" />
            <span className="font-bold text-xs text-[#172B4D]">Inter-Team Blockers Matrix</span>
          </div>
          <span className="text-xs font-semibold text-purple-700 bg-purple-50 px-2 py-0.5 rounded border border-purple-200">
            {dependencies.length} Active Blocker(s)
          </span>
        </div>

        <div className="divide-y divide-gray-100">
          {dependencies.map(dep => {
            const isBlocked = dep.source_status !== 'Done';

            return (
              <div key={dep.link_id} className="p-4 hover:bg-gray-50/70 transition flex items-center justify-between">
                
                {/* Source Item (Upstream Dependency) */}
                <div
                  onClick={() => openIssueDetail(dep.source_id)}
                  className="flex-1 p-3 bg-gray-50 hover:bg-blue-50/50 rounded-lg border border-gray-200 cursor-pointer transition text-xs group"
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-[10px] font-bold text-gray-500 uppercase tracking-wider">
                      Upstream: {dep.source_project_name} ({dep.source_project_key})
                    </span>
                    <StatusBadge status={dep.source_status} />
                  </div>
                  <div className="font-semibold text-[#0052CC] font-mono text-[11px] group-hover:underline">
                    {dep.source_key}
                  </div>
                  <div className="text-gray-800 font-medium truncate mt-0.5">{dep.source_summary}</div>
                </div>

                {/* Blocker Arrow Indicator */}
                <div className="px-6 flex flex-col items-center justify-center shrink-0">
                  <div className={`px-2.5 py-1 rounded-full text-[10px] font-bold uppercase tracking-wider flex items-center space-x-1 ${
                    isBlocked ? 'bg-rose-100 text-rose-800 border border-rose-200' : 'bg-emerald-100 text-emerald-800'
                  }`}>
                    {isBlocked ? <AlertTriangle className="w-3 h-3 text-rose-600" /> : null}
                    <span>blocks</span>
                  </div>
                  <ArrowRight className="w-5 h-5 text-gray-400 mt-1" />
                </div>

                {/* Target Item (Downstream Dependent) */}
                <div
                  onClick={() => openIssueDetail(dep.target_id)}
                  className="flex-1 p-3 bg-gray-50 hover:bg-blue-50/50 rounded-lg border border-gray-200 cursor-pointer transition text-xs group"
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-[10px] font-bold text-gray-500 uppercase tracking-wider">
                      Downstream: {dep.target_project_name} ({dep.target_project_key})
                    </span>
                    <StatusBadge status={dep.target_status} />
                  </div>
                  <div className="font-semibold text-[#0052CC] font-mono text-[11px] group-hover:underline">
                    {dep.target_key}
                  </div>
                  <div className="text-gray-800 font-medium truncate mt-0.5">{dep.target_summary}</div>
                </div>

              </div>
            );
          })}

          {dependencies.length === 0 && !isLoading && (
            <div className="p-12 text-center text-xs text-gray-400">
              No cross-team blockers found. All teams can execute without dependency risk.
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

