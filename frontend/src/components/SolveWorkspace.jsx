import React, { useEffect, useRef, useState } from 'react';
import { Maximize2, Minimize2 } from 'lucide-react';
import './SolveWorkspace.css';

const DEFAULT_SPLIT = { problem: 48, editor: 58 };
const STORAGE_KEY = 'codejudge.workspace.layout.v1';
const clamp = value => Math.min(80, Math.max(20, value));

function savedSplit() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY));
    return Object.fromEntries(Object.entries(DEFAULT_SPLIT).map(([key, value]) => [
      key, Number.isFinite(saved?.[key]) ? clamp(saved[key]) : value,
    ]));
  } catch {
    return DEFAULT_SPLIT;
  }
}

function ResizeHandle({ name, orientation, value, onChange, onReset, container, controls }) {
  const drag = useRef(null);
  const [dragging, setDragging] = useState(false);
  const vertical = orientation === 'vertical';

  function endDrag(event) {
    drag.current = null;
    setDragging(false);
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  }

  return (
    <div
      className={`workspace-resizer workspace-resizer-${orientation}${dragging ? ' is-dragging' : ''}`}
      role="separator"
      aria-label={name}
      aria-orientation={orientation}
      aria-controls={controls}
      aria-valuemin={20}
      aria-valuemax={80}
      aria-valuenow={Math.round(value)}
      aria-valuetext={`${Math.round(value)} percent`}
      tabIndex={0}
      title="Drag to resize. Arrow keys adjust; double-click resets."
      onDoubleClick={onReset}
      onPointerDown={event => {
        if (event.button !== 0 || !event.isPrimary) return;
        const bounds = container.current.getBoundingClientRect();
        const handle = event.currentTarget.getBoundingClientRect();
        drag.current = {
          pointerId: event.pointerId,
          position: vertical ? event.clientX : event.clientY,
          span: Math.max(1, vertical ? bounds.width - handle.width : bounds.height - handle.height),
          value,
        };
        event.currentTarget.focus();
        event.currentTarget.setPointerCapture(event.pointerId);
        event.preventDefault();
        setDragging(true);
      }}
      onPointerMove={event => {
        if (drag.current?.pointerId !== event.pointerId) return;
        const current = vertical ? event.clientX : event.clientY;
        onChange(clamp(drag.current.value + (current - drag.current.position) / drag.current.span * 100));
      }}
      onPointerUp={endDrag}
      onPointerCancel={endDrag}
      onLostPointerCapture={() => { drag.current = null; setDragging(false); }}
      onKeyDown={event => {
        const decrease = vertical ? 'ArrowLeft' : 'ArrowUp';
        const increase = vertical ? 'ArrowRight' : 'ArrowDown';
        if (![decrease, increase, 'Home', 'End'].includes(event.key)) return;
        event.preventDefault();
        const step = event.shiftKey ? 10 : 2;
        onChange(event.key === 'Home' ? 20 : event.key === 'End' ? 80 : clamp(value + (event.key === increase ? step : -step)));
      }}
    ><span aria-hidden="true" /></div>
  );
}

function Panel({ id, label, title, expanded, hidden, onToggle, panelRef, children }) {
  return (
    <section
      ref={panelRef}
      id={`workspace-${id}`}
      aria-label={`${label} panel`}
      className={`workspace-panel${expanded ? ' is-expanded' : ''}`}
      hidden={hidden}
    >
      <div className="workspace-panel-header">
        <span>{title}</span>
        <button
          className="btn btn-ghost workspace-expand"
          onClick={onToggle}
          aria-label={expanded ? 'Restore layout' : `Expand ${label.toLowerCase()}`}
          aria-expanded={expanded}
          title={expanded ? 'Restore layout (Esc)' : `Expand ${label.toLowerCase()}`}
        >
          {expanded ? <Minimize2 size={14} /> : <Maximize2 size={14} />}
          {expanded && <span>Restore layout · Esc</span>}
        </button>
      </div>
      <div className="workspace-panel-content">{children}</div>
    </section>
  );
}

