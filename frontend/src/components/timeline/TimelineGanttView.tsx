import React, { useState, useEffect } from 'react';
import { Calendar, ChevronLeft, ChevronRight, AlertCircle, Link as LinkIcon } from 'lucide-react';
import { useProject } from '../../context/ProjectContext.js';
import { api } from '../../api/client.js';
import { Issue } from '../../types/index.js';
import { TypeIcon, StatusBadge } from '../common/Badge.js';

export const TimelineGanttView: React.FC = () => {
  const { currentProject, openIssueDetail, refreshKey, triggerRefresh } = useProject();
  const [issues, setIssues] = useState<Issue[]>([]);
  const [currentMonthOffset, setCurrentMonthOffset] = useState(0);

  useEffect(() => {
    if (!currentProject) return;
    api.getIssues({ projectId: currentProject.id }).then(setIssues).catch(console.error);
  }, [currentProject, refreshKey]);

  // Compute 30 days calendar window
  const baseDate = new Date();
  baseDate.setMonth(baseDate.getMonth() + currentMonthOffset);
  const startOfWindow = new Date(baseDate.getFullYear(), baseDate.getMonth(), 1);
  const endOfWindow = new Date(baseDate.getFullYear(), baseDate.getMonth() + 1, 0);
  const totalDays = endOfWindow.getDate();

  const daysArray = Array.from({ length: totalDays }, (_, i) => {
    const d = new Date(startOfWindow.getFullYear(), startOfWindow.getMonth(), i + 1);
    return {
      dayNum: i + 1,
      dateStr: d.toISOString().split('T')[0],
      dayName: d.toLocaleDateString('en-US', { weekday: 'narrow' }),
      isWeekend: d.getDay() === 0 || d.getDay() === 6,
    };
  });

  const scheduledIssues = issues.filter(i => i.start_date && i.due_date);
  const unscheduledIssues = issues.filter(i => !i.start_date || !i.due_date);

  const getBarStyle = (startStr: string, dueStr: string) => {
    const s = new Date(startStr);
    const d = new Date(dueStr);

    const startDiff = Math.max(0, Math.round((s.getTime() - startOfWindow.getTime()) / (1000 * 3600 * 24)));
    const duration = Math.max(1, Math.round((d.getTime() - s.getTime()) / (1000 * 3600 * 24)) + 1);

    const leftPercent = (startDiff / totalDays) * 100;
    const widthPercent = (duration / totalDays) * 100;

    return {
      left: `${Math.min(100, Math.max(0, leftPercent))}%`,
      width: `${Math.min(100 - leftPercent, Math.max(2, widthPercent))}%`,
    };
  };

  return (
    <div className="flex-1 flex flex-col overflow-hidden p-6 space-y-4">
      {/* Header Controls */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-[#172B4D]">Roadmap Timeline</h1>
          <p className="text-xs text-gray-500 mt-0.5">Visualize dated work and delivery schedules (J-17)</p>
        </div>

        {/* Month Navigation */}
        <div className="flex items-center space-x-2 bg-white px-3 py-1.5 rounded-lg border border-gray-200 shadow-xs">
          <button
            onClick={() => setCurrentMonthOffset(m => m - 1)}
            className="p-1 hover:bg-gray-100 rounded text-gray-500"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>
          <span className="text-xs font-semibold text-gray-700 min-w-28 text-center">
            {startOfWindow.toLocaleDateString('en-US', { month: 'long', year: 'numeric' })}
          </span>
          <button
            onClick={() => setCurrentMonthOffset(m => m + 1)}
            className="p-1 hover:bg-gray-100 rounded text-gray-500"
          >
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Main Gantt Grid Container */}
      <div className="flex-1 bg-white rounded-xl border border-gray-200 shadow-xs flex flex-col overflow-hidden">
        
        {/* Days Header */}
        <div className="flex border-b border-gray-200 bg-[#FAFBFC]">
          <div className="w-72 shrink-0 p-3 border-r border-gray-200 text-xs font-bold text-gray-500 uppercase tracking-wider">
            Work Item
          </div>
          <div className="flex-1 grid" style={{ gridTemplateColumns: `repeat(${totalDays}, minmax(0, 1fr))` }}>
            {daysArray.map(day => (
              <div
                key={day.dateStr}
                className={`py-2 text-center border-r border-gray-100 last:border-r-0 ${
                  day.isWeekend ? 'bg-gray-50/60' : ''
                }`}
              >
                <div className="text-[10px] text-gray-400 font-medium">{day.dayName}</div>
                <div className="text-xs font-semibold text-gray-700">{day.dayNum}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Gantt Rows */}
        <div className="flex-1 overflow-y-auto">
          {scheduledIssues.map(issue => {
            const style = getBarStyle(issue.start_date!, issue.due_date!);
            const isDone = issue.status === 'Done';

            return (
              <div
                key={issue.id}
                onClick={() => openIssueDetail(issue.id)}
                className="flex border-b border-gray-100 hover:bg-gray-50/50 cursor-pointer transition group"
              >
                {/* Row Title */}
                <div className="w-72 shrink-0 p-3 border-r border-gray-200 flex items-center justify-between text-xs overflow-hidden">
                  <div className="flex items-center space-x-2 truncate">
                    <TypeIcon type={issue.type} />
                    <span className="font-semibold text-gray-500 font-mono text-[11px]">{issue.key}</span>
                    <span className="text-gray-900 truncate">{issue.summary}</span>
                  </div>
                  <StatusBadge status={issue.status} />
                </div>

                {/* Timeline Bar Track */}
                <div className="flex-1 relative h-12 flex items-center px-1">
                  {/* Grid lines */}
                  <div className="absolute inset-0 grid pointer-events-none" style={{ gridTemplateColumns: `repeat(${totalDays}, minmax(0, 1fr))` }}>
                    {daysArray.map(day => (
                      <div
                        key={day.dateStr}
                        className={`border-r border-gray-100 last:border-r-0 ${day.isWeekend ? 'bg-gray-50/40' : ''}`}
                      />
                    ))}
                  </div>

                  {/* Gantt Bar */}
                  <div
                    style={style}
                    className={`absolute h-7 rounded-md shadow-xs flex items-center px-2 text-[11px] font-semibold text-white overflow-hidden transition-all duration-200 group-hover:brightness-105 ${
                      isDone
                        ? 'bg-emerald-500'
                        : (issue.priority === 'High' || issue.priority === 'Highest' ? 'bg-rose-500' : 'bg-[#0052CC]')
                    }`}
                  >
                    <span className="truncate">{issue.summary}</span>
                  </div>
                </div>
              </div>
            );
          })}

          {scheduledIssues.length === 0 && (
            <div className="p-12 text-center text-xs text-gray-400">
              No scheduled work items in this month. Set Start and Due dates on issues to display them on the timeline.
            </div>
          )}
        </div>

        {/* Unscheduled Issues Drawer */}
        {unscheduledIssues.length > 0 && (
          <div className="p-3 bg-gray-50 border-t border-gray-200 flex items-center justify-between text-xs">
            <span className="text-gray-500">
              <span className="font-semibold text-gray-700">{unscheduledIssues.length}</span> unscheduled issues without dates
            </span>
            <div className="flex items-center space-x-2 overflow-x-auto max-w-xl">
              {unscheduledIssues.slice(0, 4).map(i => (
                <button
                  key={i.id}
                  onClick={() => openIssueDetail(i.id)}
                  className="px-2 py-1 bg-white hover:bg-gray-100 border border-gray-300 rounded text-[11px] text-[#0052CC] font-mono shrink-0"
                >
                  {i.key} (+ dates)
                </button>
              ))}
            </div>
          </div>
        )}

      </div>
    </div>
  );
};

