import React, { useState } from 'react';
import { Languages, X, Check, Loader2, Globe } from 'lucide-react';
import { translateProblem } from '../services/api';

const SUPPORTED_LANGUAGES = [
  { code: 'en', name: 'English 🇺🇸' },
  { code: 'es', name: 'Spanish 🇪🇸' },
  { code: 'fr', name: 'French 🇫🇷' },
  { code: 'de', name: 'German 🇩🇪' },
  { code: 'zh', name: 'Chinese 🇨🇳' },
  { code: 'ru', name: 'Russian 🇷🇺' },
  { code: 'ja', name: 'Japanese 🇯🇵' }
];

export default function TranslateModal({ problem, isOpen, onClose, onApplyTranslation }) {
  const [targetLang, setTargetLang] = useState('en');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  if (!isOpen || !problem) return null;

  const handleTranslate = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await translateProblem({
        problemId: problem.id,
        targetLanguage: targetLang,
        title: problem.title,
        problem_statements: problem.problem_statements
      });

      if (res.success) {
        setResult(res);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleApply = () => {
    if (!result) return;
    onApplyTranslation({
      title: result.translatedTitle,
      problem_statements: result.translatedStatements,
      hints: result.translatedHints,
      language: targetLang,
      isTranslated: true
    });
    onClose();
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()} style={{ maxWidth: '680px' }}>
        {/* Header */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '1rem 1.25rem',
          borderBottom: '1px solid #3a3a3a'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
            <div style={{
              backgroundColor: 'rgba(59, 130, 246, 0.15)',
              color: '#60a5fa',
              padding: '0.4rem',
              borderRadius: '0.375rem'
            }}>
              <Languages size={18} />
            </div>
            <div>
              <h3 style={{ fontSize: '1rem', fontWeight: 600, color: '#eff2f6' }}>Translate Problem</h3>
              <p style={{ fontSize: '0.75rem', color: '#888' }}>
                Translate problems across languages using AI
              </p>
            </div>
          </div>

          <button onClick={onClose} className="btn btn-ghost" style={{ padding: '0.3rem' }}>
            <X size={18} />
          </button>
        </div>

        {/* Body */}
        <div style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div>
            <label style={{ display: 'block', fontSize: '0.8rem', color: '#aaa', marginBottom: '0.4rem' }}>
              Select Target Language:
            </label>
            <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
              {SUPPORTED_LANGUAGES.map((lang) => (
                <button
                  key={lang.code}
                  onClick={() => { setTargetLang(lang.code); setResult(null); }}
                  style={{
                    padding: '0.4rem 0.75rem',
                    borderRadius: '0.375rem',
                    fontSize: '0.8rem',
                    fontWeight: 500,
                    border: '1px solid',
                    cursor: 'pointer',
                    borderColor: targetLang === lang.code ? '#ffa116' : '#444',
                    backgroundColor: targetLang === lang.code ? '#382b18' : '#222',
                    color: targetLang === lang.code ? '#ffa116' : '#ccc'
                  }}
                >
                  {lang.name}
                </button>
              ))}
            </div>
          </div>

          <button
            onClick={handleTranslate}
            disabled={loading}
            className="btn btn-primary"
            style={{ width: '100%', padding: '0.6rem', fontSize: '0.875rem' }}
          >
            {loading ? (
              <>
                <Loader2 size={16} className="animate-spin" />
                Translating with AI...
              </>
            ) : (
              <>
                <Globe size={16} />
                Translate Problem
              </>
            )}
          </button>

          {error && (
            <div style={{ fontSize: '0.8rem', color: '#ef4743' }}>
              Error: {error}
            </div>
          )}

          {/* Translation Preview */}
          {result && (
            <div style={{
              backgroundColor: '#181818',
              border: '1px solid #383838',
              borderRadius: '0.5rem',
              padding: '1rem',
              display: 'flex',
              flexDirection: 'column',
              gap: '0.75rem',
              maxHeight: '320px',
              overflowY: 'auto'
            }}>
              <div>
                <span style={{ fontSize: '0.75rem', color: '#ffa116', fontWeight: 600 }}>TRANSLATED TITLE</span>
                <h4 style={{ fontSize: '0.95rem', fontWeight: 600, color: '#eff2f6', marginTop: '0.2rem' }}>
                  {result.translatedTitle}
                </h4>
              </div>

              <div>
                <span style={{ fontSize: '0.75rem', color: '#ffa116', fontWeight: 600 }}>TRANSLATED STATEMENT</span>
                <pre style={{
                  fontSize: '0.8rem',
                  color: '#ccc',
                  fontFamily: 'inherit',
                  whiteSpace: 'pre-wrap',
                  marginTop: '0.3rem',
                  lineHeight: 1.5
                }}>
                  {result.translatedStatements}
                </pre>
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', paddingTop: '0.5rem', borderTop: '1px solid #2e2e2e' }}>
                <button onClick={handleApply} className="btn btn-success" style={{ fontSize: '0.825rem' }}>
                  <Check size={15} /> Apply Translation to Workspace
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

