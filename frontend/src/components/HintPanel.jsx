import React, { useState } from 'react';
import { Lightbulb, ChevronRight, Loader2, Sparkles, CheckCircle2 } from 'lucide-react';
import { fetchHint } from '../services/api';

export default function HintPanel({ problemId }) {
  const [hints, setHints] = useState([]);
  const [currentLevel, setCurrentLevel] = useState(0);
  const [totalSteps, setTotalSteps] = useState(7);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleGetHint = async () => {
    const nextLevel = currentLevel + 1;
    if (nextLevel > totalSteps) return;

    setLoading(true);
    setError(null);
    try {
      const res = await fetchHint({ problemId, hintLevel: nextLevel });
      if (res.success) {
        if (res.totalSteps) setTotalSteps(res.totalSteps);
        setHints(prev => [
          ...prev,
          {
            level: res.hintLevel,
            category: res.category,
            title: res.stepTitle || `Step ${res.hintLevel}`,
            text: res.hintText,
          }
        ]);
        setCurrentLevel(res.hintLevel);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      backgroundColor: '#202020',
      border: '1px solid #333',
      borderRadius: '0.5rem',
      padding: '0.85rem',
      display: 'flex',
      flexDirection: 'column',
      gap: '0.75rem'
    }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
          <div style={{
            backgroundColor: 'rgba(255, 161, 22, 0.15)',
            color: '#ffa116',
            padding: '0.3rem',
            borderRadius: '0.375rem',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center'
          }}>
            <Lightbulb size={16} />
          </div>
          <div>
            <h4 style={{ fontSize: '0.875rem', fontWeight: 600, color: '#eff2f6' }}>Programming Thinking Steps</h4>
            <p style={{ fontSize: '0.75rem', color: '#888' }}>
              Structured progressive steps (5–10 steps) to solve the problem
            </p>
          </div>
        </div>

        {currentLevel < totalSteps && (
          <button
            onClick={handleGetHint}
            disabled={loading}
            className="btn btn-secondary"
            style={{
              padding: '0.35rem 0.75rem',
              fontSize: '0.775rem',
              display: 'flex',
              alignItems: 'center',
              gap: '0.3rem'
            }}
          >
            {loading ? (
              <>
                <Loader2 size={13} className="animate-spin" />
                Formulating Step...
              </>
            ) : (
              <>
                <Sparkles size={13} color="#ffa116" />
                {currentLevel === 0 ? 'Unlock Step 1' : `Unlock Step ${currentLevel + 1}`}
              </>
            )}
          </button>
        )}
      </div>

      {error && (
        <div style={{ fontSize: '0.75rem', color: '#ef4743' }}>
          Failed to load thinking step: {error}
        </div>
      )}

      {/* Thinking Steps Progress Bar */}
      {currentLevel > 0 && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginTop: '0.1rem' }}>
          <div style={{ flex: 1, height: '4px', backgroundColor: '#333', borderRadius: '2px', overflow: 'hidden' }}>
            <div style={{
              width: `${(currentLevel / totalSteps) * 100}%`,
              height: '100%',
              backgroundColor: '#ffa116',
              transition: 'width 0.3s ease'
            }} />
          </div>
          <span style={{ fontSize: '0.7rem', color: '#aaa', whiteSpace: 'nowrap' }}>
            Step {currentLevel} of {totalSteps}
          </span>
        </div>
      )}

      {/* Thinking Steps List */}
      {hints.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem', marginTop: '0.25rem' }}>
          {hints.map((h, i) => (
            <div
              key={i}
              style={{
                backgroundColor: '#181818',
                border: '1px solid #383838',
                borderRadius: '0.375rem',
                padding: '0.65rem 0.75rem'
              }}
            >
              <div style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                fontSize: '0.75rem',
                fontWeight: 600,
                color: '#ffa116',
                marginBottom: '0.35rem'
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                  <span style={{
                    backgroundColor: '#302616',
                    padding: '0.1rem 0.4rem',
                    borderRadius: '0.2rem',
                    border: '1px solid #523e1d',
                    color: '#ffa116'
                  }}>
                    {h.title}
                  </span>
                  <span style={{ color: '#aaa', fontSize: '0.72rem' }}>• {h.category}</span>
                </div>
              </div>
              <p style={{
                fontSize: '0.8rem',
                color: '#d1d5db',
                lineHeight: 1.5,
                whiteSpace: 'pre-wrap'
              }}>
                {h.text}
              </p>
            </div>
          ))}
        </div>
      )}

      {currentLevel >= totalSteps && (
        <div style={{
          fontSize: '0.75rem',
          color: '#2cbb5d',
          backgroundColor: 'rgba(44, 187, 93, 0.1)',
          padding: '0.4rem',
          borderRadius: '0.3rem',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: '0.35rem'
        }}>
          <CheckCircle2 size={13} />
          All {totalSteps} programming thinking steps revealed. Ready to code your solution!
        </div>
      )}
    </div>
  );
}

