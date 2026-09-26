import React from 'react';
import { 
  Bookmark, 
  CheckSquare, 
  CircleDot, 
  AlertCircle, 
  ChevronUp, 
  ChevronDown, 
  ChevronsUp, 
  ChevronsDown, 
  Minus,
  Layers,
  Sparkles,
  Code2,
  BookOpen,
  FileText
} from 'lucide-react';
import { IssueType, IssuePriority, StoryType } from '../../types/index.js';

export const TypeIcon: React.FC<{ type: IssueType; className?: string }> = ({ type, className = 'w-4 h-4' }) => {
  switch (type) {
    case 'Bug':
      return <CircleDot className={`${className} text-[#E11D48]`} fill="#E11D48" />;
    case 'Story':
      return <Bookmark className={`${className} text-[#10B981]`} fill="#10B981" />;
    case 'Task':
      return <CheckSquare className={`${className} text-[#3B82F6]`} fill="#3B82F6" />;
    case 'Epic':
      return <Layers className={`${className} text-[#8B5CF6]`} fill="#8B5CF6" />;
    case 'Feature':
      return <Sparkles className={`${className} text-[#F59E0B]`} fill="#F59E0B" />;
    case 'Subtask':
      return <CheckSquare className={`${className} text-[#06B6D4]`} />;
    default:
      return <CheckSquare className={`${className} text-[#3B82F6]`} />;
  }
};


export const PriorityIcon: React.FC<{ priority: IssuePriority; className?: string }> = ({ priority, className = 'w-4 h-4' }) => {
  switch (priority) {
    case 'Highest':
      return <ChevronsUp className={`${className} text-[#E11D48]`} />;
    case 'High':
      return <ChevronUp className={`${className} text-[#F97316]`} />;
    case 'Medium':
      return <Minus className={`${className} text-[#EAB308]`} />;
    case 'Low':
      return <ChevronDown className={`${className} text-[#3B82F6]`} />;
    case 'Lowest':
      return <ChevronsDown className={`${className} text-[#64748B]`} />;
    default:
      return <Minus className={`${className} text-[#EAB308]`} />;
  }
};

export const StatusBadge: React.FC<{ status: string }> = ({ status }) => {
  let bg = 'bg-gray-100 text-gray-700 border-gray-300';
  if (status === 'To Do') {
    bg = 'bg-slate-100 text-slate-700 border-slate-300';
  } else if (status === 'In Progress') {
    bg = 'bg-blue-50 text-blue-700 border-blue-200';
  } else if (status === 'In Review') {
    bg = 'bg-purple-50 text-purple-700 border-purple-200';
  } else if (status === 'Done') {
    bg = 'bg-emerald-50 text-emerald-700 border-emerald-200';
  }

  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold uppercase tracking-wider border ${bg}`}>
      {status}
    </span>
  );
};

export const RoleBadge: React.FC<{ role: string }> = ({ role }) => {
  let color = 'bg-blue-100 text-blue-800';
  if (role === 'Admin') color = 'bg-rose-100 text-rose-800 font-semibold';
  if (role === 'Viewer') color = 'bg-amber-100 text-amber-800 font-medium';

  return (
    <span className={`px-2 py-0.5 rounded text-[11px] font-medium ${color}`}>
      {role}
    </span>
  );
};

export const StoryTypeBadge: React.FC<{ storyType?: StoryType; className?: string }> = ({ storyType, className = '' }) => {
  if (!storyType) return null;
  if (storyType === 'coding') {
    return (
      <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[11px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200 ${className}`}>
        <Code2 className="w-3 h-3 text-emerald-600" />
        <span>Coding</span>
      </span>
    );
  }
  if (storyType === 'learning') {
    return (
      <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[11px] font-semibold bg-sky-50 text-sky-700 border border-sky-200 ${className}`}>
        <BookOpen className="w-3 h-3 text-sky-600" />
        <span>Learning</span>
      </span>
    );
  }
  if (storyType === 'study') {
    return (
      <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[11px] font-semibold bg-emerald-50 text-emerald-800 border border-emerald-300 ${className}`}>
        <BookOpen className="w-3 h-3 text-emerald-600" />
        <span>Study</span>
      </span>
    );
  }
  return (
    <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[11px] font-semibold bg-purple-50 text-purple-700 border border-purple-200 ${className}`}>
      <FileText className="w-3 h-3 text-purple-600" />
      <span>Non-Coding</span>
    </span>
  );
};


