import React, { useEffect, useState } from 'react';
import { Compass, ArrowRight, Loader2 } from 'lucide-react';
import { fetchRecommendations } from '../services/api';

export default function RecommendationList({ problemId, onSelectProblem }) {
  const [recommendations, setRecommendations] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!problemId) return;
    let active = true;

    async function load() {
      setLoading(true);
      try {
        const res = await fetchRecommendations({ problemId });
        if (active && res.success) {
          setRecommendations(res.recommendations);
        }
      } catch (e) {
        console.error('Failed to load recommendations', e);
      } finally {
        if (active) setLoading(false);
      }
    }

    load();
    return () => { active = false; };
  }, [problemId]);

  if (loading) {
    return (
      <div style={{ padding: '1rem', textAlign: 'center', color: '#888', fontSize: '0.8rem' }}>
        <Loader2 size={16} className="animate-spin" style={{ display: 'inline', marginRight: '0.4rem' }} />
        Computing AI recommendations...
      </div>
    );
  }

  if (recommendations.length === 0) return null;

  return (
    <div style={{
      backgroundColor: '#202020',
      border: '1px solid #333',
      borderRadius: '0.5rem',
      padding: '0.85rem',
      display: 'flex',
      flexDirection: 'column',
      gap: '0.65rem'
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
        <div style={{
          backgroundColor: 'rgba(0, 184, 163, 0.15)',
          color: '#00b8a3',
          padding: '0.3rem',
          borderRadius: '0.375rem',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center'
        }}>
          <Compass size={16} />
        </div>
        <div>
          <h4 style={{ fontSize: '0.875rem', fontWeight: 600, color: '#eff2f6' }}>Recommended Problems</h4>
          <p style={{ fontSize: '0.75rem', color: '#888' }}>
            Curated by AI to reinforce patterns from this problem
          </p>
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.45rem' }}>
        {recommendations.map((rec) => (
          <div
            key={rec.id}
            onClick={() => onSelectProblem(rec.id)}
            style={{
              backgroundColor: '#191919',
              border: '1px solid #363636',
              borderRadius: '0.375rem',
              padding: '0.6rem 0.75rem',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              transition: 'all 0.15s ease'
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.backgroundColor = '#232323';
              e.currentTarget.style.borderColor = '#555';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.backgroundColor = '#191919';
              e.currentTarget.style.borderColor = '#363636';
            }}
          >
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.2rem', overflow: 'hidden' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <span style={{ fontSize: '0.825rem', fontWeight: 600, color: '#eff2f6' }}>
                  {rec.title}
                </span>
                <span className={`badge badge-${rec.difficulty ? rec.difficulty.toLowerCase() : 'medium'}`}>
                  {rec.difficulty || 'Medium'}
                </span>
              </div>
              <span style={{ fontSize: '0.725rem', color: '#9ea3ab' }}>
                {rec.recommendationReason}
              </span>
            </div>

            <ArrowRight size={14} color="#777" style={{ flexShrink: 0, marginLeft: '0.5rem' }} />
          </div>
        ))}
      </div>
    </div>
  );
}

