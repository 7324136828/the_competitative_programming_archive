import React from 'react';
import RichContent from './RichContent';
import { Languages, Sparkles, RotateCcw } from 'lucide-react';
import HintPanel from './HintPanel';
import RecommendationList from './RecommendationList';
import ProblemAudio from './ProblemAudio';

export default function ProblemDetail({
  problem,
  onOpenTranslate,
  onOpenGenerateSimilar,
  onSelectProblem,
  translatedData,
  onResetTranslation
}) {
  if (!problem) {
    return <div style={{ padding: '2rem', color: '#888' }}>Select a problem to begin.</div>;
  }

  const isTranslated = !!translatedData;
  const displayTitle = isTranslated ? translatedData.title : problem.title;
  const displayStatements = isTranslated ? translatedData.problem_statements : problem.problem_statements;
  const source = typeof problem.source === 'string' ? problem.source.trim() : '';
  let sourceHref = null;
  if (source) {
    try {
      const url = new URL(source);
      if (url.protocol === 'https:' || url.protocol === 'http:') {
        sourceHref = url.href;
      }
    } catch {
      // Non-URL source names remain readable as plain text.
    }
  }

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      height: '100%',
      backgroundColor: '#1c1c1c',
      overflowY: 'auto'
    }}>
      {/* Problem Header */}
      <div style={{
        padding: '1.25rem',
        borderBottom: '1px solid #2e2e2e',
        backgroundColor: '#222'
      }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '1rem', flexWrap: 'wrap' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginBottom: '0.4rem', flexWrap: 'wrap' }}>
              <span style={{ fontSize: '0.8rem', color: problem.is_solved ? '#2cbb5d' : '#888', fontWeight: 600 }}>
                #{problem.id}{problem.is_solved ? ' · Solved' : ''}
              </span>
              <span className={`badge badge-${problem.difficulty ? problem.difficulty.toLowerCase() : 'medium'}`}>
                {problem.difficulty || 'Medium'}
              </span>
              <span style={{
                fontSize: '0.7rem',
                backgroundColor: '#2e2e2e',
                color: '#aaa',
                padding: '0.1rem 0.4rem',
                borderRadius: '0.25rem',
                textTransform: 'uppercase'
              }}>
                {isTranslated ? `${translatedData.language} (Translated)` : (problem.language || 'en')}
              </span>
            </div>

            <h2 style={{ fontSize: '1.25rem', fontWeight: 700, color: '#eff2f6' }}>
              {displayTitle}
            </h2>
            {source && (
              <div style={{ marginTop: '0.5rem', fontSize: '0.8rem', color: '#aaa', overflowWrap: 'anywhere' }}>
                Source: {sourceHref ? (
                  <a href={sourceHref} target="_blank" rel="noopener noreferrer" style={{ color: '#60a5fa', textDecoration: 'underline' }}>
                    {source}
                  </a>
                ) : source}
              </div>
            )}
          </div>

          {/* AI Action Buttons */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
            {isTranslated ? (
              <button
                onClick={onResetTranslation}
                className="btn btn-secondary"
                title="Revert to original text"
                style={{ fontSize: '0.775rem', padding: '0.35rem 0.65rem' }}
              >
                <RotateCcw size={13} />
                <span>Show Original</span>
              </button>
            ) : (
              <button
                onClick={onOpenTranslate}
                className="btn btn-secondary"
                title="Translate problem text to another language"
                style={{ fontSize: '0.775rem', padding: '0.35rem 0.65rem' }}
              >
                <Languages size={14} color="#60a5fa" />
                <span>Translate</span>
              </button>
            )}

            <button
              onClick={onOpenGenerateSimilar}
              className="btn btn-secondary"
              title="Generate a new AI problem"
              style={{ fontSize: '0.775rem', padding: '0.35rem 0.65rem' }}
            >
              <Sparkles size={14} color="#ffa116" />
              <span>Generate Similar</span>
            </button>
          </div>
        </div>

        {/* Tags */}
        {problem.tags && problem.tags.length > 0 && (
          <div style={{ display: 'flex', gap: '0.35rem', marginTop: '0.75rem', flexWrap: 'wrap' }}>
            {problem.tags.map((tag, idx) => (
              <span
                key={idx}
                style={{
                  fontSize: '0.725rem',
                  backgroundColor: '#2a2a2a',
                  color: '#9ea3ab',
                  padding: '0.15rem 0.5rem',
                  borderRadius: '0.25rem',
                  border: '1px solid #383838'
                }}
              >
                {tag}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Main Body */}
      <div style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
        <ProblemAudio key={problem.id} problem={problem} />
        {/* Problem Statement */}
        <section>
          <RichContent content={displayStatements} style={{
            color: '#d1d5db',
            fontSize: '0.9rem',
            lineHeight: 1.65,
            fontFamily: 'Inter, system-ui, sans-serif'
          }} />
        </section>

        {/* Sample Inputs and Outputs */}
        {problem.sample_input_output && problem.sample_input_output.length > 0 && (
          <section style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            <h3 style={{ fontSize: '0.95rem', fontWeight: 600, color: '#eff2f6' }}>
              Sample Test Cases
            </h3>

            {problem.sample_input_output.map((sample, idx) => (
              <div
                key={idx}
                style={{
                  backgroundColor: '#222',
                  border: '1px solid #333',
                  borderRadius: '0.5rem',
                  padding: '0.85rem'
                }}
              >
                <div style={{ fontSize: '0.75rem', fontWeight: 600, color: '#888', marginBottom: '0.5rem' }}>
                  Example {idx + 1}
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                  <div>
                    <span style={{ fontSize: '0.75rem', color: '#aaa', fontWeight: 500 }}>Input:</span>
                    <pre style={{
                      backgroundColor: '#151515',
                      padding: '0.5rem 0.75rem',
                      borderRadius: '0.375rem',
                      fontFamily: 'JetBrains Mono, monospace',
                      fontSize: '0.825rem',
                      color: '#eff2f6',
                      marginTop: '0.2rem',
                      whiteSpace: 'pre-wrap'
                    }}>
                      {sample.input}
                    </pre>
                  </div>

                  <div>
                    <span style={{ fontSize: '0.75rem', color: '#aaa', fontWeight: 500 }}>Output:</span>
                    <pre style={{
                      backgroundColor: '#151515',
                      padding: '0.5rem 0.75rem',
                      borderRadius: '0.375rem',
                      fontFamily: 'JetBrains Mono, monospace',
                      fontSize: '0.825rem',
                      color: '#2cbb5d',
                      marginTop: '0.2rem',
                      whiteSpace: 'pre-wrap'
                    }}>
                      {sample.output}
                    </pre>
                  </div>
                </div>
              </div>
            ))}
          </section>
        )}

        {/* AI Progressive Thinking Hints */}
        <HintPanel key={problem.id} problemId={problem.id} />

        {/* AI Recommended Problems */}
        <RecommendationList problemId={problem.id} onSelectProblem={onSelectProblem} />
      </div>
    </div>
  );
}
