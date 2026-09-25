import React from 'react';
import {
  Kanban,
  ListTodo,
  Calendar,
  Network,
  Tag,
  BarChart2,
  LayoutDashboard,
  Filter,
  Settings,
  Zap,
  Sliders,
  ShieldCheck,
  ChevronLeft,
  ChevronRight,
  GitBranch,
  Sparkles,
  Gauge,
  Code2
} from 'lucide-react';
import { useProject } from '../../context/ProjectContext.js';

export type NavTab = 
  | 'board' 
  | 'backlog' 
  | 'timeline' 
  | 'crossteam' 
  | 'releases' 
  | 'burndown' 
  | 'dashboard' 
  | 'filters' 
  | 'settings'
  | 'ai'
  | 'metrics'
  | 'problems';

interface SidebarProps {
  activeTab: NavTab;
  setActiveTab: (tab: NavTab) => void;
  isCollapsed: boolean;
  setIsCollapsed: (collapsed: boolean) => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  activeTab,
  setActiveTab,
  isCollapsed,
  setIsCollapsed
}) => {
  const { currentProject } = useProject();

  const navSections = [
    {
      title: 'Planning',
      items: [
        { id: 'board', label: 'Active Board', icon: Kanban, tag: 'J-08' },
        { id: 'backlog', label: 'Backlog', icon: ListTodo, tag: 'J-05/07' },
        { id: 'problems', label: 'Problem Archive', icon: Code2, tag: 'CP' },
        { id: 'timeline', label: 'Roadmap Timeline', icon: Calendar, tag: 'J-17' },
      ],
    },
    {
      title: 'Enterprise & Delivery',
      items: [
        { id: 'crossteam', label: 'Cross-Team Plan', icon: Network, tag: 'J-24' },
        { id: 'releases', label: 'Releases & Versions', icon: Tag, tag: 'J-18' },
      ],
    },
    {
      title: 'Analytics & Search',
      items: [
        { id: 'burndown', label: 'Sprint Burndown', icon: BarChart2, tag: 'J-15' },
        { id: 'dashboard', label: 'Status Dashboard', icon: LayoutDashboard, tag: 'J-16' },
        { id: 'filters', label: 'Search & Filters', icon: Filter, tag: 'J-13/14' },
      ],
    },
    {
      title: 'AI & Insights',
      items: [
        { id: 'ai', label: 'AI Assistant', icon: Sparkles, tag: 'AI' },
        { id: 'metrics', label: 'Task & Sprint Metrics', icon: Gauge, tag: 'J-30' },
      ],
    },
    {
      title: 'Project Settings',
      items: [
        { id: 'settings', label: 'Workflows & Automation', icon: Settings, tag: 'J-19/22' },
      ],
    },
  ];

  return (
    <aside
      className={`h-[calc(100vh-3.5rem)] bg-[#FAFBFC] border-r border-[#DFE1E6] flex flex-col transition-all duration-200 select-none relative z-20 ${
        isCollapsed ? 'w-16' : 'w-64'
      }`}
    >
      {/* Project Header */}
      <div className="p-4 border-b border-[#DFE1E6] flex items-center justify-between">
        {!isCollapsed && (
          <div className="flex items-center space-x-3 overflow-hidden">
            <div className="w-8 h-8 rounded bg-gradient-to-tr from-blue-700 to-indigo-500 text-white font-bold flex items-center justify-center text-sm shadow-xs shrink-0">
              {currentProject?.key || 'P'}
            </div>
            <div className="overflow-hidden">
              <h2 className="font-semibold text-xs text-[#172B4D] truncate leading-tight">
                {currentProject?.name || 'Project'}
              </h2>
              <span className="text-[10px] text-gray-500">Software Project</span>
            </div>
          </div>
        )}
        {isCollapsed && (
          <div className="w-8 h-8 mx-auto rounded bg-gradient-to-tr from-blue-700 to-indigo-500 text-white font-bold flex items-center justify-center text-sm shadow-xs">
            {currentProject?.key || 'P'}
          </div>
        )}

        {/* Collapse toggle */}
        <button
          onClick={() => setIsCollapsed(!isCollapsed)}
          className={`absolute -right-3 top-5 w-6 h-6 rounded-full bg-white border border-gray-300 flex items-center justify-center text-gray-500 hover:text-gray-800 shadow-xs z-30 transition`}
        >
          {isCollapsed ? <ChevronRight className="w-3.5 h-3.5" /> : <ChevronLeft className="w-3.5 h-3.5" />}
        </button>
      </div>

      {/* Nav List */}
      <div className="flex-1 overflow-y-auto py-3 px-2 space-y-4">
        {navSections.map(sec => (
          <div key={sec.title}>
            {!isCollapsed && (
              <div className="px-3 py-1 text-[11px] font-bold text-gray-400 uppercase tracking-wider">
                {sec.title}
              </div>
            )}
            <div className="space-y-0.5">
              {sec.items.map(item => {
                const Icon = item.icon;
                const isActive = activeTab === item.id;
                return (
                  <button
                    key={item.id}
                    onClick={() => setActiveTab(item.id as NavTab)}
                    className={`w-full flex items-center justify-between px-3 py-2 rounded-md text-xs font-medium transition group ${
                      isActive
                        ? 'bg-[#EBF2FF] text-[#0052CC] font-semibold'
                        : 'text-gray-700 hover:bg-[#EBECF0]'
                    } ${isCollapsed ? 'justify-center px-0' : ''}`}
                    title={item.label}
                  >
                    <div className="flex items-center space-x-3">
                      <Icon
                        className={`w-4 h-4 shrink-0 ${
                          isActive ? 'text-[#0052CC]' : 'text-gray-500 group-hover:text-gray-700'
                        }`}
                      />
                      {!isCollapsed && <span>{item.label}</span>}
                    </div>

                    {!isCollapsed && item.tag && (
                      <span className="text-[9px] px-1.5 py-0.2 bg-gray-200/60 text-gray-600 rounded font-mono">
                        {item.tag}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </aside>
  );
};

