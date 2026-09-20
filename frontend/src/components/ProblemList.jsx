import React, { useState, useEffect } from 'react';
import { Search, ChevronLeft, ChevronRight, Filter, Globe, BookOpen, CheckCircle2 } from 'lucide-react';
import { fetchProblems } from '../services/api';

export default function ProblemList({ onSelectProblem }) {
  const [problems, setProblems] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [search, setSearch] = useState('');
  const [language, setLanguage] = useState('all');
  const [difficulty, setDifficulty] = useState('all');
  const [loading, setLoading] = useState(false);

  const loadProblems = async () => {
    setLoading(true);
    try {
      const res = await fetchProblems({
        page,
        limit: 25,
        search,
        language,
        difficulty
      });
      if (res.success) {
        setProblems(res.problems);
        setTotal(res.total);
        setTotalPages(res.totalPages || 1);
      }
    } catch (err) {
      console.error('Failed to load problems:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadProblems();
  }, [page, language, difficulty]);

  const handleSearchSubmit = (e) => {
    e.preventDefault();
    setPage(1);
    loadProblems();
  };

  return (
    <div style={{ maxWidth: '1200px', margin: '0 auto', padding: '1.5rem', width: '100%' }}>
      {/* Header Banner */}
      <div style={{ marginBottom: '1.5rem' }}>
        <h1 style={{ fontSize: '1.75rem', fontWeight: 700, color: '#eff2f6', marginBottom: '0.35rem' }}>
          Problem Archive
        </h1>
        <p style={{ fontSize: '0.9rem', color: '#9ea3ab' }}>
          Practice competitive programming & coding interview questions with local C++, Python, and Java execution.
        </p>
      </div>

      {/* Filter and Search Bar */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        gap: '1rem',
        marginBottom: '1.25rem',
        flexWrap: 'wrap'
      }}>
        {/* Search */}
        <form onSubmit={handleSearchSubmit} style={{ display: 'flex', flex: '1', minWidth: '240px', maxWidth: '450px' }}>
          <div style={{
            position: 'relative',
            width: '100%',
            display: 'flex',
            alignItems: 'center'
          }}>
            <Search size={16} color="#777" style={{ position: 'absolute', left: '0.75rem' }} />
            <input
              type="text"
              placeholder="Search problems by title, tags, or description..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              style={{
                width: '100%',
                backgroundColor: '#262626',
                color: '#eff2f6',
                border: '1px solid #3a3a3a',
                borderRadius: '0.375rem',
                padding: '0.5rem 0.75rem 0.5rem 2.2rem',
                fontSize: '0.85rem',
                outline: 'none'
              }}
            />
          </div>
        </form>

        {/* Filters */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          {/* Language filter */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
            <Globe size={14} color="#888" />
            <select
              value={language}
              onChange={(e) => { setLanguage(e.target.value); setPage(1); }}
              style={{
                backgroundColor: '#262626',
                color: '#ccc',
                border: '1px solid #3a3a3a',
                borderRadius: '0.375rem',
                padding: '0.45rem 0.65rem',
                fontSize: '0.8rem',
                outline: 'none',
                cursor: 'pointer'
              }}
            >
              <option value="all">All Languages</option>
              <option value="en">English (en)</option>
              <option value="ai">AI Generated (ai)</option>
              <option value="ru">Russian (ru)</option>
            </select>
          </div>

          {/* Difficulty filter */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
            <Filter size={14} color="#888" />
            <select
              value={difficulty}
              onChange={(e) => { setDifficulty(e.target.value); setPage(1); }}
              style={{
                backgroundColor: '#262626',
                color: '#ccc',
                border: '1px solid #3a3a3a',
                borderRadius: '0.375rem',
                padding: '0.45rem 0.65rem',
                fontSize: '0.8rem',
                outline: 'none',
                cursor: 'pointer'
              }}
            >
              <option value="all">All Difficulties</option>
              <option value="Easy">Easy</option>
              <option value="Medium">Medium</option>
              <option value="Hard">Hard</option>
            </select>
          </div>
        </div>
      </div>

      {/* Problems Table */}
      <div style={{
        backgroundColor: '#222',
        border: '1px solid #333',
        borderRadius: '0.5rem',
        overflow: 'hidden'
      }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left' }}>
          <thead>
            <tr style={{ backgroundColor: '#282828', borderBottom: '1px solid #3a3a3a', color: '#9ea3ab', fontSize: '0.75rem', textTransform: 'uppercase' }}>
              <th style={{ padding: '0.75rem 1rem', width: '70px' }}>#</th>
              <th style={{ padding: '0.75rem 1rem' }}>Title</th>
              <th style={{ padding: '0.75rem 1rem', width: '120px' }}>Difficulty</th>
              <th style={{ padding: '0.75rem 1rem', width: '100px' }}>Language</th>
              <th style={{ padding: '0.75rem 1rem', width: '120px' }}>Testcases</th>
              <th style={{ padding: '0.75rem 1rem', width: '100px', textAlign: 'right' }}>Action</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={6} style={{ textAlign: 'center', padding: '3rem', color: '#888' }}>
                  Loading problems from database...
                </td>
              </tr>
            ) : problems.length === 0 ? (
              <tr>
                <td colSpan={6} style={{ textAlign: 'center', padding: '3rem', color: '#888' }}>
                  {search || language !== 'all' || difficulty !== 'all'
                    ? 'No problems matched your search criteria.'
                    : 'No problems in the database. Use Upload Problems to import a dataset.'}
                </td>
              </tr>
            ) : (
              problems.map((p) => {
                const sampleCount = (p.sample_input_output || []).length;
                return (
                  <tr
                    key={p.id}
                    onClick={() => onSelectProblem(p.id)}
                    style={{
                      borderBottom: '1px solid #2a2a2a',
                      cursor: 'pointer',
                      transition: 'background-color 0.1s'
                    }}
                    onMouseEnter={(e) => e.currentTarget.style.backgroundColor = '#292929'}
                    onMouseLeave={(e) => e.currentTarget.style.backgroundColor = 'transparent'}
                  >
                    <td style={{ padding: '0.85rem 1rem', fontSize: '0.85rem', color: '#777', fontWeight: 600 }}>
                      {p.id}
                    </td>

                    <td style={{ padding: '0.85rem 1rem' }}>
                      <div style={{ display: 'flex', flexDirection: 'column' }}>
                        <span style={{ fontSize: '0.9rem', fontWeight: 600, color: '#eff2f6' }}>
                          {p.title}
                        </span>
                        {p.tags && p.tags.length > 0 && (
                          <div style={{ display: 'flex', gap: '0.3rem', marginTop: '0.2rem' }}>
                            {p.tags.slice(0, 3).map((tag, tIdx) => (
                              <span key={tIdx} style={{ fontSize: '0.65rem', color: '#888' }}>
                                #{tag}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    </td>

                    <td style={{ padding: '0.85rem 1rem' }}>
                      <span className={`badge badge-${p.difficulty ? p.difficulty.toLowerCase() : 'medium'}`}>
                        {p.difficulty || 'Medium'}
                      </span>
                    </td>

                    <td style={{ padding: '0.85rem 1rem' }}>
                      <span style={{
                        fontSize: '0.75rem',
                        backgroundColor: p.language === 'ai' ? '#302616' : '#2e2e2e',
                        padding: '0.15rem 0.45rem',
                        borderRadius: '0.25rem',
                        color: p.language === 'ai' ? '#ffa116' : '#bbb',
                        border: p.language === 'ai' ? '1px solid #523e1d' : 'none',
                        textTransform: 'uppercase'
                      }}>
                        {p.language || 'en'}
                      </span>
                    </td>

                    <td style={{ padding: '0.85rem 1rem', fontSize: '0.8rem', color: '#9ea3ab' }}>
                      {sampleCount > 0 ? `${sampleCount} sample${sampleCount > 1 ? 's' : ''}` : 'No samples'}
                    </td>

                    <td style={{ padding: '0.85rem 1rem', textAlign: 'right' }}>
                      <button className="btn btn-secondary" style={{ fontSize: '0.75rem', padding: '0.3rem 0.65rem' }}>
                        Solve
                      </button>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>

        {/* Pagination Footer */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '0.75rem 1rem',
          backgroundColor: '#262626',
          borderTop: '1px solid #333'
        }}>
          <span style={{ fontSize: '0.8rem', color: '#888' }}>
            Showing page {page} of {totalPages} ({total} total problems)
          </span>

          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <button
              onClick={() => setPage(p => Math.max(1, p - 1))}
              disabled={page <= 1}
              className="btn btn-secondary"
              style={{ padding: '0.3rem 0.6rem', fontSize: '0.8rem', opacity: page <= 1 ? 0.4 : 1 }}
            >
              <ChevronLeft size={15} /> Prev
            </button>

            <span style={{ fontSize: '0.8rem', color: '#ccc', padding: '0 0.4rem' }}>
              {page} / {totalPages}
            </span>

            <button
              onClick={() => setPage(p => Math.min(totalPages, p + 1))}
              disabled={page >= totalPages}
              className="btn btn-secondary"
              style={{ padding: '0.3rem 0.6rem', fontSize: '0.8rem', opacity: page >= totalPages ? 0.4 : 1 }}
            >
              Next <ChevronRight size={15} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

