import React from 'react';
import { Code2, ListFilter, Upload, Shuffle, History, Trash2, MessageSquare, Sparkles, Settings } from 'lucide-react';

export default function Navbar({
  currentView,
  onViewChange,
  currentProblem,
  onRandomProblem,
  onOpenUpload,
  onOpenGenerate,
  onClearDatabase,
  isClearingDatabase,
  isDatabaseBusy,
  onToggleChat,
  isChatOpen
}) {
  return (
    <header style={{
      backgroundColor: '#262626',
      borderBottom: '1px solid #3a3a3a',
      padding: '0.65rem 1.25rem',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      gap: '0.75rem',
      flexWrap: 'wrap',
      position: 'sticky',
      top: 0,
      zIndex: 40
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.8rem', flexWrap: 'wrap' }}>
        {/* Brand */}
        <div 
          onClick={() => onViewChange('list')}
          style={{ 
            display: 'flex', 
            alignItems: 'center', 
            gap: '0.6rem', 
            cursor: 'pointer',
            userSelect: 'none'
          }}
        >
          <div style={{
            backgroundColor: '#ffa116',
            color: '#1a1a1a',
            padding: '0.35rem',
            borderRadius: '0.375rem',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center'
          }}>
            <Code2 size={20} strokeWidth={2.5} />
          </div>
          <span style={{ fontWeight: 700, fontSize: '1.1rem', letterSpacing: '-0.02em', color: '#eff2f6' }}>
            CodeJudge
          </span>
          <span style={{
            fontSize: '0.7rem',
            backgroundColor: '#383838',
            color: '#ffa116',
            padding: '0.15rem 0.45rem',
            borderRadius: '0.25rem',
            fontWeight: 600,
            border: '1px solid #4a4a4a'
          }}>
            LeetCode Local
          </span>
        </div>

        {/* Problem List Button */}
        <button
          onClick={() => onViewChange('list')}
          className="btn btn-ghost"
          style={{
            color: currentView === 'list' ? '#ffa116' : '#9ea3ab',
            backgroundColor: currentView === 'list' ? '#333' : 'transparent',
            display: 'flex',
            alignItems: 'center',
            gap: '0.4rem',
            fontSize: '0.85rem'
          }}
        >
          <ListFilter size={16} />
          Problem Set
        </button>

        <button onClick={() => onViewChange('submissions')} className="btn btn-ghost" aria-current={currentView === 'submissions' ? 'page' : undefined} style={{ fontSize: '0.85rem', color: currentView === 'submissions' ? '#ffa116' : '#9ea3ab', backgroundColor: currentView === 'submissions' ? '#333' : 'transparent' }}>
          <History size={16} /> Submissions
        </button>

        <button onClick={() => onViewChange('settings')} className="btn btn-ghost" aria-current={currentView === 'settings' ? 'page' : undefined} style={{ fontSize: '0.85rem', color: currentView === 'settings' ? '#ffa116' : '#9ea3ab', backgroundColor: currentView === 'settings' ? '#333' : 'transparent' }}>
          <Settings size={16} /> Settings
        </button>

        {/* Active problem breadcrumb */}
        {currentProblem && currentView === 'solve' && (
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
            fontSize: '0.85rem',
            color: '#9ea3ab',
            borderLeft: '1px solid #444',
            paddingLeft: '1rem'
          }}>
            <span style={{ color: '#6b7280' }}>Solving:</span>
            <span style={{ color: '#fff', fontWeight: 600, maxWidth: '260px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {currentProblem.title}
            </span>
          </div>
        )}
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
        {/* AI Chat Drawer Toggle Button */}
        <button
          onClick={onToggleChat}
          className="btn"
          style={{
            fontSize: '0.825rem',
            backgroundColor: isChatOpen ? '#ffa116' : '#303030',
            color: isChatOpen ? '#111' : '#eff2f6',
            border: '1px solid #444',
            gap: '0.35rem',
            position: 'relative'
          }}
          title="Open AI Chat Assistant"
        >
          <MessageSquare size={14} />
          <span>AI Chat</span>
          <span style={{
            width: 6,
            height: 6,
            borderRadius: '50%',
            backgroundColor: isChatOpen ? '#111' : '#2cbb5d',
            display: 'inline-block'
          }} />
        </button>

        {/* Generate AI Problem Button */}
        <button
          onClick={onOpenGenerate}
          disabled={isClearingDatabase}
          className="btn btn-secondary"
          style={{ fontSize: '0.825rem', gap: '0.35rem', color: '#ffa116' }}
          title="Generate a new AI problem into the database"
        >
          <Sparkles size={14} />
          <span>Generate AI Problem</span>
        </button>

        {/* Random problem button */}
        <button
          onClick={onRandomProblem}
          disabled={isClearingDatabase}
          className="btn btn-secondary"
          title="Jump to a random problem"
          style={{ fontSize: '0.825rem' }}
        >
          <Shuffle size={14} />
          <span>Random</span>
        </button>

        {/* Upload problems.json button */}
        <button
          onClick={onOpenUpload}
          disabled={isClearingDatabase}
          className="btn btn-primary"
          style={{ fontSize: '0.825rem' }}
        >
          <Upload size={14} />
          <span>Upload</span>
        </button>

        {/* Clear Database button */}
        <button
          onClick={onClearDatabase}
          disabled={isClearingDatabase || isDatabaseBusy}
          className="btn btn-danger"
          title={isDatabaseBusy ? 'Finish the current action before clearing the database' : 'Delete all problems and submission history'}
          style={{ fontSize: '0.825rem' }}
        >
          <Trash2 size={14} />
          <span>{isClearingDatabase ? 'Clearing...' : 'Clear'}</span>
        </button>
      </div>
    </header>
  );
}
