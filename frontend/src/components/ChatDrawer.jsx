import React, { useState, useEffect, useRef } from 'react';
import { MessageSquare, X, Send, Bot, User, Sparkles, Loader2, Code2, Lightbulb, Bug, Check, Copy } from 'lucide-react';
import { chatWithAI, fetchChatHistory } from '../services/api';

export default function ChatDrawer({ isOpen, onClose, currentProblem, currentCode, currentLanguage, onApplyTestCases, onApplyThinkingSteps }) {
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      content: 'Hello! I am your CodeJudge AI Assistant. I can help explain algorithmic strategies, guide you through programming thinking steps, generate boundary test cases, or review and debug your code. What would you like to explore?'
    }
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [includeContext, setIncludeContext] = useState(true);
  const [copiedIndex, setCopiedIndex] = useState(null);
  const messagesEndRef = useRef(null);

  useEffect(() => {
    if (isOpen) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, isOpen]);

  const handleSend = async (customMessage) => {
    const textToSend = customMessage || input;
    if (!textToSend.trim() || loading) return;

    const userMessage = { role: 'user', content: textToSend };
    const updatedMessages = [...messages, userMessage];
    setMessages(updatedMessages);
    if (!customMessage) setInput('');
    setLoading(true);

    try {
      const res = await chatWithAI({
        messages: updatedMessages,
        problemId: includeContext && currentProblem ? currentProblem.id : null,
        code: includeContext && currentCode ? currentCode : null,
        language: includeContext ? currentLanguage : null,
        sessionId: 'user-chat-session'
      });

      if (res.success && res.reply) {
        setMessages(prev => [...prev, { role: 'assistant', content: res.reply }]);
      } else {
        setMessages(prev => [...prev, { role: 'assistant', content: 'I encountered an error generating a response. Please try again.' }]);
      }
    } catch (err) {
      setMessages(prev => [...prev, { role: 'assistant', content: `Error: ${err.message}` }]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const copyToClipboard = (text, idx) => {
    navigator.clipboard.writeText(text);
    setCopiedIndex(idx);
    setTimeout(() => setCopiedIndex(null), 2000);
  };

  if (!isOpen) return null;

  return (
    <div style={{
      position: 'fixed',
      top: 0,
      right: 0,
      bottom: 0,
      width: '420px',
      maxWidth: '100vw',
      backgroundColor: '#202020',
      borderLeft: '1px solid #383838',
      zIndex: 100,
      display: 'flex',
      flexDirection: 'column',
      boxShadow: '-8px 0 24px rgba(0, 0, 0, 0.45)'
    }}>
      {/* Header */}
      <div style={{
        padding: '0.85rem 1rem',
        borderBottom: '1px solid #333',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        backgroundColor: '#262626'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <div style={{
            backgroundColor: 'rgba(255, 161, 22, 0.15)',
            color: '#ffa116',
            padding: '0.35rem',
            borderRadius: '0.375rem'
          }}>
            <Bot size={18} />
          </div>
          <div>
            <h3 style={{ fontSize: '0.9rem', fontWeight: 600, color: '#eff2f6' }}>AI Assistant</h3>
            <span style={{ fontSize: '0.72rem', color: '#888' }}>
              {includeContext && currentProblem ? `Context: ${currentProblem.title}` : 'General Coding Mode'}
            </span>
          </div>
        </div>
        <button
          onClick={onClose}
          className="btn btn-ghost"
          style={{ padding: '0.3rem', color: '#aaa', cursor: 'pointer' }}
          title="Close Chat"
        >
          <X size={18} />
        </button>
      </div>

      {/* Context Toggle */}
      {currentProblem && (
        <div style={{
          padding: '0.4rem 1rem',
          backgroundColor: '#1c1c1c',
          borderBottom: '1px solid #2d2d2d',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          fontSize: '0.75rem',
          color: '#aaa'
        }}>
          <span>Include active problem & code in context</span>
          <input
            type="checkbox"
            checked={includeContext}
            onChange={(e) => setIncludeContext(e.target.checked)}
            style={{ cursor: 'pointer', accentColor: '#ffa116' }}
          />
        </div>
      )}

      {/* Messages Thread */}
      <div style={{
        flex: 1,
        overflowY: 'auto',
        padding: '1rem',
        display: 'flex',
        flexDirection: 'column',
        gap: '0.85rem'
      }}>
        {messages.map((m, idx) => (
          <div
            key={idx}
            style={{
              display: 'flex',
              flexDirection: 'column',
              alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start',
              maxWidth: '92%'
            }}
          >
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.35rem',
              marginBottom: '0.2rem',
              fontSize: '0.7rem',
              color: '#888',
              alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start'
            }}>
              {m.role === 'user' ? <User size={12} /> : <Bot size={12} color="#ffa116" />}
              <span>{m.role === 'user' ? 'You' : 'CodeJudge AI'}</span>
            </div>
            <div style={{
              backgroundColor: m.role === 'user' ? '#ffa116' : '#282828',
              color: m.role === 'user' ? '#111' : '#eff2f6',
              borderRadius: '0.5rem',
              padding: '0.65rem 0.85rem',
              fontSize: '0.825rem',
              lineHeight: 1.45,
              whiteSpace: 'pre-wrap',
              border: m.role === 'user' ? 'none' : '1px solid #383838',
              boxShadow: '0 1px 3px rgba(0,0,0,0.2)'
            }}>
              {m.content}
            </div>
            {m.role === 'assistant' && (
              <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '0.2rem' }}>
                <button
                  onClick={() => copyToClipboard(m.content, idx)}
                  className="btn btn-ghost"
                  style={{ padding: '0.1rem 0.3rem', fontSize: '0.68rem', color: '#888', gap: '0.2rem' }}
                >
                  {copiedIndex === idx ? <Check size={11} color="#2cbb5d" /> : <Copy size={11} />}
                  {copiedIndex === idx ? 'Copied' : 'Copy'}
                </button>
              </div>
            )}
          </div>
        ))}
        {loading && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#ffa116', fontSize: '0.78rem' }}>
            <Loader2 size={14} className="animate-spin" />
            <span>Thinking and formulating response...</span>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Suggested Quick Prompt Chips */}
      <div style={{
        padding: '0.5rem 0.85rem',
        borderTop: '1px solid #333',
        backgroundColor: '#1b1b1b',
        display: 'flex',
        gap: '0.4rem',
        overflowX: 'auto'
      }}>
        <button
          onClick={() => handleSend('Can you explain the problem constraints and outline 5 to 10 thinking steps?')}
          className="btn btn-secondary"
          style={{ fontSize: '0.72rem', padding: '0.25rem 0.5rem', whiteSpace: 'nowrap', gap: '0.25rem' }}
        >
          <Lightbulb size={12} color="#ffa116" />
          Thinking Steps
        </button>
        <button
          onClick={() => handleSend('Can you generate boundary and edge test cases based on the limitations of this problem?')}
          className="btn btn-secondary"
          style={{ fontSize: '0.72rem', padding: '0.25rem 0.5rem', whiteSpace: 'nowrap', gap: '0.25rem' }}
        >
          <Sparkles size={12} color="#2cbb5d" />
          Edge Test Cases
        </button>
        <button
          onClick={() => handleSend('Can you review and debug my current code for potential edge-case failures or time limits?')}
          className="btn btn-secondary"
          style={{ fontSize: '0.72rem', padding: '0.25rem 0.5rem', whiteSpace: 'nowrap', gap: '0.25rem' }}
        >
          <Bug size={12} color="#ef4743" />
          Debug Code
        </button>
      </div>

      {/* Input Area */}
      <div style={{
        padding: '0.75rem',
        borderTop: '1px solid #333',
        backgroundColor: '#262626',
        display: 'flex',
        gap: '0.5rem'
      }}>
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask a question about this problem, algorithms, or code..."
          rows={2}
          style={{
            flex: 1,
            backgroundColor: '#181818',
            border: '1px solid #444',
            borderRadius: '0.375rem',
            padding: '0.5rem 0.65rem',
            color: '#eff2f6',
            fontSize: '0.825rem',
            resize: 'none',
            fontFamily: 'inherit',
            outline: 'none'
          }}
        />
        <button
          onClick={() => handleSend()}
          disabled={!input.trim() || loading}
          className="btn btn-primary"
          style={{ padding: '0.5rem 0.75rem', alignSelf: 'flex-end' }}
        >
          {loading ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
        </button>
      </div>
    </div>
  );
}

