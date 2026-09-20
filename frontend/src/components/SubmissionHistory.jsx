import React, { useState } from 'react';
import { CheckCircle2, XCircle, Clock, ChevronRight, Code } from 'lucide-react';

export default function SubmissionHistory({ submissions = [] }) {
  const [selectedSub, setSelectedSub] = useState(null);

  if (!submissions || submissions.length === 0) {
    return (
      <div style={{ textAlign: 'center', padding: '2rem 1rem', color: '#777', fontSize: '0.85rem' }}>
        No submissions yet for this problem. Write your solution and click "Submit"!
      </div>
    );
  }

  const getStatusColor = (status) => {
    switch (status) {
      case 'Accepted':
        return '#2cbb5d';
      case 'Wrong Answer':
        return '#ef4743';
      case 'Time Limit Exceeded':
        return '#ffa116';
      default:
        return '#ff375f';
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
      <div style={{ fontSize: '0.85rem', fontWeight: 600, color: '#aaa', marginBottom: '0.25rem' }}>
        Past Submissions ({submissions.length})
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
        {submissions.map((sub) => {
          const color = getStatusColor(sub.status);
          const date = new Date(sub.created_at).toLocaleString();

          return (
            <div
              key={sub.id}
              onClick={() => setSelectedSub(selectedSub?.id === sub.id ? null : sub)}
              style={{
                backgroundColor: '#1a1a1a',
                border: '1px solid #333',
                borderRadius: '0.375rem',
                padding: '0.6rem 0.85rem',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                cursor: 'pointer',
                transition: 'background-color 0.15s'
              }}
              onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#242424'}
              onMouseLeave={(e) => e.currentTarget.style.backgroundColor = '#1a1a1a'}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                <span style={{
                  color,
                  fontWeight: 600,
                  fontSize: '0.85rem',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.3rem'
                }}>
                  {sub.status === 'Accepted' ? <CheckCircle2 size={15} /> : <XCircle size={15} />}
                  {sub.status}
                </span>

                <span style={{
                  backgroundColor: '#2d2d2d',
                  padding: '0.15rem 0.45rem',
                  borderRadius: '0.25rem',
                  fontSize: '0.75rem',
                  color: '#bbb',
                  textTransform: 'uppercase'
                }}>
                  {sub.language}
                </span>

                <span style={{ fontSize: '0.75rem', color: '#777', display: 'flex', alignItems: 'center', gap: '0.2rem' }}>
                  <Clock size={12} />
                  {sub.runtime_ms} ms
                </span>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <span style={{ fontSize: '0.75rem', color: '#666' }}>{date}</span>
                <ChevronRight size={14} color="#666" />
              </div>
            </div>
          );
        })}
      </div>

      {/* Code Inspector for Selected Submission */}
      {selectedSub && (
        <div style={{
          marginTop: '1rem',
          backgroundColor: '#161616',
          border: '1px solid #3a3a3a',
          borderRadius: '0.5rem',
          padding: '0.85rem'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
            <span style={{ fontSize: '0.8rem', fontWeight: 600, color: '#ccc', display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
              <Code size={14} color="#ffa116" />
              Submitted Code ({selectedSub.language})
            </span>
            <button
              onClick={() => setSelectedSub(null)}
              className="btn btn-ghost"
              style={{ fontSize: '0.75rem', padding: '0.2rem 0.4rem' }}
            >
              Close
            </button>
          </div>

          <pre style={{
            backgroundColor: '#111',
            padding: '0.75rem',
            borderRadius: '0.375rem',
            fontSize: '0.8rem',
            fontFamily: 'JetBrains Mono, monospace',
            overflowX: 'auto',
            maxHeight: '250px'
          }}>
            {selectedSub.code}
          </pre>
        </div>
      )}
    </div>
  );
}

