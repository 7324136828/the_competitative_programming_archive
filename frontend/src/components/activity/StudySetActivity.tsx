import React, { useState } from 'react';
import {
  BookOpen,
  ArrowRight,
  ExternalLink,
  CheckCircle2,
  FileQuestion,
  Layers,
  Sparkles,
  Headphones,
  FileText,
} from 'lucide-react';
import confetti from 'canvas-confetti';
import { Issue } from '../../types';
import { api } from '../../api/client';

interface StudySetActivityProps {
  issue: Issue;
  onStatusUpdated?: (newStatus: string) => void;
  onOpenStudySet?: (studySetId: string | null | undefined, targetTab: string) => Promise<void>;
  onClose: () => void;
}

export const StudySetActivity: React.FC<StudySetActivityProps> = ({
  issue,
  onStatusUpdated,
  onOpenStudySet,
}) => {
  const [isUpdatingStatus, setIsUpdatingStatus] = useState(false);
  const [isOpeningStudySet, setIsOpeningStudySet] = useState(false);
  const [navigationError, setNavigationError] = useState<string | null>(null);
  const isDone = issue.status === 'Done';

  const handleLaunchStudySet = async (targetTab = 'home') => {
    setNavigationError(null);
    setIsOpeningStudySet(true);
    try {
      if (!onOpenStudySet) {
        throw new Error('Study set navigation is unavailable. Please try again.');
      }
      await onOpenStudySet(issue.study_set_id, targetTab);
    } catch (error) {
      setNavigationError(error instanceof Error ? error.message : 'Could not open the linked study set.');
    } finally {
      setIsOpeningStudySet(false);
    }
  };

  const handleComplete = async () => {
    setIsUpdatingStatus(true);
    try {
      await api.updateStatus(issue.id, 'Done');
      confetti({
        particleCount: 80,
        spread: 70,
        origin: { y: 0.6 },
      });
      onStatusUpdated?.('Done');
    } catch (err) {
      console.error('Failed to complete study story:', err);
    } finally {
      setIsUpdatingStatus(false);
    }
  };

  const studySetName = issue.study_set?.name || issue.summary;

  return (
    <div className="flex-1 flex flex-col h-full bg-[#18181b] text-gray-100 overflow-y-auto p-6 md:p-8 space-y-6">
      {(!issue.study_set_id || navigationError) && (
        <div role="alert" className="p-3 rounded-lg border border-amber-700 bg-amber-950/40 text-amber-200 text-sm">
          {navigationError || 'No study set is linked to this story.'}
        </div>
      )}
      {/* Hero Header */}
      <div className="p-6 rounded-2xl bg-gradient-to-br from-emerald-950/60 to-gray-900 border border-emerald-800/60 shadow-xl flex flex-col md:flex-row md:items-center justify-between gap-6">
        <div className="space-y-2 max-w-xl">
          <div className="flex items-center space-x-2 text-emerald-400 font-semibold text-xs tracking-wider uppercase">
            <BookOpen className="w-4 h-4" />
            <span>Interactive Study Set</span>
          </div>
          <h2 className="text-2xl font-bold text-white tracking-tight">{studySetName}</h2>
          <p className="text-sm text-gray-400 leading-relaxed">
            {issue.description ||
              'Explore quizzes, flashcards, mind maps, audio podcasts, and reports tailored for this study module.'}
          </p>
        </div>

        <div className="flex flex-col sm:flex-row items-center gap-3 shrink-0">
          <button
            type="button"
            onClick={() => handleLaunchStudySet('home')}
            disabled={!issue.study_set_id || isOpeningStudySet}
            className="w-full sm:w-auto px-5 py-3 rounded-xl font-bold text-sm bg-emerald-500 hover:bg-emerald-400 disabled:opacity-50 disabled:cursor-not-allowed text-gray-950 shadow-lg shadow-emerald-500/20 transition flex items-center justify-center space-x-2"
          >
            <span>{isOpeningStudySet ? 'Opening study set…' : 'Open in Study Set Tab'}</span>
            <ArrowRight className="w-4 h-4" />
          </button>

          {!isDone && (
            <button
              type="button"
              disabled={isUpdatingStatus}
              onClick={handleComplete}
              className="w-full sm:w-auto px-4 py-3 rounded-xl font-semibold text-xs bg-gray-800 hover:bg-gray-700 border border-gray-700 text-emerald-300 transition flex items-center justify-center space-x-1.5"
            >
              <CheckCircle2 className="w-4 h-4 text-emerald-400" />
              <span>{isUpdatingStatus ? 'Saving...' : 'Mark as Done'}</span>
            </button>
          )}
        </div>
      </div>

      {/* Quick Launch Viewer Grid */}
      <div className="space-y-3">
        <h3 className="text-sm font-bold text-gray-300 tracking-wide uppercase">Direct Learning Tools</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          <button
            type="button"
            onClick={() => handleLaunchStudySet('quizzes')}
            disabled={!issue.study_set_id || isOpeningStudySet}
            className="p-4 text-left rounded-xl bg-gray-900/60 hover:bg-gray-900 border border-gray-800 hover:border-emerald-500/60 transition group flex flex-col justify-between space-y-3"
          >
            <div className="flex items-center justify-between">
              <span className="text-2xl">📝</span>
              <ExternalLink className="w-4 h-4 text-gray-600 group-hover:text-emerald-400 transition" />
            </div>
            <div>
              <h4 className="font-semibold text-sm text-gray-200 group-hover:text-emerald-300">Quizzes</h4>
              <p className="text-xs text-gray-400 mt-1">
                Multiple-choice questions with answer explanations and difficulty tiers.
              </p>
            </div>
          </button>

          <button
            type="button"
            onClick={() => handleLaunchStudySet('flashcards')}
            disabled={!issue.study_set_id || isOpeningStudySet}
            className="p-4 text-left rounded-xl bg-gray-900/60 hover:bg-gray-900 border border-gray-800 hover:border-emerald-500/60 transition group flex flex-col justify-between space-y-3"
          >
            <div className="flex items-center justify-between">
              <span className="text-2xl">🗂️</span>
              <ExternalLink className="w-4 h-4 text-gray-600 group-hover:text-emerald-400 transition" />
            </div>
            <div>
              <h4 className="font-semibold text-sm text-gray-200 group-hover:text-emerald-300">Flashcards</h4>
              <p className="text-xs text-gray-400 mt-1">
                Spaced repetition flip cards with Kokoro text-to-speech audio narration.
              </p>
            </div>
          </button>

          <button
            type="button"
            onClick={() => handleLaunchStudySet('mindmaps')}
            disabled={!issue.study_set_id || isOpeningStudySet}
            className="p-4 text-left rounded-xl bg-gray-900/60 hover:bg-gray-900 border border-gray-800 hover:border-emerald-500/60 transition group flex flex-col justify-between space-y-3"
          >
            <div className="flex items-center justify-between">
              <span className="text-2xl">🧠</span>
              <ExternalLink className="w-4 h-4 text-gray-600 group-hover:text-emerald-400 transition" />
            </div>
            <div>
              <h4 className="font-semibold text-sm text-gray-200 group-hover:text-emerald-300">Mind Maps</h4>
              <p className="text-xs text-gray-400 mt-1">
                Hierarchical interactive tree diagrams showing knowledge structure.
              </p>
            </div>
          </button>

          <button
            type="button"
            onClick={() => handleLaunchStudySet('podcasts')}
            disabled={!issue.study_set_id || isOpeningStudySet}
            className="p-4 text-left rounded-xl bg-gray-900/60 hover:bg-gray-900 border border-gray-800 hover:border-emerald-500/60 transition group flex flex-col justify-between space-y-3"
          >
            <div className="flex items-center justify-between">
              <span className="text-2xl">🎙️</span>
              <ExternalLink className="w-4 h-4 text-gray-600 group-hover:text-emerald-400 transition" />
            </div>
            <div>
              <h4 className="font-semibold text-sm text-gray-200 group-hover:text-emerald-300">Podcasts</h4>
              <p className="text-xs text-gray-400 mt-1">
                Dialogue-based audio lessons generated with dual-speaker Kokoro TTS.
              </p>
            </div>
          </button>

          <button
            type="button"
            onClick={() => handleLaunchStudySet('reports')}
            disabled={!issue.study_set_id || isOpeningStudySet}
            className="p-4 text-left rounded-xl bg-gray-900/60 hover:bg-gray-900 border border-gray-800 hover:border-emerald-500/60 transition group flex flex-col justify-between space-y-3"
          >
            <div className="flex items-center justify-between">
              <span className="text-2xl">📊</span>
              <ExternalLink className="w-4 h-4 text-gray-600 group-hover:text-emerald-400 transition" />
            </div>
            <div>
              <h4 className="font-semibold text-sm text-gray-200 group-hover:text-emerald-300">Reports</h4>
              <p className="text-xs text-gray-400 mt-1">
                In-depth analytical summaries with citation claims and conclusions.
              </p>
            </div>
          </button>

          <button
            type="button"
            onClick={() => handleLaunchStudySet('qanda')}
            disabled={!issue.study_set_id || isOpeningStudySet}
            className="p-4 text-left rounded-xl bg-gray-900/60 hover:bg-gray-900 border border-gray-800 hover:border-emerald-500/60 transition group flex flex-col justify-between space-y-3"
          >
            <div className="flex items-center justify-between">
              <span className="text-2xl">💬</span>
              <ExternalLink className="w-4 h-4 text-gray-600 group-hover:text-emerald-400 transition" />
            </div>
            <div>
              <h4 className="font-semibold text-sm text-gray-200 group-hover:text-emerald-300">Free-text Q&A</h4>
              <p className="text-xs text-gray-400 mt-1">
                Self-evaluation questions with answer history and JSON export.
              </p>
            </div>
          </button>
        </div>
      </div>
    </div>
  );
};
