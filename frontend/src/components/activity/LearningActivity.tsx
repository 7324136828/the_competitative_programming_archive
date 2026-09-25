import React, { useState, useEffect } from 'react';
import { 
  BookOpen, 
  CheckSquare, 
  Square, 
  Volume2, 
  VolumeX, 
  Sparkles, 
  Send, 
  CheckCircle2, 
  FileText, 
  Lightbulb,
  GraduationCap
} from 'lucide-react';
import confetti from 'canvas-confetti';
import RichContent from '../RichContent';
import { Issue } from '../../types';
import { api } from '../../api/client';

interface LearningActivityProps {
  issue: Issue;
  onStatusUpdated?: (newStatus: string) => void;
  onClose: () => void;
}

export const LearningActivity: React.FC<LearningActivityProps> = ({
  issue,
  onStatusUpdated,
  onClose,
}) => {
  const [objectives, setObjectives] = useState<Array<{ id: number; text: string; completed: boolean }>>([]);
  const [notes, setNotes] = useState<string>(() => {
    return localStorage.getItem(`learning_notes_${issue.id}`) || '';
  });
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [aiPrompt, setAiPrompt] = useState('');
  const [aiChat, setAiChat] = useState<Array<{ role: 'user' | 'assistant'; text: string }>>([
    {
      role: 'assistant',
      text: `Hello! I am your AI learning tutor for "${issue.summary}". Ask me anything about this concept, request analogies, or test your understanding with practice questions.`
    }
  ]);
  const [isAiLoading, setIsAiLoading] = useState(false);
  const [isDone, setIsDone] = useState(issue.status === 'Done');

  // Parse or create default learning objectives from description
  useEffect(() => {
    const saved = localStorage.getItem(`learning_obj_${issue.id}`);
    if (saved) {
      try {
        setObjectives(JSON.parse(saved));
        return;
      } catch (e) {}
    }

    // Default objectives based on description lines or summary
    const defaultObj = [
      { id: 1, text: `Understand the fundamental concepts of ${issue.summary}`, completed: false },
      { id: 2, text: 'Review time and space complexity characteristics & trade-offs', completed: false },
      { id: 3, text: 'Analyze edge cases, common pitfalls, and real-world invariants', completed: false },
      { id: 4, text: 'Summarize key takeaways in the study notes section', completed: false },
    ];
    setObjectives(defaultObj);
  }, [issue.id, issue.summary]);

  const toggleObjective = (id: number) => {
    const updated = objectives.map(obj => obj.id === id ? { ...obj, completed: !obj.completed } : obj);
    setObjectives(updated);
    localStorage.setItem(`learning_obj_${issue.id}`, JSON.stringify(updated));
  };

  const handleNotesChange = (text: string) => {
    setNotes(text);
    localStorage.setItem(`learning_notes_${issue.id}`, text);
  };

  // Web Speech API Read Aloud
  const toggleSpeech = () => {
    if (!('speechSynthesis' in window)) {
      alert('Speech synthesis is not supported in this browser.');
      return;
    }
    if (isSpeaking) {
      window.speechSynthesis.cancel();
      setIsSpeaking(false);
    } else {
      const cleanText = `${issue.summary}. ${issue.description || ''}`.replace(/[#*`_~]/g, '');
      const utterance = new SpeechSynthesisUtterance(cleanText);
      utterance.rate = 1.0;
      utterance.onend = () => setIsSpeaking(false);
      utterance.onerror = () => setIsSpeaking(false);
      window.speechSynthesis.speak(utterance);
      setIsSpeaking(true);
    }
  };

  // Stop speaking when leaving
  useEffect(() => {
    return () => {
      if ('speechSynthesis' in window) window.speechSynthesis.cancel();
    };
  }, []);

  const handleSendAi = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!aiPrompt.trim() || isAiLoading) return;
    const userMsg = aiPrompt.trim();
    setAiPrompt('');
    setAiChat(prev => [...prev, { role: 'user', text: userMsg }]);
    setIsAiLoading(true);

    try {
      const history = aiChat.map(m => ({ role: m.role, content: m.text }));
      history.push({ role: 'user', content: userMsg });

      const res = await api.aiAssistant({
        projectId: issue.project_id,
        messages: [
          {
            role: 'system',
            content: `You are an expert computer science and competitive programming educator. Guide the user through the learning story: "${issue.summary}". Details: ${issue.description || ''}. Keep answers concise, clear, and pedagogically sound.`
          },
          ...history
        ]
      });

      const reply = res.reply || res.text || res.message || 'I have reviewed your inquiry. What would you like to explore next?';
      setAiChat(prev => [...prev, { role: 'assistant', text: reply }]);
    } catch (err: any) {
      setAiChat(prev => [...prev, { role: 'assistant', text: `AI assistance note: ${err.message || 'Unable to fetch response.'}` }]);
    } finally {
      setIsAiLoading(false);
    }
  };

  const handleMarkComplete = async () => {
    try {
      await api.updateStatus(issue.id, 'Done');
      setIsDone(true);
      onStatusUpdated?.('Done');
      confetti({
        particleCount: 80,
        spread: 60,
        origin: { y: 0.6 }
      });
    } catch (e: any) {
      alert(`Could not update status: ${e.message}`);
    }
  };

  return (
    <div className="flex-1 flex overflow-hidden bg-[#18181b] text-gray-200">
      {/* Left Column: Lesson Content, Objectives, Notes */}
      <div className="flex-1 flex flex-col overflow-y-auto p-6 space-y-6 border-r border-[#27272a]">
        {/* Lesson Header */}
        <div className="bg-[#27272a]/60 rounded-xl p-5 border border-[#3f3f46]">
          <div className="flex items-center justify-between flex-wrap gap-3">
            <div className="flex items-center space-x-3">
              <span className="p-2 bg-indigo-500/20 text-indigo-400 rounded-lg">
                <GraduationCap className="w-5 h-5" />
              </span>
              <div>
                <h1 className="text-lg font-bold text-white">{issue.summary}</h1>
                <p className="text-xs text-gray-400">Interactive Learning Module · {issue.key}</p>
              </div>
            </div>

            <div className="flex items-center space-x-2">
              <button
                onClick={toggleSpeech}
                className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center space-x-1.5 transition ${
                  isSpeaking
                    ? 'bg-amber-600 text-white'
                    : 'bg-[#3f3f46] hover:bg-[#52525b] text-gray-200'
                }`}
                title={isSpeaking ? 'Stop narration' : 'Listen to lesson overview'}
              >
                {isSpeaking ? <VolumeX className="w-4 h-4" /> : <Volume2 className="w-4 h-4" />}
                <span>{isSpeaking ? 'Stop Audio' : 'Read Aloud'}</span>
              </button>

              <button
                onClick={handleMarkComplete}
                disabled={isDone}
                className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center space-x-1.5 transition ${
                  isDone
                    ? 'bg-emerald-600/30 text-emerald-400 border border-emerald-600/50 cursor-default'
                    : 'bg-emerald-600 hover:bg-emerald-500 text-white shadow-xs'
                }`}
              >
                <CheckCircle2 className="w-4 h-4" />
                <span>{isDone ? 'Completed' : 'Mark as Done'}</span>
              </button>
            </div>
          </div>
        </div>

        {/* Content Material */}
        <section className="bg-[#27272a]/40 rounded-xl p-5 border border-[#3f3f46]">
          <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wider mb-3 flex items-center space-x-2">
            <BookOpen className="w-4 h-4 text-indigo-400" />
            <span>Study Guide & Core Concepts</span>
          </h2>
          <div className="prose prose-invert max-w-none text-xs leading-relaxed">
            <RichContent content={issue.description || 'No detailed reading content has been provided for this topic.'} />
          </div>
        </section>

        {/* Learning Objectives Checklist */}
        <section className="bg-[#27272a]/40 rounded-xl p-5 border border-[#3f3f46]">
          <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wider mb-3 flex items-center space-x-2">
            <CheckSquare className="w-4 h-4 text-emerald-400" />
            <span>Learning Objectives Checklist</span>
          </h2>
          <div className="space-y-2">
            {objectives.map(obj => (
              <button
                key={obj.id}
                onClick={() => toggleObjective(obj.id)}
                className="w-full flex items-center space-x-3 p-2.5 rounded-lg bg-[#27272a]/80 hover:bg-[#3f3f46]/50 transition text-left text-xs"
              >
                {obj.completed ? (
                  <CheckSquare className="w-4 h-4 text-emerald-400 shrink-0" />
                ) : (
                  <Square className="w-4 h-4 text-gray-500 shrink-0" />
                )}
                <span className={obj.completed ? 'line-through text-gray-400' : 'text-gray-200'}>
                  {obj.text}
                </span>
              </button>
            ))}
          </div>
        </section>

        {/* User Study Notes */}
        <section className="bg-[#27272a]/40 rounded-xl p-5 border border-[#3f3f46]">
          <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wider mb-2 flex items-center space-x-2">
            <FileText className="w-4 h-4 text-amber-400" />
            <span>Your Study Notes</span>
          </h2>
          <p className="text-[11px] text-gray-400 mb-3">Persisted locally in your browser workspace.</p>
          <textarea
            rows={5}
            value={notes}
            onChange={e => handleNotesChange(e.target.value)}
            placeholder="Jot down formulas, algorithmic invariants, step-by-step proofs, or questions..."
            className="w-full p-3 bg-[#18181b] border border-[#3f3f46] rounded-lg text-xs text-gray-200 focus:ring-1 focus:ring-indigo-500 outline-none resize-y"
          />
        </section>
      </div>

      {/* Right Column: AI Tutor & Discussion */}
      <div className="w-96 flex flex-col bg-[#202023] border-l border-[#27272a]">
        <div className="p-4 border-b border-[#27272a] flex items-center space-x-2">
          <Sparkles className="w-4 h-4 text-indigo-400" />
          <h3 className="text-xs font-bold text-gray-200 uppercase tracking-wider">AI Concept Tutor</h3>
        </div>

        {/* Message Thread */}
        <div className="flex-1 overflow-y-auto p-4 space-y-3 text-xs">
          {aiChat.map((m, idx) => (
            <div
              key={idx}
              className={`p-3 rounded-lg leading-relaxed ${
                m.role === 'user'
                  ? 'bg-indigo-600 text-white ml-6'
                  : 'bg-[#27272a] text-gray-300 mr-6 border border-[#3f3f46]'
              }`}
            >
              <div className="text-[10px] font-semibold text-gray-400 mb-1">
                {m.role === 'user' ? 'You' : 'AI Tutor'}
              </div>
              <RichContent content={m.text} />
            </div>
          ))}
          {isAiLoading && (
            <div className="p-3 rounded-lg bg-[#27272a] text-gray-400 mr-6 text-xs italic animate-pulse">
              AI Tutor is analyzing your question...
            </div>
          )}
        </div>

        {/* Chat Input */}
        <form onSubmit={handleSendAi} className="p-3 border-t border-[#27272a] flex items-center space-x-2">
          <input
            type="text"
            value={aiPrompt}
            onChange={e => setAiPrompt(e.target.value)}
            placeholder="Ask a question about this topic..."
            className="flex-1 px-3 py-2 bg-[#18181b] border border-[#3f3f46] rounded-lg text-xs text-gray-200 outline-none focus:ring-1 focus:ring-indigo-500"
          />
          <button
            type="submit"
            disabled={!aiPrompt.trim() || isAiLoading}
            className="p-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded-lg transition"
          >
            <Send className="w-4 h-4" />
          </button>
        </form>
      </div>
    </div>
  );
};