export default function SolveWorkspace({ problem, editor, tests }) {
  const [split, setSplit] = useState(savedSplit);
  const [expanded, setExpanded] = useState(null);
  const [stacked, setStacked] = useState(() => window.matchMedia('(max-width: 800px)').matches);
  const workspace = useRef(null);
  const coding = useRef(null);
  const panels = useRef({});

  useEffect(() => {
    const media = window.matchMedia('(max-width: 800px)');
    const changed = () => setStacked(media.matches);
    media.addEventListener('change', changed);
    return () => media.removeEventListener('change', changed);
  }, []);

  useEffect(() => {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(split)); } catch { /* Storage can be disabled. */ }
  }, [split]);

  useEffect(() => {
    if (expanded) panels.current[expanded]?.querySelector('.workspace-expand')?.focus();
  }, [expanded]);

  const resize = (name, value) => setSplit(current => ({ ...current, [name]: value }));
  const problemTracks = `minmax(0, ${split.problem}fr) 10px minmax(0, ${100 - split.problem}fr)`;
  const toggle = id => setExpanded(current => current === id ? null : id);

  return (
    <div
      ref={workspace}
      className={`solve-workspace${stacked ? ' is-stacked' : ''}`}
      style={stacked ? { gridTemplateRows: problemTracks } : { gridTemplateColumns: problemTracks }}
      onKeyDown={event => {
        if (!expanded || event.defaultPrevented) return;
        if (event.key === 'Escape') {
          event.preventDefault();
          setExpanded(null);
        }
        // Keep keyboard navigation inside the panel while it fills the viewport.
        if (event.key === 'Tab') {
          const focusable = [...panels.current[expanded].querySelectorAll('button, a[href], input, textarea, select, [tabindex], [contenteditable="true"]')]
            .filter(element => !element.disabled && element.tabIndex >= 0 && element.getClientRects().length);
          const first = focusable[0];
          const last = focusable[focusable.length - 1];
          if (event.shiftKey && event.target === first) { event.preventDefault(); last?.focus(); }
          else if (!event.shiftKey && event.target === last) { event.preventDefault(); first?.focus(); }
        }
      }}
    >
      <Panel id="problem" label="Problem" title="Problem" expanded={expanded === 'problem'} hidden={Boolean(expanded && expanded !== 'problem')} onToggle={() => toggle('problem')} panelRef={node => { panels.current.problem = node; }}>
        {problem}
      </Panel>
      {!expanded && <ResizeHandle name="Resize problem and editor" orientation={stacked ? 'horizontal' : 'vertical'} value={split.problem} onChange={value => resize('problem', value)} onReset={() => resize('problem', DEFAULT_SPLIT.problem)} container={workspace} controls="workspace-problem" />}
      <div ref={coding} className="workspace-coding" hidden={expanded === 'problem'} style={{ gridTemplateRows: `minmax(0, ${split.editor}fr) 10px minmax(0, ${100 - split.editor}fr)` }}>
        <Panel id="editor" label="Code editor" title="Code editor" expanded={expanded === 'editor'} hidden={expanded === 'tests'} onToggle={() => toggle('editor')} panelRef={node => { panels.current.editor = node; }}>
          {editor}
        </Panel>
        {!expanded && <ResizeHandle name="Resize editor and test cases" orientation="horizontal" value={split.editor} onChange={value => resize('editor', value)} onReset={() => resize('editor', DEFAULT_SPLIT.editor)} container={coding} controls="workspace-editor" />}
        <Panel id="tests" label="Test cases" title="Test cases & results" expanded={expanded === 'tests'} hidden={expanded === 'editor'} onToggle={() => toggle('tests')} panelRef={node => { panels.current.tests = node; }}>
          {tests}
        </Panel>
      </div>
    </div>
  );
}
