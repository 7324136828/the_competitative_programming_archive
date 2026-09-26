import React, { useState, useEffect, useRef } from 'react';
import {
  Sparkles,
  FileText,
  Search,
  MessageSquare,
  Settings,
  Send,
  ChevronDown,
  ChevronRight,
  AlertCircle,
  Copy,
  Check,
  RotateCcw,
  Wrench,
  Loader2,
} from 'lucide-react';
import { useProject } from '../../context/ProjectContext.js';
import { useAuth } from '../../context/AuthContext.js';
import { api } from '../../api/client.js';
import { AiStatus, AiRequestRow, Sprint } from '../../types/index.js';
import { StatusBadge, TypeIcon, PriorityIcon } from '../common/Badge.js';
import { formatDateTime } from '../../utils/format.js';

type AiTab = 'draft' | 'recommend' | 'chat' | 'settings';

const KEY_RE = /\b([A-Z][A-Z0-9]{1,9}-\d+)\b/g;

// Render simple markdown safely (no HTML): paragraphs, - lists, **bold**, `code`, issue-key links.
const InlineText: React.FC<{ text: string; onOpenKey: (key: string) => void }> = ({ text, onOpenKey }) => {
  const parts: React.ReactNode[] = [];
  // split by inline code first
  const codeSplit = text.split(/(`[^`]+`)/g);
  codeSplit.forEach((seg, i) => {
    if (seg.startsWith('`') && seg.endsWith('`') && seg.length > 2) {
      parts.push(
        <code key={i} className="px-1 py-0.5 bg-gray-100 rounded font-mono text-[11px] text-[#172B4D]">
          {seg.slice(1, -1)}
        </code>
      );
      return;
    }
    // bold then issue keys
    const boldSplit = seg.split(/(\*\*[^*]+\*\*)/g);
    boldSplit.forEach((b, j) => {
      if (b.startsWith('**') && b.endsWith('**') && b.length > 4) {
        parts.push(<strong key={`${i}-${j}`} className="font-semibold">{b.slice(2, -2)}</strong>);
        return;
      }
      let lastIdx = 0;
      let m: RegExpExecArray | null;
      const re = new RegExp(KEY_RE);
      while ((m = re.exec(b)) !== null) {
        if (m.index > lastIdx) parts.push(b.slice(lastIdx, m.index));
        parts.push(
          <button
            key={`${i}-${j}-${m.index}`}
            onClick={() => onOpenKey(m![1])}
            className="font-semibold text-[#0052CC] hover:underline"
          >
            {m[1]}
          </button>
        );
        lastIdx = m.index + m[1].length;
      }
      if (lastIdx < b.length) parts.push(b.slice(lastIdx));
    });
  });
  return <>{parts}</>;
};

const Markdown: React.FC<{ text: string; onOpenKey: (key: string) => void }> = ({ text, onOpenKey }) => {
  const blocks = text.split(/\n{2,}/);
  return (
    <div className="space-y-2 text-xs text-gray-800 leading-relaxed">
      {blocks.map((block, i) => {
        const lines = block.split('\n');
        if (lines.every(l => /^\s*[-*]\s+/.test(l))) {
          return (
            <ul key={i} className="list-disc pl-5 space-y-0.5">
              {lines.map((l, j) => (
                <li key={j}><InlineText text={l.replace(/^\s*[-*]\s+/, '')} onOpenKey={onOpenKey} /></li>
              ))}
            </ul>
          );
        }
        return (
          <p key={i}>
            {lines.map((l, j) => (
              <React.Fragment key={j}>
                {j > 0 && <br />}
                <InlineText text={l} onOpenKey={onOpenKey} />
              </React.Fragment>
            ))}
          </p>
        );
      })}
    </div>
  );
};

interface ChatMsg {
  role: 'user' | 'assistant';
  content: string;
  steps?: Array<{ tool: string; arguments: any; ok: boolean; error?: string; resultPreview?: string }>;
  error?: boolean;
}

const MUTATING_TOOLS = new Set(['create_ticket', 'add_comment', 'transition_ticket']);

const TabButton: React.FC<{ active: boolean; onClick: () => void; icon: any; label: string }> = ({ active, onClick, icon: Icon, label }) => (
  <button
    onClick={onClick}
    className={`pb-2 text-xs font-semibold flex items-center space-x-1.5 border-b-2 transition ${
      active ? 'border-[#0052CC] text-[#0052CC]' : 'border-transparent text-gray-500 hover:text-gray-700'
    }`}
  >
    <Icon className="w-3.5 h-3.5" />
    <span>{label}</span>
  </button>
);

export const AiAssistantView: React.FC = () => {
  const { currentProject, openIssueDetail, triggerRefresh, refreshKey } = useProject();
  const { currentUser, users, isAdmin, isViewer, canEdit } = useAuth();
  const [tab, setTab] = useState<AiTab>('draft');

  // ---------- Draft tab state ----------
  const [draftText, setDraftText] = useState('');
  const [maxTickets, setMaxTickets] = useState(5);
  const [drafts, setDrafts] = useState<any[]>([]);
  const [draftAi, setDraftAi] = useState<any>(null);
  const [draftLoading, setDraftLoading] = useState(false);
  const [draftError, setDraftError] = useState<string | null>(null);
  const [draftSprintId, setDraftSprintId] = useState('');
  const [draftAssigneeId, setDraftAssigneeId] = useState('');
  const [sprints, setSprints] = useState<Sprint[]>([]);
  const [createdKeys, setCreatedKeys] = useState<any[]>([]);
  const [createWarnings, setCreateWarnings] = useState<string[]>([]);
  const [creating, setCreating] = useState(false);

  // ---------- Recommend tab state ----------
  const [recQuery, setRecQuery] = useState('');
  const [recUseAi, setRecUseAi] = useState(true);
  const [recIncludeDone, setRecIncludeDone] = useState(false);
  const [recAllProjects, setRecAllProjects] = useState(false);
  const [recLimit, setRecLimit] = useState(5);
  const [recResults, setRecResults] = useState<any[]>([]);
  const [recExtracted, setRecExtracted] = useState<any>(null);
  const [recAi, setRecAi] = useState<any>(null);
  const [recLoading, setRecLoading] = useState(false);
  const [recError, setRecError] = useState<string | null>(null);

  // ---------- Chat state ----------
  const [chatMessages, setChatMessages] = useState<ChatMsg[]>([]);
  const [chatInput, setChatInput] = useState('');
  const [chatLoading, setChatLoading] = useState(false);
  const [expandedTools, setExpandedTools] = useState<Set<number>>(new Set());
  const chatEndRef = useRef<HTMLDivElement>(null);

  // ---------- Settings state ----------
  const [aiStatus, setAiStatus] = useState<AiStatus | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);
  const [selectedModel, setSelectedModel] = useState('');
  const [settingsMsg, setSettingsMsg] = useState<string | null>(null);
  const [registering, setRegistering] = useState(false);
  const [intakeText, setIntakeText] = useState('');
  const [intakeResult, setIntakeResult] = useState<any>(null);
  const [intakeLoading, setIntakeLoading] = useState(false);
  const [aiRequests, setAiRequests] = useState<AiRequestRow[]>([]);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (currentProject) {
      api.getSprints(currentProject.id).then(setSprints).catch(() => {});
    }
  }, [currentProject, refreshKey]);

  useEffect(() => {
    if (tab === 'settings') {
      api.getAiStatus().then(s => {
        setAiStatus(s);
        setSelectedModel(s.model || '');
        setStatusError(null);
      }).catch(e => setStatusError(e.message));
      api.getAiRequests(20).then(setAiRequests).catch(() => {});
    }
  }, [tab, refreshKey]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chatMessages, chatLoading]);

  // ---------- Draft handlers ----------
  const handleDraft = async () => {
    if (!draftText.trim() || !currentProject) return;
    setDraftLoading(true);
    setDraftError(null);
    setCreatedKeys([]);
    try {
      const out = await api.aiDraftTickets({ text: draftText, projectId: currentProject.id, maxTickets });
      setDrafts(out.drafts.map((d: any) => ({ ...d, included: true })));
      setDraftAi(out.ai);
    } catch (e: any) {
      setDraftError(e.message);
      setDrafts([]);
    } finally {
      setDraftLoading(false);
    }
  };

  const updateDraft = (idx: number, patch: any) => {
    setDrafts(ds => ds.map((d, i) => (i === idx ? { ...d, ...patch } : d)));
  };

  const handleCreateTickets = async () => {
    if (!currentProject) return;
    const selected = drafts
      .filter(d => d.included)
      .map(({ included, similar, ...d }) => ({
        ...d,
        sprintId: draftSprintId || null,
        assigneeId: draftAssigneeId || null,
      }));
    if (!selected.length) return;
    setCreating(true);
    setDraftError(null);
    try {
      const out = await api.aiCreateTickets(currentProject.id, selected);
      setCreatedKeys(out.created);
      setCreateWarnings(out.warnings || []);
      setDrafts(ds => ds.map(d => ({ ...d, included: false })));
      triggerRefresh();
    } catch (e: any) {
      setDraftError(e.message);
    } finally {
      setCreating(false);
    }
  };

  // ---------- Recommend handlers ----------
  const handleRecommend = async () => {
    if (!recQuery.trim()) return;
    setRecLoading(true);
    setRecError(null);
    try {
      const out = await api.aiRecommend({
        query: recQuery,
        projectId: recAllProjects ? null : currentProject?.id,
        limit: recLimit,
        includeDone: recIncludeDone,
        useAi: recUseAi,
      });
      setRecResults(out.results);
      setRecExtracted(out.extracted);
      setRecAi(out.ai);
    } catch (e: any) {
      setRecError(e.message);
      setRecResults([]);
    } finally {
      setRecLoading(false);
    }
  };

  // ---------- Chat handlers ----------
  const sendChat = async (text: string) => {
    const content = text.trim();
    if (!content || chatLoading) return;
    const userMsg: ChatMsg = { role: 'user', content };
    const next = [...chatMessages, userMsg];
    setChatMessages(next);
    setChatInput('');
    setChatLoading(true);
    try {
      const payload = next.slice(-20).map(m => ({ role: m.role, content: m.content }));
      const out = await api.aiAssistant({ messages: payload, projectId: currentProject?.id });
      setChatMessages([...next, { role: 'assistant', content: out.reply ?? '', steps: out.steps || [] }]);
      if ((out.steps || []).some((s: any) => s.ok && MUTATING_TOOLS.has(s.tool))) {
        triggerRefresh();
      }
    } catch (e: any) {
      setChatMessages([...next, { role: 'assistant', content: e.message, error: true }]);
    } finally {
      setChatLoading(false);
    }
  };

  // ---------- Settings handlers ----------
  const handleSaveModel = async (model: string | null) => {
    try {
      const out = await api.updateAiSettings(model);
      setAiStatus(s => (s ? { ...s, model: out.model, modelSource: out.modelSource } : s));
      setSelectedModel(out.model);
      setSettingsMsg(`Model set to ${out.model} (${out.modelSource})`);
      setTimeout(() => setSettingsMsg(null), 4000);
    } catch (e: any) {
      setSettingsMsg(`Error: ${e.message}`);
    }
  };

  const handleRegisterTools = async () => {
    setRegistering(true);
    try {
      const out = await api.aiRegisterTools();
      setSettingsMsg(`Registered ${out.registered.length} tools, ${out.failed.length} failed`);
      const s = await api.getAiStatus();
      setAiStatus(s);
      setTimeout(() => setSettingsMsg(null), 4000);
    } catch (e: any) {
      setSettingsMsg(`Error: ${e.message}`);
    } finally {
      setRegistering(false);
    }
  };

  const handleIntakeDryRun = async () => {
    if (!intakeText.trim() || !currentProject) return;
    setIntakeLoading(true);
    try {
      const out = await api.aiIntake({ projectId: currentProject.id, text: intakeText, source: 'settings-dry-run', dryRun: true });
      setIntakeResult(out);
    } catch (e: any) {
      setIntakeResult({ error: e.message });
    } finally {
      setIntakeLoading(false);
    }
  };

  const curlExample = `curl -X POST "${location.origin}/api/ai/intake" -H "Content-Type: application/json" -H "x-user-id: <user-id>" -d "{\\"projectId\\": \\"${currentProject?.id || '<project-id>'}\\", \\"text\\": \\"Bug report text here\\"}"`;
  const nonClosedSprints = sprints.filter(s => s.state !== 'closed');
  const assignableUsers = users.filter(u => u.role !== 'Viewer');

  return (
    <div className="flex-1 overflow-y-auto p-6 space-y-5">
      <div>
        <div className="flex items-center space-x-2">
          <h1 className="text-xl font-bold text-[#172B4D]">AI Assistant</h1>
          <Sparkles className="w-4 h-4 text-[#0052CC]" />
        </div>
        <p className="text-xs text-gray-500 mt-0.5">Draft tickets, get recommendations, and chat with Jira AI</p>
      </div>

      <div className="flex items-center space-x-5 border-b border-gray-200">
        <TabButton active={tab === 'draft'} onClick={() => setTab('draft')} icon={FileText} label="Create tickets from text" />
        <TabButton active={tab === 'recommend'} onClick={() => setTab('recommend')} icon={Search} label="Recommend tickets to fix" />
        <TabButton active={tab === 'chat'} onClick={() => setTab('chat')} icon={MessageSquare} label="Ask Jira AI" />
        <TabButton active={tab === 'settings'} onClick={() => setTab('settings')} icon={Settings} label="Settings & integration" />
      </div>

      {/* ================= DRAFT TAB ================= */}
      {tab === 'draft' && (
        <div className="space-y-4">
          <div className="bg-white rounded-xl border border-gray-200 shadow-xs p-4 space-y-3">
            <label className="block text-xs font-bold text-gray-700 uppercase tracking-wider">Describe the work in free text</label>
            <textarea
              rows={5}
              value={draftText}
              onChange={e => setDraftText(e.target.value)}
              placeholder="Paste a bug report, feature request, meeting notes, stack trace..."
              className="w-full p-3 border border-gray-300 rounded-lg text-xs outline-none focus:ring-1 focus:ring-blue-500"
            />
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2 text-xs">
                <label className="text-gray-500 font-medium">Max tickets:</label>
                <select
                  value={maxTickets}
                  onChange={e => setMaxTickets(Number(e.target.value))}
                  className="px-2 py-1 border border-gray-300 rounded text-xs bg-white outline-none"
                >
                  {Array.from({ length: 10 }, (_, i) => i + 1).map(n => (
                    <option key={n} value={n}>{n}</option>
                  ))}
                </select>
              </div>
              <button
                onClick={handleDraft}
                disabled={draftLoading || !draftText.trim()}
                className="px-4 py-1.5 bg-[#0052CC] hover:bg-[#0065FF] text-white text-xs font-semibold rounded-md transition disabled:opacity-50 flex items-center space-x-1.5"
              >
                {draftLoading && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                <span>Draft tickets</span>
              </button>
            </div>
          </div>

          {draftError && (
            <div className="p-3 bg-red-50 border border-red-200 rounded text-xs text-red-700 flex items-center space-x-2">
              <AlertCircle className="w-4 h-4 shrink-0" /><span>{draftError}</span>
            </div>
          )}

          {draftAi && (
            <div className={`p-3 rounded-lg border text-xs flex items-center space-x-2 ${
              draftAi.used ? 'bg-blue-50 border-blue-200 text-blue-800' : 'bg-amber-50 border-amber-200 text-amber-800'
            }`}>
              <Sparkles className="w-3.5 h-3.5 shrink-0" />
              {draftAi.used ? (
                <span>Drafted by <b>{draftAi.model}</b> in {draftAi.latencyMs}ms</span>
              ) : (
                <span>AI unavailable{draftAi.error ? ` (${draftAi.error})` : ''} — showing a heuristic fallback draft.</span>
              )}
            </div>
          )}

          {createdKeys.length > 0 && (
            <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-lg text-xs text-emerald-800">
              Created:{' '}
              {createdKeys.map((c, i) => (
                <React.Fragment key={c.id}>
                  {i > 0 && ', '}
                  <button onClick={() => openIssueDetail(c.key)} className="font-bold text-emerald-700 hover:underline">
                    {c.key}
                  </button>
                </React.Fragment>
              ))}
              {createWarnings.map((w, i) => (
                <div key={i} className="text-amber-700 mt-1">{w}</div>
              ))}
            </div>
          )}

          {drafts.length > 0 && (
            <>
              <div className="flex items-center space-x-4 bg-white rounded-xl border border-gray-200 shadow-xs p-3 text-xs">
                <div className="flex items-center space-x-2">
                  <label className="text-gray-500 font-medium">Sprint:</label>
                  <select value={draftSprintId} onChange={e => setDraftSprintId(e.target.value)}
                    className="px-2 py-1 border border-gray-300 rounded text-xs bg-white outline-none">
                    <option value="">None</option>
                    {nonClosedSprints.map(s => <option key={s.id} value={s.id}>{s.name} ({s.state})</option>)}
                  </select>
                </div>
                <div className="flex items-center space-x-2">
                  <label className="text-gray-500 font-medium">Assignee:</label>
                  <select value={draftAssigneeId} onChange={e => setDraftAssigneeId(e.target.value)}
                    className="px-2 py-1 border border-gray-300 rounded text-xs bg-white outline-none">
                    <option value="">Unassigned</option>
                    {assignableUsers.map(u => <option key={u.id} value={u.id}>{u.name}</option>)}
                  </select>
                </div>
                <div className="flex-1" />
                <button
                  onClick={handleCreateTickets}
                  disabled={creating || isViewer || !drafts.some(d => d.included)}
                  title={isViewer ? 'Viewer role cannot create issues' : undefined}
                  className="px-4 py-1.5 bg-[#0052CC] hover:bg-[#0065FF] text-white text-xs font-semibold rounded-md transition disabled:opacity-50"
                >
                  {creating ? 'Creating...' : `Create ${drafts.filter(d => d.included).length} tickets`}
                </button>
              </div>

              <div className="space-y-3">
                {drafts.map((d, idx) => (
                  <div key={idx} className={`bg-white rounded-xl border shadow-xs p-4 space-y-3 transition ${d.included ? 'border-gray-200' : 'border-gray-100 opacity-50'}`}>
                    <div className="flex items-center space-x-3">
                      <input type="checkbox" checked={d.included} onChange={e => updateDraft(idx, { included: e.target.checked })}
                        className="w-4 h-4 accent-[#0052CC]" />
                      <select value={d.type} onChange={e => updateDraft(idx, { type: e.target.value })}
                        className="px-2 py-1 border border-gray-300 rounded text-xs bg-white outline-none">
                        {['Story', 'Bug', 'Task', 'Epic', 'Subtask'].map(t => <option key={t}>{t}</option>)}
                      </select>
                      <select value={d.priority} onChange={e => updateDraft(idx, { priority: e.target.value })}
                        className="px-2 py-1 border border-gray-300 rounded text-xs bg-white outline-none">
                        {['Highest', 'High', 'Medium', 'Low', 'Lowest'].map(p => <option key={p}>{p}</option>)}
                      </select>
                      <input
                        type="number" min={0} value={d.storyPoints ?? ''}
                        onChange={e => updateDraft(idx, { storyPoints: e.target.value === '' ? null : Number(e.target.value) })}
                        placeholder="pts"
                        className="w-16 px-2 py-1 border border-gray-300 rounded text-xs outline-none"
                      />
                    </div>
                    <input
                      value={d.summary}
                      onChange={e => updateDraft(idx, { summary: e.target.value })}
                      className="w-full px-3 py-1.5 border border-gray-300 rounded text-xs font-semibold outline-none focus:ring-1 focus:ring-blue-500"
                    />
                    <textarea
                      rows={4} value={d.description}
                      onChange={e => updateDraft(idx, { description: e.target.value })}
                      className="w-full px-3 py-2 border border-gray-300 rounded text-xs outline-none focus:ring-1 focus:ring-blue-500 font-mono"
                    />
                    {d.similar?.length > 0 && (
                      <div className="text-[11px] text-gray-500">
                        <span className="font-semibold">Possible duplicates: </span>
                        {d.similar.map((s: any, i: number) => (
                          <span key={s.key} className="mr-2">
                            {i > 0 && ' '}
                            <button onClick={() => openIssueDetail(s.key)} className="font-semibold text-[#0052CC] hover:underline">
                              {s.key}
                            </button>
                            <span className="text-gray-400"> ({s.status}, score {s.score})</span>
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      )}

      {/* ================= RECOMMEND TAB ================= */}
      {tab === 'recommend' && (
        <div className="space-y-4">
          <div className="bg-white rounded-xl border border-gray-200 shadow-xs p-4 space-y-3">
            <label className="block text-xs font-bold text-gray-700 uppercase tracking-wider">What do you want to work on?</label>
            <textarea
              rows={3}
              value={recQuery}
              onChange={e => setRecQuery(e.target.value)}
              placeholder="Keywords, error messages, ticket keys, PR or branch links..."
              className="w-full p-3 border border-gray-300 rounded-lg text-xs outline-none focus:ring-1 focus:ring-blue-500"
            />
            <div className="flex items-center flex-wrap gap-4 text-xs">
              <label className="flex items-center space-x-1.5 text-gray-600">
                <input type="checkbox" checked={recUseAi} onChange={e => setRecUseAi(e.target.checked)} className="accent-[#0052CC]" />
                <span>Use AI re-ranking</span>
              </label>
              <label className="flex items-center space-x-1.5 text-gray-600">
                <input type="checkbox" checked={recIncludeDone} onChange={e => setRecIncludeDone(e.target.checked)} className="accent-[#0052CC]" />
                <span>Include done</span>
              </label>
              <label className="flex items-center space-x-1.5 text-gray-600">
                <input type="checkbox" checked={recAllProjects} onChange={e => setRecAllProjects(e.target.checked)} className="accent-[#0052CC]" />
                <span>All projects</span>
              </label>
              <select value={recLimit} onChange={e => setRecLimit(Number(e.target.value))}
                className="px-2 py-1 border border-gray-300 rounded text-xs bg-white outline-none">
                <option value={5}>Top 5</option>
                <option value={10}>Top 10</option>
              </select>
              <div className="flex-1" />
              <button
                onClick={handleRecommend}
                disabled={recLoading || !recQuery.trim()}
                className="px-4 py-1.5 bg-[#0052CC] hover:bg-[#0065FF] text-white text-xs font-semibold rounded-md transition disabled:opacity-50 flex items-center space-x-1.5"
              >
                {recLoading && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                <span>Recommend</span>
              </button>
            </div>
          </div>

          {recError && (
            <div className="p-3 bg-red-50 border border-red-200 rounded text-xs text-red-700 flex items-center space-x-2">
              <AlertCircle className="w-4 h-4 shrink-0" /><span>{recError}</span>
            </div>
          )}

          {recAi?.suggestion && (
            <div className="p-3 bg-blue-50 border border-blue-200 rounded-lg text-xs text-blue-900 flex items-start space-x-2">
              <Sparkles className="w-3.5 h-3.5 shrink-0 mt-0.5" />
              <span>{recAi.suggestion}</span>
            </div>
          )}
          {recAi && !recAi.used && recAi.error && (
            <div className="p-3 bg-amber-50 border border-amber-200 rounded-lg text-xs text-amber-800">
              AI re-ranking unavailable ({recAi.error}) — showing deterministic ranking.
            </div>
          )}

          {recExtracted && (
            <div className="flex flex-wrap gap-1.5 text-[10px]">
              {recExtracted.issueKeys?.map((k: string) => (
                <button key={k} onClick={() => openIssueDetail(k)} className="px-2 py-0.5 bg-blue-100 text-blue-800 rounded font-mono font-bold hover:bg-blue-200">{k}</button>
              ))}
              {recExtracted.pullRequests?.map((p: any) => (
                <span key={p.url} className="px-2 py-0.5 bg-purple-100 text-purple-800 rounded font-mono">PR {p.repo}#{p.number}</span>
              ))}
              {recExtracted.branches?.map((b: string) => (
                <span key={b} className="px-2 py-0.5 bg-emerald-100 text-emerald-800 rounded font-mono">{b}</span>
              ))}
              {recExtracted.filePaths?.map((f: string) => (
                <span key={f} className="px-2 py-0.5 bg-gray-200 text-gray-700 rounded font-mono">{f}</span>
              ))}
              {recExtracted.errorSignatures?.map((s: string) => (
                <span key={s} className="px-2 py-0.5 bg-red-100 text-red-700 rounded font-mono">{s}</span>
              ))}
            </div>
          )}

          <div className="space-y-2">
            {recResults.map((r, idx) => (
              <div key={r.id} className="bg-white rounded-xl border border-gray-200 shadow-xs p-4">
                <div className="flex items-center space-x-3">
                  <span className="text-lg font-bold text-gray-300 w-6">#{idx + 1}</span>
                  <TypeIcon type={r.type} />
                  <button onClick={() => openIssueDetail(r.key)} className="font-bold text-[#0052CC] hover:underline text-sm">
                    {r.key}
                  </button>
                  <span className="text-xs text-gray-800 flex-1 truncate" title={r.summary}>{r.summary}</span>
                  <StatusBadge status={r.status} />
                  <PriorityIcon priority={r.priority} />
                  <span className="text-[10px] font-mono text-gray-400" title="Score">{r.score}</span>
                </div>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {r.matchedTerms?.length > 0 && (
                    <span className="text-[10px] text-gray-500">matched: {r.matchedTerms.join(', ')}</span>
                  )}
                  {r.reasons?.map((reason: string, i: number) => (
                    <span key={i} className="px-1.5 py-0.5 bg-gray-100 text-gray-600 rounded text-[10px]">{reason}</span>
                  ))}
                </div>
                {r.aiRationale && (
                  <div className="mt-2 p-2 bg-purple-50 border border-purple-100 rounded text-[11px] text-purple-900 flex items-start space-x-2">
                    <Sparkles className="w-3 h-3 shrink-0 mt-0.5" />
                    <span>
                      {r.aiRationale}
                      {r.aiConfidence != null && <span className="text-purple-500 ml-1">(confidence {Math.round(r.aiConfidence * 100)}%)</span>}
                    </span>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ================= CHAT TAB ================= */}
      {tab === 'chat' && (
        <div className="flex flex-col h-[calc(100vh-13rem)] bg-white rounded-xl border border-gray-200 shadow-xs overflow-hidden">
          <div className="px-4 py-2.5 border-b border-gray-200 flex items-center justify-between">
            <span className="text-xs font-bold text-gray-700 uppercase tracking-wider">Ask Jira AI</span>
            <button
              onClick={() => setChatMessages([])}
              className="flex items-center space-x-1 text-[11px] text-gray-500 hover:text-gray-700"
            >
              <RotateCcw className="w-3 h-3" />
              <span>New chat</span>
            </button>
          </div>

          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {chatMessages.length === 0 && !chatLoading && (
              <div className="h-full flex flex-col items-center justify-center text-center space-y-4">
                <Sparkles className="w-8 h-8 text-gray-300" />
                <div className="text-xs text-gray-400">Ask about tickets, sprints, or metrics.</div>
                <div className="flex flex-wrap justify-center gap-2">
                  {['What should I fix first?', "Summarize the active sprint's metrics", 'Find tickets about login timeouts'].map(s => (
                    <button
                      key={s}
                      onClick={() => sendChat(s)}
                      className="px-3 py-1.5 bg-blue-50 hover:bg-blue-100 text-[#0052CC] text-xs font-medium rounded-full border border-blue-200 transition"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {chatMessages.map((m, i) => (
              <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                <div className={`max-w-[75%] rounded-xl px-4 py-2.5 ${
                  m.role === 'user'
                    ? 'bg-[#0052CC] text-white'
                    : m.error
                      ? 'bg-red-50 border border-red-200 text-red-700'
                      : 'bg-gray-50 border border-gray-200'
                }`}>
                  {m.role === 'user' ? (
                    <div className="text-xs whitespace-pre-wrap">{m.content}</div>
                  ) : m.error ? (
                    <div className="text-xs flex items-center space-x-2">
                      <AlertCircle className="w-4 h-4 shrink-0" /><span>{m.content}</span>
                    </div>
                  ) : (
                    <>
                      <Markdown text={m.content} onOpenKey={openIssueDetail} />
                      {m.steps && m.steps.length > 0 && (
                        <div className="mt-2 border-t border-gray-200 pt-2">
                          <button
                            onClick={() => {
                              const next = new Set(expandedTools);
                              if (next.has(i)) next.delete(i); else next.add(i);
                              setExpandedTools(next);
                            }}
                            className="flex items-center space-x-1 text-[10px] font-semibold text-gray-500 hover:text-gray-700"
                          >
                            {expandedTools.has(i) ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
                            <Wrench className="w-3 h-3" />
                            <span>Used tools ({m.steps.length})</span>
                          </button>
                          {expandedTools.has(i) && (
                            <div className="mt-1.5 space-y-1.5">
                              {m.steps.map((s, j) => (
                                <div key={j} className="p-2 bg-white border border-gray-200 rounded text-[10px] font-mono">
                                  <div className="flex items-center justify-between">
                                    <span className="font-bold text-[#172B4D]">{s.tool}</span>
                                    <span className={s.ok ? 'text-emerald-600 font-bold' : 'text-red-600 font-bold'}>
                                      {s.ok ? 'ok' : `error: ${s.error}`}
                                    </span>
                                  </div>
                                  <div className="text-gray-500 mt-0.5 break-all">args: {JSON.stringify(s.arguments)}</div>
                                  {s.resultPreview && (
                                    <div className="text-gray-400 mt-0.5 break-all line-clamp-3">→ {s.resultPreview}</div>
                                  )}
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      )}
                    </>
                  )}
                </div>
              </div>
            ))}

            {chatLoading && (
              <div className="flex justify-start">
                <div className="bg-gray-50 border border-gray-200 rounded-xl px-4 py-2.5 text-xs text-gray-500 flex items-center space-x-2">
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  <span>Thinking...</span>
                </div>
              </div>
            )}
            <div ref={chatEndRef} />
          </div>

          <div className="border-t border-gray-200 p-3">
            <div className="flex items-end space-x-2">
              <textarea
                rows={2}
                value={chatInput}
                onChange={e => setChatInput(e.target.value)}
                onKeyDown={e => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    sendChat(chatInput);
                  }
                }}
                placeholder="Ask Jira AI... (Enter to send, Shift+Enter for newline)"
                className="flex-1 p-2.5 border border-gray-300 rounded-lg text-xs outline-none focus:ring-1 focus:ring-blue-500 resize-none"
              />
              <button
                onClick={() => sendChat(chatInput)}
                disabled={chatLoading || !chatInput.trim()}
                className="p-2.5 bg-[#0052CC] hover:bg-[#0065FF] text-white rounded-lg transition disabled:opacity-50"
                title="Send"
              >
                <Send className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ================= SETTINGS TAB ================= */}
      {tab === 'settings' && (
        <div className="space-y-4">
          {statusError && (
            <div className="p-3 bg-red-50 border border-red-200 rounded text-xs text-red-700">{statusError}</div>
          )}
          {settingsMsg && (
            <div className="p-3 bg-blue-50 border border-blue-200 rounded text-xs text-blue-800">{settingsMsg}</div>
          )}

          {!aiStatus ? (
            <div className="p-6 text-center text-xs text-gray-400">Loading AI status...</div>
          ) : (
            <>
              <div className="bg-white rounded-xl border border-gray-200 shadow-xs p-4 space-y-3">
                <h3 className="text-xs font-bold text-gray-700 uppercase tracking-wider">Connector</h3>
                <div className="grid grid-cols-2 gap-3 text-xs">
                  <div>
                    <span className="text-gray-500">URL: </span>
                    <span className="font-mono text-[#172B4D]">{aiStatus.connectorUrl}</span>
                  </div>
                  <div>
                    <span className="text-gray-500">Reachable: </span>
                    <span className={`font-bold ${aiStatus.connector.reachable ? 'text-emerald-600' : 'text-red-600'}`}>
                      {aiStatus.connector.reachable ? 'yes' : `no${aiStatus.connector.error ? ` (${aiStatus.connector.error})` : ''}`}
                    </span>
                  </div>
                  <div>
                    <span className="text-gray-500">Version: </span>
                    <span className="font-mono">{aiStatus.connector.version || '-'}</span>
                  </div>
                  <div>
                    <span className="text-gray-500">Effective model: </span>
                    <span className="font-mono font-semibold">{aiStatus.model}</span>
                    <span className="text-gray-400"> ({aiStatus.modelSource})</span>
                  </div>
                </div>

                <div className="flex items-center space-x-2 pt-2 border-t border-gray-100">
                  <select
                    value={selectedModel}
                    onChange={e => setSelectedModel(e.target.value)}
                    disabled={!isAdmin}
                    className="px-2 py-1.5 border border-gray-300 rounded text-xs bg-white outline-none disabled:opacity-50"
                  >
                    {aiStatus.models.length === 0 && <option value={selectedModel}>{selectedModel}</option>}
                    {aiStatus.models.map(m => <option key={m} value={m}>{m}</option>)}
                  </select>
                  <button
                    onClick={() => handleSaveModel(selectedModel)}
                    disabled={!isAdmin}
                    title={!isAdmin ? 'Admin role required' : undefined}
                    className="px-3 py-1.5 bg-[#0052CC] text-white text-xs font-semibold rounded hover:bg-[#0065FF] disabled:opacity-50"
                  >
                    Save model
                  </button>
                  <button
                    onClick={() => handleSaveModel(null)}
                    disabled={!isAdmin}
                    title={!isAdmin ? 'Admin role required' : undefined}
                    className="px-3 py-1.5 bg-gray-100 text-gray-700 text-xs font-semibold rounded hover:bg-gray-200 disabled:opacity-50"
                  >
                    Reset to default
                  </button>
                </div>
              </div>

              <div className="bg-white rounded-xl border border-gray-200 shadow-xs p-4 space-y-3">
                <h3 className="text-xs font-bold text-gray-700 uppercase tracking-wider">Tool registration</h3>
                <div className="text-xs text-gray-600 space-y-1">
                  <div>
                    Registered:{' '}
                    <span className={`font-bold ${aiStatus.tools.registered ? 'text-emerald-600' : 'text-gray-500'}`}>
                      {aiStatus.tools.registered === null ? 'unknown (connector offline)' : aiStatus.tools.registered ? 'yes' : 'no'}
                    </span>
                    {aiStatus.tools.lastRegistration && (
                      <span className="text-gray-400 ml-2">
                        last attempt <span title={aiStatus.tools.lastRegistration.at}>{formatDateTime(aiStatus.tools.lastRegistration.at)}</span>
                        {' '}({aiStatus.tools.lastRegistration.registered} ok, {aiStatus.tools.lastRegistration.failed} failed)
                      </span>
                    )}
                  </div>
                  {aiStatus.tools.names.length > 0 && (
                    <div className="flex flex-wrap gap-1 pt-1">
                      {aiStatus.tools.names.map(n => (
                        <span key={n} className="px-1.5 py-0.5 bg-gray-100 text-gray-600 rounded font-mono text-[10px]">{n}</span>
                      ))}
                    </div>
                  )}
                </div>
                <button
                  onClick={handleRegisterTools}
                  disabled={!isAdmin || registering}
                  title={!isAdmin ? 'Admin role required' : undefined}
                  className="px-3 py-1.5 bg-[#0052CC] text-white text-xs font-semibold rounded hover:bg-[#0065FF] disabled:opacity-50 flex items-center space-x-1.5"
                >
                  {registering && <Loader2 className="w-3 h-3 animate-spin" />}
                  <span>Register tools now</span>
                </button>
              </div>

              <div className="bg-white rounded-xl border border-gray-200 shadow-xs p-4 space-y-3">
                <h3 className="text-xs font-bold text-gray-700 uppercase tracking-wider">Intake webhook</h3>
                <div className="text-xs">
                  <span className="text-gray-500">Endpoint: </span>
                  <span className="font-mono text-[#172B4D]">{location.origin}/api/ai/intake</span>
                </div>
                <div className="relative">
                  <pre className="p-3 bg-[#172B4D] text-gray-200 rounded-lg text-[11px] overflow-x-auto font-mono">{curlExample}</pre>
                  <button
                    onClick={() => { navigator.clipboard.writeText(curlExample); setCopied(true); setTimeout(() => setCopied(false), 2000); }}
                    className="absolute top-2 right-2 p-1.5 bg-white/10 hover:bg-white/20 rounded text-white"
                    title="Copy curl command"
                  >
                    {copied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
                  </button>
                </div>
                <div className="space-y-2">
                  <label className="block text-[11px] font-semibold text-gray-600">Test payload (dry run — nothing is written)</label>
                  <textarea
                    rows={3}
                    value={intakeText}
                    onChange={e => setIntakeText(e.target.value)}
                    placeholder="Incoming bug report text..."
                    className="w-full p-2.5 border border-gray-300 rounded-lg text-xs outline-none focus:ring-1 focus:ring-blue-500"
                  />
                  <button
                    onClick={handleIntakeDryRun}
                    disabled={intakeLoading || !intakeText.trim()}
                    className="px-3 py-1.5 bg-gray-800 text-white text-xs font-semibold rounded hover:bg-black disabled:opacity-50"
                  >
                    {intakeLoading ? 'Testing...' : 'Test (dry run)'}
                  </button>
                  {intakeResult && (
                    <div className="p-3 bg-gray-50 border border-gray-200 rounded-lg text-xs space-y-1">
                      {intakeResult.error ? (
                        <div className="text-red-600">{intakeResult.error}</div>
                      ) : (
                        <>
                          <div>Action: <span className="font-bold">{intakeResult.action}</span></div>
                          {intakeResult.duplicateOf && (
                            <div>
                              Duplicate decision:{' '}
                              <button onClick={() => openIssueDetail(intakeResult.duplicateOf.key)} className="font-semibold text-[#0052CC] hover:underline">
                                {intakeResult.duplicateOf.key}
                              </button>
                              <span className="text-gray-500"> (confidence {Math.round(intakeResult.duplicateOf.confidence * 100)}%{intakeResult.duplicateOf.reason ? `, ${intakeResult.duplicateOf.reason}` : ''})</span>
                            </div>
                          )}
                          {intakeResult.draft && (
                            <div>
                              Draft: <TypeIcon type={intakeResult.draft.type} /> <PriorityIcon priority={intakeResult.draft.priority} />
                              <span className="font-semibold ml-1">{intakeResult.draft.summary}</span>
                              <span className="text-gray-400"> ({intakeResult.draft.storyPoints ?? '-'} pts)</span>
                            </div>
                          )}
                        </>
                      )}
                    </div>
                  )}
                </div>
              </div>

              <div className="bg-white rounded-xl border border-gray-200 shadow-xs overflow-hidden">
                <div className="px-4 py-3 border-b border-gray-200 text-xs font-bold text-gray-700 uppercase tracking-wider">
                  Recent AI requests
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-xs text-left">
                    <thead>
                      <tr className="border-b border-gray-200 text-gray-400 font-semibold">
                        <th className="px-3 py-2">When</th>
                        <th className="px-3 py-2">Feature</th>
                        <th className="px-3 py-2">Model</th>
                        <th className="px-3 py-2">Status</th>
                        <th className="px-3 py-2">Latency</th>
                        <th className="px-3 py-2">Request ID</th>
                        <th className="px-3 py-2">Error</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {aiRequests.map(r => (
                        <tr key={r.id} className="hover:bg-gray-50">
                          <td className="px-3 py-2 whitespace-nowrap" title={r.created_at}>{formatDateTime(r.created_at)}</td>
                          <td className="px-3 py-2 font-mono">{r.feature}</td>
                          <td className="px-3 py-2 font-mono">{r.model || '-'}</td>
                          <td className="px-3 py-2">
                            <span className={`font-bold ${r.status === 'ok' ? 'text-emerald-600' : 'text-red-600'}`}>{r.status}</span>
                          </td>
                          <td className="px-3 py-2 font-mono">{r.latency_ms != null ? `${r.latency_ms}ms` : '-'}</td>
                          <td className="px-3 py-2 font-mono text-gray-400 whitespace-nowrap">{r.id}</td>
                          <td className="px-3 py-2 text-red-600 max-w-[200px] truncate" title={r.error || ''}>{r.error || '-'}</td>
                        </tr>
                      ))}
                      {aiRequests.length === 0 && (
                        <tr><td colSpan={7} className="px-3 py-6 text-center text-gray-400">No AI requests recorded yet.</td></tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
};
