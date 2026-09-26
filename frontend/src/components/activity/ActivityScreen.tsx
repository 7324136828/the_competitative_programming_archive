import React, { useEffect, useState } from 'react';
import { 
  X, 
  ArrowLeft, 
  Code2, 
  BookOpen, 
  Cpu, 
  CheckCircle2, 
  Clock, 
  Layers,
  ExternalLink
} from 'lucide-react';
import { Issue } from '../../types';
import { StatusBadge, PriorityIcon } from '../common/Badge';
import { CodingActivity } from './CodingActivity';
import { LearningActivity } from './LearningActivity';
import { NonCodingActivity } from './NonCodingActivity';
import { StudySetActivity } from './StudySetActivity';

export interface ActivityHandlerProps {
  issue: Issue;
  onStatusUpdated?: (newStatus: string) => void;
  onClose: () => void;
}

// Extensible Activity Registry: allows registering new activity types dynamically
export const ACTIVITY_REGISTRY: Record<string, React.ComponentType<ActivityHandlerProps>> = {
  coding: CodingActivity,
  learning: LearningActivity,
  'non-coding': NonCodingActivity,
  study: StudySetActivity,
};

export function registerActivityHandler(type: string, component: React.ComponentType<ActivityHandlerProps>) {
  ACTIVITY_REGISTRY[type] = component;
}

interface ActivityScreenProps {
  issue: Issue | null;
  onClose: () => void;
  onOpenStory?: (issueId: string) => void;
  onCreateStory?: (problemId: number) => Promise<void>;
  onStatusUpdated?: (issueId: string, newStatus: string) => void;
}

