import React, { useState, useEffect } from 'react';
import { 
  Cpu, 
  CheckCircle2, 
  Sparkles, 
  Send, 
  FileCode, 
  Layers, 
  CheckSquare, 
  Square,
  AlertTriangle,
  RefreshCw
} from 'lucide-react';
import confetti from 'canvas-confetti';
import RichContent from '../RichContent';
import { Issue } from '../../types';
import { api } from '../../api/client';

interface NonCodingActivityProps {
  issue: Issue;
  onStatusUpdated?: (newStatus: string) => void;
  onClose: () => void;
}

export const NonCodingActivity: React.FC<NonCodingActivityProps> = ({
  issue,
  onStatusUpdated,
  onClose,
}) => {
  const [solutionProposal, setSolutionProposal] = useState<string>(() => {
    return localStorage.getItem(`noncoding_proposal_${issue.id}`) || '';
  });
  const [criteria, setCriteria] = useState<Array<{ id: number; text: string; done: boolean }>>([]);
  const [aiReview, setAiReview] = useState<string | null>(null);
  const [isReviewing, setIsReviewing] = useState(false);
  const [isDone, setIsDone] = useState(issue.status === 'Done');

  useEffect(() => {
    const savedCriteria = localStorage.getItem(`noncoding_crit_${issue.id}`);
    if (savedCriteria) {
      try {
        setCriteria(JSON.parse(savedCriteria));
        return;
      } catch (e) {}
    }

    const defaultCriteria = [
      { id: 1, text: 'Functional requirements clearly specified and scoped', done: false },
      { id: 2, text: 'Scale & throughput estimates (QPS, storage, bandwidth)', done: false },
      { id: 3, text: 'High-level component architecture & data flow diagrams', done: false },
      { id: 4, text: 'Data model / schema definition and storage choices', done: false },
      { id: 5, text: 'Bottlenecks, single point of failure (SPOF), and failure recovery strategies', done: false },
    ];
    setCriteria(defaultCriteria);
  }, [issue.id]);

  const toggleCriteria = (id: number) => {
    const updated = criteria.map(c => c.id === id ? { ...c, done: !c.done } : c);
    setCriteria(updated);
    localStorage.setItem(`noncoding_crit_${issue.id}`, JSON.stringify(updated));
  };

  const handleProposalChange = (val: string) => {
    setSolutionProposal(val);
    localStorage.setItem(`noncoding_proposal_${issue.id}`, val);
  };

  const handleRequestReview = async () => {
    if (!solutionProposal.trim()) {
      alert('Please write your solution proposal before requesting an AI review.');
      return;
    }

    setIsReviewing(true);
    setAiReview(null);

    try {
      const res = await api.aiAssistant({
        projectId: issue.project_id,
        messages: [
          {
            role: 'system',
            content: `You are a Principal Software Architect conducting a rigorous technical review. The task is "${issue.summary}". Requirements: ${issue.description || 'None'}. Review the user's design proposal for correctness, scalability, latency/throughput tradeoffs, security, and edge-case handling. Structure your review into: 1) Strengths, 2) Critical Bottlenecks / Risks, 3) Recommended Architecture Improvements.`
          },
          {
            role: 'user',
            content: `Here is my design proposal:\n\n${solutionProposal}`
          }
        ]
      });

      const reply = res.reply || res.text || res.message || 'Review completed.';
      setAiReview(reply);
    } catch (err: any) {
      setAiReview(`AI Review error: ${err.message || 'Unable to complete review.'}`);
    } finally {
      setIsReviewing(false);
    }
  };

  const handleMarkDone = async () => {
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
      {/* Left Column: Requirements, Acceptance Criteria & Canvas */}
      <div className="flex-1 flex flex-col overflow-y-auto p-6 space-y-6 border-r border-[#27272a]">
        {/* Header */}
        <div className="bg-[#27272a]/60 rounded-xl p-5 border border-[#3f3f46]">
          <div className="flex items-center justify-between flex-wrap gap-3">
            <div className="flex items-center space-x-3">
              <span className="p-2 bg-purple-500/20 text-purple-400 rounded-lg">
                <Cpu className="w-5 h-5" />
              </span>
              <div>
                <h1 className="text-lg font-bold text-white">{issue.summary}</h1>
                <p className="text-xs text-gray-400">System Design & Non-Coding Task · {issue.key}</p>
              </div>
            </div>

            <div className="flex items-center space-x-2">
              <button
                onClick={handleMarkDone}
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

        {/* Requirements */}
        <section className="bg-[#27272a]/40 rounded-xl p-5 border border-[#3f3f46]">
          <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wider mb-3 flex items-center space-x-2">
            <Layers className="w-4 h-4 text-purple-400" />
            <span>Problem Requirements & Goals</span>
          </h2>
          <div className="prose prose-invert max-w-none text-xs leading-relaxed">
            <RichContent content={issue.description || 'No requirements specified.'} />
          </div>
        </section>

        {/* Acceptance Criteria Checklist */}
        <section className="bg-[#27272a]/40 rounded-xl p-5 border border-[#3f3f46]">
          <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wider mb-3 flex items-center space-x-2">
            <CheckSquare className="w-4 h-4 text-purple-400" />
            <span>Design Verification Checklist</span>
          </h2>
          <div className="space-y-2">
            {criteria.map(c => (
              <button
                key={c.id}
                onClick={() => toggleCriteria(c.id)}
                className="w-full flex items-center space-x-3 p-2.5 rounded-lg bg-[#27272a]/80 hover:bg-[#3f3f46]/50 transition text-left text-xs"
              >
                {c.done ? (
                  <CheckSquare className="w-4 h-4 text-purple-400 shrink-0" />
                ) : (
                  <Square className="w-4 h-4 text-gray-500 shrink-0" />
                )}
                <span className={c.done ? 'line-through text-gray-400' : 'text-gray-200'}>
                  {c.text}
                </span>
              </button>
            ))}
          </div>
        </section>

        {/* Solution Proposal Canvas */}
        <section className="bg-[#27272a]/40 rounded-xl p-5 border border-[#3f3f46]">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-gray-300 uppercase tracking-wider flex items-center space-x-2">
              <FileCode className="w-4 h-4 text-amber-400" />
              <span>Your Architecture & Design Proposal</span>
            </h2>
            <button
              onClick={handleRequestReview}
              disabled={isReviewing || !solutionProposal.trim()}
              className="px-3 py-1.5 bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 disabled:opacity-50 text-white rounded-lg text-xs font-semibold flex items-center space-x-1.5 transition shadow-xs"
            >
              {isReviewing ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
              <span>{isReviewing ? 'Analyzing...' : 'Request AI Review'}</span>
            </button>
          </div>
          <p className="text-[11px] text-gray-400 mb-3">Draft your architectural diagrams, API contracts, database schemas, and caching/sharding strategies in Markdown.</p>
          <textarea
            rows={10}
            value={solutionProposal}
            onChange={e => handleProposalChange(e.target.value)}
            placeholder="### 1. High-Level Architecture&#10;Describe system components, clients, load balancers, services...&#10;&#10;### 2. Data Storage & Schema&#10;Define SQL/NoSQL choices, indexes, and partition keys...&#10;&#10;### 3. Scalability & Resilience&#10;Explain caching, replication, and disaster recovery..."
            className="w-full p-4 bg-[#18181b] border border-[#3f3f46] rounded-lg text-xs font-mono text-gray-200 focus:ring-1 focus:ring-purple-500 outline-none resize-y leading-relaxed"
          />
        </section>
      </div>

      {/* Right Column: AI Architectural Review */}
      <div className="w-96 flex flex-col bg-[#202023] border-l border-[#27272a]">
        <div className="p-4 border-b border-[#27272a] flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <Sparkles className="w-4 h-4 text-purple-400" />
            <h3 className="text-xs font-bold text-gray-200 uppercase tracking-wider">AI Architectural Review</h3>
          </div>
          {aiReview && (
            <button
              onClick={handleRequestReview}
              disabled={isReviewing}
              className="text-[11px] text-purple-400 hover:text-purple-300 font-semibold"
            >
              Re-review
            </button>
          )}
        </div>

        <div className="flex-1 overflow-y-auto p-4 text-xs leading-relaxed">
          {isReviewing ? (
            <div className="flex flex-col items-center justify-center h-full text-center space-y-3 text-gray-400">
              <RefreshCw className="w-8 h-8 animate-spin text-purple-500" />
              <p>Analyzing architecture proposal for scalability bottlenecks, SPOFs, and data consistency...</p>
            </div>
          ) : aiReview ? (
            <div className="bg-[#27272a] p-4 rounded-xl border border-[#3f3f46] text-gray-300 space-y-2">
              <div className="flex items-center space-x-1.5 text-purple-400 font-semibold mb-2">
                <CheckCircle2 className="w-4 h-4" />
                <span>Review Feedback</span>
              </div>
              <RichContent content={aiReview} />
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center h-full text-center space-y-2 text-gray-500 p-6">
              <Cpu className="w-10 h-10 stroke-1 text-gray-600" />
              <p className="font-semibold text-gray-400">No Review Yet</p>
              <p className="text-[11px]">Write your design proposal on the left and click "Request AI Review" to receive architecture critique.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
