import React, { useState } from 'react';
import { 
  X, 
  Sparkles, 
  Code2, 
  BookOpen, 
  Cpu, 
  CheckCircle2, 
  AlertCircle, 
  RefreshCw,
  ArrowRight
} from 'lucide-react';
import { useProject } from '../../context/ProjectContext';
import { api } from '../../api/client';
import { StoryType, Issue } from '../../types';

interface AiStoryModalProps {
  isOpen: boolean;
  onClose: () => void;
  onStoryCreated?: (issue: Issue) => void;
}

export const AiStoryModal: React.FC<AiStoryModalProps> = ({
  isOpen,
  onClose,
  onStoryCreated,
}) => {
  const { currentProject, projects, triggerRefresh, openIssueDetail } = useProject();
  const [projectId, setProjectId] = useState<string>(currentProject?.id || projects[0]?.id || '');
  const [storyType, setStoryType] = useState<StoryType>('coding');
  const [difficulty, setDifficulty] = useState<'Easy' | 'Medium' | 'Hard'>('Medium');
  const [title, setTitle] = useState('');
  const [prompt, setPrompt] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [createdIssue, setCreatedIssue] = useState<Issue | null>(null);

  if (!isOpen) return null;

  const handleGenerate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!prompt.trim()) {
      setErrorMsg('Please enter a description or prompt for the story.');
      return;
    }

    setIsGenerating(true);
    setErrorMsg(null);
    setCreatedIssue(null);

    try {
      const res = await api.aiGenerateStory({
        projectId,
        story_type: storyType,
        difficulty,
        title: title.trim() || undefined,
        prompt: prompt.trim(),
      });

      if (res.issue) {
        setCreatedIssue(res.issue);
        triggerRefresh();
        onStoryCreated?.(res.issue);
      } else {
        throw new Error('Server generated story without issue details.');
      }
    } catch (err: any) {
      setErrorMsg(err.message || 'AI Story generation failed.');
    } finally {
      setIsGenerating(false);
    }
  };

  const handleReset = () => {
    setTitle('');
    setPrompt('');
    setCreatedIssue(null);
    setErrorMsg(null);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-xs animate-in fade-in duration-100">
      <div className="bg-white rounded-xl shadow-2xl border border-gray-200 w-full max-w-xl max-h-[90vh] flex flex-col overflow-hidden animate-in zoom-in-95 duration-100 text-gray-800">
        {/* Header */}
        <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <span className="p-2 bg-gradient-to-tr from-amber-500 to-indigo-600 text-white rounded-lg shadow-xs">
              <Sparkles className="w-5 h-5" />
            </span>
            <div>
              <h2 className="font-bold text-base text-[#172B4D]">AI Story Generator</h2>
              <p className="text-xs text-gray-500">Synthesize coding, learning, or system design stories with AI</p>
            </div>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 p-1 rounded-md">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-4 text-xs">
          {errorMsg && (
            <div className="p-3 bg-red-50 border border-red-200 rounded-md flex items-center space-x-2 text-red-700">
              <AlertCircle className="w-4 h-4 shrink-0 text-red-600" />
              <span>{errorMsg}</span>
            </div>
          )}

          {createdIssue ? (
            <div className="p-6 bg-emerald-50 border border-emerald-200 rounded-xl space-y-4 text-center">
              <CheckCircle2 className="w-12 h-12 text-emerald-600 mx-auto" />
              <div>
                <span className="font-mono text-xs font-bold text-emerald-800 bg-emerald-100 px-2 py-0.5 rounded">
                  {createdIssue.key}
                </span>
                <h3 className="text-base font-bold text-emerald-950 mt-1">{createdIssue.summary}</h3>
                <p className="text-xs text-emerald-700 mt-1 line-clamp-3">
                  {createdIssue.description}
                </p>
              </div>

              <div className="pt-2 flex justify-center space-x-3">
                <button
                  onClick={handleReset}
                  className="px-4 py-2 bg-white border border-gray-300 hover:bg-gray-50 text-gray-700 rounded-lg font-semibold"
                >
                  Generate Another
                </button>
                <button
                  onClick={() => {
                    onClose();
                    openIssueDetail(createdIssue.id);
                  }}
                  className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg font-semibold flex items-center space-x-1.5"
                >
                  <span>Open Story</span>
                  <ArrowRight className="w-4 h-4" />
                </button>
              </div>
            </div>
          ) : (
            <form onSubmit={handleGenerate} className="space-y-4">
              {/* Project */}
              <div>
                <label className="block font-semibold text-gray-700 mb-1">Target Project *</label>
                <select
                  value={projectId}
                  onChange={e => setProjectId(e.target.value)}
                  className="w-full px-3 py-2 bg-gray-50 border border-gray-300 rounded-md text-gray-800 text-xs focus:ring-2 focus:ring-blue-500 outline-none"
                >
                  {projects.map(p => (
                    <option key={p.id} value={p.id}>{p.name} ({p.key})</option>
                  ))}
                </select>
              </div>

              {/* Story Type Selector */}
              <div>
                <label className="block font-semibold text-gray-700 mb-1.5">Story Type *</label>
                <div className="grid grid-cols-3 gap-2.5">
                  <button
                    type="button"
                    onClick={() => setStoryType('coding')}
                    className={`p-3 rounded-lg border text-left flex flex-col items-start transition ${
                      storyType === 'coding'
                        ? 'border-blue-600 bg-blue-50/70 text-blue-900 ring-2 ring-blue-100'
                        : 'border-gray-200 hover:bg-gray-50 text-gray-700'
                    }`}
                  >
                    <Code2 className="w-4 h-4 text-blue-600 mb-1" />
                    <span className="font-bold">Coding</span>
                    <span className="text-[10px] text-gray-500 mt-0.5">Algorithm problem & unit tests</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => setStoryType('learning')}
                    className={`p-3 rounded-lg border text-left flex flex-col items-start transition ${
                      storyType === 'learning'
                        ? 'border-indigo-600 bg-indigo-50/70 text-indigo-900 ring-2 ring-indigo-100'
                        : 'border-gray-200 hover:bg-gray-50 text-gray-700'
                    }`}
                  >
                    <BookOpen className="w-4 h-4 text-indigo-600 mb-1" />
                    <span className="font-bold">Learning</span>
                    <span className="text-[10px] text-gray-500 mt-0.5">Concept guide & objectives</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => setStoryType('non-coding')}
                    className={`p-3 rounded-lg border text-left flex flex-col items-start transition ${
                      storyType === 'non-coding'
                        ? 'border-purple-600 bg-purple-50/70 text-purple-900 ring-2 ring-purple-100'
                        : 'border-gray-200 hover:bg-gray-50 text-gray-700'
                    }`}
                  >
                    <Cpu className="w-4 h-4 text-purple-600 mb-1" />
                    <span className="font-bold">Non-Coding</span>
                    <span className="text-[10px] text-gray-500 mt-0.5">System design & architecture</span>
                  </button>
                </div>
              </div>

              {/* Difficulty */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block font-semibold text-gray-700 mb-1">Difficulty</label>
                  <select
                    value={difficulty}
                    onChange={e => setDifficulty(e.target.value as any)}
                    className="w-full px-3 py-2 bg-gray-50 border border-gray-300 rounded-md text-gray-800 text-xs focus:ring-2 focus:ring-blue-500 outline-none"
                  >
                    <option value="Easy">Easy</option>
                    <option value="Medium">Medium</option>
                    <option value="Hard">Hard</option>
                  </select>
                </div>

                <div>
                  <label className="block font-semibold text-gray-700 mb-1">Title (Optional)</label>
                  <input
                    type="text"
                    value={title}
                    onChange={e => setTitle(e.target.value)}
                    placeholder="Auto-generated if left blank"
                    className="w-full px-3 py-2 border border-gray-300 rounded-md text-gray-800 text-xs focus:ring-2 focus:ring-blue-500 outline-none"
                  />
                </div>
              </div>

              {/* Prompt */}
              <div>
                <label className="block font-semibold text-gray-700 mb-1">
                  Topic Prompt / Instructions <span className="text-red-500">*</span>
                </label>
                <textarea
                  rows={4}
                  value={prompt}
                  onChange={e => setPrompt(e.target.value)}
                  placeholder={
                    storyType === 'coding'
                      ? 'e.g. Create a problem on finding the maximum subarray sum with at least one element deleted.'
                      : storyType === 'learning'
                      ? 'e.g. Explain how Dijkstra algorithm works with binary heaps and invariant proofs.'
                      : 'e.g. Design a distributed ID generator capable of 100,000 unique IDs per second with zero collisions.'
                  }
                  className="w-full p-3 border border-gray-300 rounded-md text-gray-800 text-xs focus:ring-2 focus:ring-blue-500 outline-none resize-y"
                />
              </div>

              {/* Actions */}
              <div className="flex items-center justify-end space-x-3 pt-3 border-t border-gray-200">
                <button
                  type="button"
                  onClick={onClose}
                  className="px-4 py-2 text-xs font-semibold text-gray-600 hover:text-gray-800"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isGenerating || !prompt.trim()}
                  className="px-5 py-2 bg-gradient-to-r from-amber-600 to-indigo-600 hover:from-amber-500 hover:to-indigo-500 disabled:opacity-50 text-white rounded-lg text-xs font-semibold flex items-center space-x-2 transition shadow-xs"
                >
                  {isGenerating ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
                  <span>{isGenerating ? 'Synthesizing Story...' : 'Generate Story'}</span>
                </button>
              </div>
            </form>
          )}
        </div>
      </div>
    </div>
  );
};