export const ActivityScreen: React.FC<ActivityScreenProps> = ({
  issue,
  onClose,
  onOpenStory,
  onCreateStory,
  onStatusUpdated,
}) => {
  const [currentStatus, setCurrentStatus] = useState<string>(issue?.status || 'To Do');
  const [isCreatingStory, setIsCreatingStory] = useState(false);
  const [storyError, setStoryError] = useState<string | null>(null);

  useEffect(() => {
    if (issue) {
      setCurrentStatus(issue.status);
      setIsCreatingStory(false);
      setStoryError(null);
    }
  }, [issue?.id, issue?.status]);

  // Keyboard shortcut to close (Escape)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  if (!issue) return null;

  const storyType = (issue.story_type || 'coding').toLowerCase();
  const ActivityHandler = ACTIVITY_REGISTRY[storyType] || CodingActivity;

  const handleStatusChange = (newStatus: string) => {
    setCurrentStatus(newStatus);
    onStatusUpdated?.(issue.id, newStatus);
  };

  const handleCreateStory = async () => {
    if (!issue.problem_id || !onCreateStory) return;
    setIsCreatingStory(true);
    setStoryError(null);
    try {
      await onCreateStory(issue.problem_id);
    } catch (error) {
      setStoryError(error instanceof Error ? error.message : 'Unable to create a story for this problem.');
      setIsCreatingStory(false);
    }
  };

  return (
    <div data-testid="activity-screen" className="fixed inset-0 z-50 flex flex-col bg-[#141416] text-white animate-in fade-in duration-150">
      {/* Activity Screen Top Navigation Bar */}
      <header className="h-14 px-4 bg-[#1f1f23] border-b border-[#2e2e33] flex items-center justify-between shrink-0 select-none z-30">
        <div className="flex items-center space-x-3 overflow-hidden">
          {/* Back button */}
          <button
            onClick={onClose}
            className="flex items-center space-x-1.5 px-2.5 py-1.5 rounded-lg bg-[#2b2b30] hover:bg-[#38383f] text-gray-300 hover:text-white text-xs font-semibold transition"
            title="Exit Activity Screen (Esc)"
          >
            <ArrowLeft className="w-4 h-4" />
            <span className="hidden sm:inline">Back to Project</span>
          </button>

          {/* Breadcrumbs */}
          <div className="flex items-center space-x-2 text-xs text-gray-400 overflow-hidden">
            {issue.project_key && (
              <>
                <span className="font-semibold text-gray-300">{issue.project_key}</span>
                <span>/</span>
              </>
            )}
            {issue.parent_key && (
              <>
                <span className="font-mono text-indigo-400 bg-indigo-500/10 px-1.5 py-0.5 rounded text-[11px]">
                  {issue.parent_key}
                </span>
                <span>/</span>
              </>
            )}
            <span className="font-mono font-bold text-blue-400">{issue.key}</span>
          </div>

          {/* Summary title */}
          <h1 className="text-xs sm:text-sm font-bold text-gray-100 truncate max-w-xs md:max-w-md lg:max-w-xl">
            {issue.summary}
          </h1>
        </div>

        {/* Badges & Meta */}
        <div className="flex items-center space-x-2 shrink-0">
          {onOpenStory && issue.type === 'Story' && !String(issue.id).startsWith('problem-') && (
            <button
              type="button"
              onClick={() => onOpenStory(issue.id)}
              className="inline-flex items-center space-x-1.5 px-2.5 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold transition"
              title={`Open original story ${issue.key}`}
            >
              <ExternalLink className="w-3.5 h-3.5" />
              <span>Navigate to story</span>
            </button>
          )}
          {onCreateStory && issue.problem_id && String(issue.id).startsWith('problem-') && (
            <button
              type="button"
              onClick={handleCreateStory}
              disabled={isCreatingStory}
              className="inline-flex items-center space-x-1.5 px-2.5 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-60 disabled:cursor-wait text-white text-xs font-semibold transition"
              title="Create a story linked to this problem"
            >
              <BookOpen className="w-3.5 h-3.5" />
              <span>{isCreatingStory ? 'Creating…' : 'Create a story'}</span>
            </button>
          )}
          {storyError && <span className="text-xs text-red-300" role="alert">{storyError}</span>}

          {/* Story Type Badge */}
          {storyType === 'coding' && (
            <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-blue-500/20 text-blue-300 border border-blue-500/30">
              <Code2 className="w-3 h-3" />
              <span>Coding Story</span>
            </span>
          )}
          {storyType === 'learning' && (
            <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
              <BookOpen className="w-3 h-3" />
              <span>Learning Story</span>
            </span>
          )}
          {storyType === 'non-coding' && (
            <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-purple-500/20 text-purple-300 border border-purple-500/30">
              <Cpu className="w-3 h-3" />
              <span>Non-Coding Story</span>
            </span>
          )}

          {/* Difficulty Badge */}
          {issue.difficulty && (
            <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${
              issue.difficulty === 'Easy' ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30' :
              issue.difficulty === 'Hard' ? 'bg-rose-500/20 text-rose-400 border border-rose-500/30' :
              'bg-amber-500/20 text-amber-400 border border-amber-500/30'
            }`}>
              {issue.difficulty}
            </span>
          )}

          {/* Status Badge */}
          <div className="flex items-center space-x-1 px-2 py-1 rounded bg-[#2b2b30] text-xs font-semibold">
            <span className="text-[10px] text-gray-400 uppercase">Status:</span>
            <span className={`font-bold ${
              currentStatus === 'Done' ? 'text-emerald-400' :
              currentStatus === 'In Progress' ? 'text-blue-400' : 'text-gray-300'
            }`}>
              {currentStatus}
            </span>
          </div>

          {/* Close button */}
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-gray-400 hover:text-white hover:bg-[#2b2b30] transition"
            title="Close Activity Screen"
          >
            <X className="w-5 h-5" />
          </button>
        </div>
      </header>

      {/* Main Activity Area */}
      <main className="flex-1 flex overflow-hidden">
        <ActivityHandler
          key={issue.id}
          issue={{ ...issue, status: currentStatus }}
          onStatusUpdated={handleStatusChange}
          onClose={onClose}
        />
      </main>
    </div>
  );
};
