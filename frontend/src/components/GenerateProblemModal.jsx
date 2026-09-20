import React, { useState } from 'react';
import { Sparkles, X, PlusCircle, Check, Loader2, BookOpen, Database } from 'lucide-react';
import { generateSimilarProblem, saveProblem } from '../services/api';
import LLMModel, { useLLMModel } from './LLMModel';
import RichContent from './RichContent';

export default function GenerateProblemModal({ problem, isOpen, onClose, onProblemCreated }) {
  const [loading, setLoading] = useState(false);
  const [generated, setGenerated] = useState(null);
  const [savedProblem, setSavedProblem] = useState(null);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [usedModel, setUsedModel] = useState(null);
  const { model, ready } = useLLMModel();

  if (!isOpen) return null;

  const handleClose = () => {
    if (loading || saving) return;
    onClose();
  };

  const handleGenerate = async () => {
    if (!ready || loading || saving) return;
    setLoading(true);
    setError(null);
    setGenerated(null);
    setSavedProblem(null);
    setUsedModel(null);
    try {
      const res = await generateSimilarProblem({
        problemId: problem ? problem.id : null,
        difficulty: problem ? problem.difficulty : 'Medium',
        autoSave: true,
        model
      });
      if (res.success) {
        setGenerated(res.generatedProblem);
        setSavedProblem(res.savedProblem);
        setUsedModel(res.model || model);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleSolve = async () => {
    if (!generated || loading || saving) return;
    setSaving(true);
    setError(null);
    try {
      let persisted = savedProblem;
      if (!persisted?.id) {
        const response = await saveProblem(generated);
        persisted = response.problem;
        if (!persisted?.id) throw new Error('The problem could not be saved. Please try again.');
        setSavedProblem(persisted);
      }
      onProblemCreated?.(persisted);
      onClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={handleClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()} style={{ maxWidth: '720px' }}>
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
              backgroundColor: 'rgba(255, 161, 22, 0.15)',
              color: '#ffa116',
              padding: '0.4rem',
              borderRadius: '0.375rem'
            }}>
              <Sparkles size={18} />
            </div>
            <div>
              <h3 style={{ fontSize: '1rem', fontWeight: 600, color: '#eff2f6' }}>AI Problem Generator</h3>
              <p style={{ fontSize: '0.75rem', color: '#888' }}>
                Generate new challenge problems (language: AI, source: Unknown) persisted directly to database
              </p>
            </div>
          </div>

          <button onClick={handleClose} className="btn btn-ghost" style={{ padding: '0.3rem' }}>
            <X size={18} />
          </button>
        </div>

        {/* Content */}
        <div style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <LLMModel usedModel={usedModel} />
          {!generated ? (
            <div style={{ textAlign: 'center', padding: '1.5rem 1rem' }}>
              <p style={{ color: '#aaa', fontSize: '0.875rem', marginBottom: '1.25rem', maxWidth: '480px', margin: '0 auto 1.25rem' }}>
                Click below to synthesize a new competitive programming problem. The new problem will be created under the language of AI with unknown source and saved directly into the SQLite database.
              </p>
              <button
                onClick={handleGenerate}
                disabled={loading || !ready}
                className="btn btn-primary"
                style={{ padding: '0.6rem 1.5rem', fontSize: '0.9rem' }}
              >
                {loading ? (
                  <>
                    <Loader2 size={16} className="animate-spin" />
                    Generating & Persisting to Database...
                  </>
                ) : (
                  <>
                    <Sparkles size={16} />
                    Generate AI Problem
                  </>
                )}
              </button>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
              {/* Preview of Generated Problem */}
              <div style={{
                backgroundColor: '#1b1b1b',
                border: '1px solid #383838',
                borderRadius: '0.5rem',
                padding: '1rem',
                display: 'flex',
                flexDirection: 'column',
                gap: '0.6rem'
              }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.5rem' }}>
                  <h4 style={{ fontSize: '1.05rem', fontWeight: 600, color: '#eff2f6' }}>
                    {generated.title}
                  </h4>
                  <div style={{ display: 'flex', gap: '0.4rem' }}>
                    <span className="badge badge-medium">{generated.difficulty}</span>
                    <span className="badge badge-warning" style={{ textTransform: 'uppercase' }}>Language: {generated.language}</span>
                    <span className="badge" style={{ backgroundColor: '#2d2d2d', color: '#aaa' }}>Source: {generated.source}</span>
                  </div>
                </div>

                <div style={{
                  fontSize: '0.825rem',
                  color: '#d1d5db',
                  lineHeight: 1.5,
                  maxHeight: '220px',
                  overflowY: 'auto',
                  backgroundColor: '#161616',
                  padding: '0.75rem',
                  borderRadius: '0.375rem',
                  border: '1px solid #282828',
                }}>
                  <RichContent content={generated.problem_statements} />
                </div>

                {generated.sample_input_output?.length > 0 && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '0.3rem' }}>
                    <span style={{ fontSize: '0.75rem', color: '#888', fontWeight: 600 }}>Sample Input & Output:</span>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem' }}>
                      <pre style={{ backgroundColor: '#141414', padding: '0.4rem 0.6rem', borderRadius: '0.25rem', fontSize: '0.75rem', color: '#eff2f6' }}>
                        {generated.sample_input_output[0].input}
                      </pre>
                      <pre style={{ backgroundColor: '#141414', padding: '0.4rem 0.6rem', borderRadius: '0.25rem', fontSize: '0.75rem', color: '#2cbb5d' }}>
                        {generated.sample_input_output[0].output}
                      </pre>
                    </div>
                  </div>
                )}
              </div>

              {/* Status & Actions */}
              <div style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '0.5rem 0'
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', color: '#2cbb5d', fontSize: '0.825rem' }}>
                  <Database size={15} />
                  <span>{savedProblem?.id ? `Saved to database (ID: ${savedProblem.id})` : 'This preview will be saved when you select Solve This Problem.'}</span>
                </div>

                <div style={{ display: 'flex', gap: '0.5rem' }}>
                  <button
                    onClick={handleGenerate}
                    disabled={loading || saving || !ready}
                    className="btn btn-secondary"
                    style={{ fontSize: '0.825rem' }}
                  >
                    {loading ? <Loader2 size={14} className="animate-spin" /> : 'Generate Another'}
                  </button>
                  <button
                    onClick={handleSolve}
                    disabled={loading || saving}
                    className="btn btn-primary"
                    style={{ fontSize: '0.825rem' }}
                  >
                    {saving ? 'Saving...' : 'Solve This Problem'}
                  </button>
                </div>
              </div>
            </div>
          )}

          {error && (
            <div style={{ color: '#ff8d89', fontSize: '0.8rem', backgroundColor: '#381616', padding: '0.5rem 0.75rem', borderRadius: '0.375rem' }}>
              {error}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
