import React, { useState } from 'react';
import { Upload, X, Check, AlertCircle, FileText, Loader2 } from 'lucide-react';
import { uploadProblemsFile, uploadProblemsJson } from '../services/api';

export default function UploadModal({ isOpen, onClose, onUploadComplete }) {
  const [file, setFile] = useState(null);
  const [jsonText, setJsonText] = useState('');
  const [tab, setTab] = useState('file'); // 'file' or 'text'
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  if (!isOpen) return null;

  const handleClose = () => {
    if (!loading) onClose();
  };

  const handleFileChange = (e) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
      setError(null);
      setResult(null);
    }
  };

  const handleUpload = async () => {
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      let res;
      if (tab === 'file') {
        if (!file) {
          throw new Error('Please select a JSON file first.');
        }
        res = await uploadProblemsFile(file);
      } else {
        if (!jsonText.trim()) {
          throw new Error('Please paste valid JSON text.');
        }
        const parsed = JSON.parse(jsonText);
        res = await uploadProblemsJson(parsed);
      }

      if (res.success) {
        setResult(res);
        if (onUploadComplete) {
          onUploadComplete();
        }
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="modal-overlay" onClick={handleClose}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()} style={{ maxWidth: '620px' }}>
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
              <Upload size={18} />
            </div>
            <div>
              <h3 style={{ fontSize: '1rem', fontWeight: 600, color: '#eff2f6' }}>Upload Problems Dataset</h3>
              <p style={{ fontSize: '0.75rem', color: '#888' }}>
                Import and persist problems from a problems.json file into the SQLite database
              </p>
            </div>
          </div>

          <button onClick={handleClose} disabled={loading} className="btn btn-ghost" style={{ padding: '0.3rem' }}>
            <X size={18} />
          </button>
        </div>

        {/* Body */}
        <div style={{ padding: '1.25rem', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          {/* Method Tabs */}
          <div style={{ display: 'flex', gap: '0.5rem', borderBottom: '1px solid #333', paddingBottom: '0.5rem' }}>
            <button
              onClick={() => setTab('file')}
              className={`btn ${tab === 'file' ? 'btn-primary' : 'btn-ghost'}`}
              style={{ fontSize: '0.8rem', padding: '0.3rem 0.8rem' }}
            >
              Upload File (.json)
            </button>
            <button
              onClick={() => setTab('text')}
              className={`btn ${tab === 'text' ? 'btn-primary' : 'btn-ghost'}`}
              style={{ fontSize: '0.8rem', padding: '0.3rem 0.8rem' }}
            >
              Paste JSON
            </button>
          </div>

          {tab === 'file' ? (
            <div style={{
              border: '2px dashed #444',
              borderRadius: '0.5rem',
              padding: '2rem 1rem',
              textAlign: 'center',
              backgroundColor: '#191919'
            }}>
              <input
                type="file"
                id="problem-file-input"
                accept=".json"
                onChange={handleFileChange}
                style={{ display: 'none' }}
              />
              <label htmlFor="problem-file-input" style={{ cursor: 'pointer', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '0.5rem' }}>
                <FileText size={32} color="#ffa116" />
                <span style={{ fontSize: '0.85rem', color: '#eff2f6', fontWeight: 500 }}>
                  {file ? file.name : 'Click to browse or drop problems.json'}
                </span>
                <span style={{ fontSize: '0.75rem', color: '#888' }}>
                  Supports problems.json format (700+ problems or custom arrays)
                </span>
              </label>
            </div>
          ) : (
            <div>
              <textarea
                value={jsonText}
                onChange={(e) => setJsonText(e.target.value)}
                placeholder='Paste {"problems": [...]} or [{ "title": "...", "problem_statements": "...", "source": "https://2025.andgein.ru/about-tasks" }]'
                rows={8}
                style={{
                  width: '100%',
                  backgroundColor: '#181818',
                  color: '#eff2f6',
                  border: '1px solid #3a3a3a',
                  borderRadius: '0.375rem',
                  padding: '0.65rem',
                  fontFamily: 'JetBrains Mono, monospace',
                  fontSize: '0.8rem',
                  outline: 'none',
                  resize: 'vertical'
                }}
              />
            </div>
          )}

          <p style={{ fontSize: '0.75rem', color: '#aaa', lineHeight: 1.5 }}>
            Each problem may include an optional <code>source</code> URL or name, shown alongside its title.
          </p>

          {error && (
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.4rem',
              color: '#ef4743',
              fontSize: '0.8rem',
              backgroundColor: 'rgba(239, 71, 67, 0.1)',
              padding: '0.5rem 0.75rem',
              borderRadius: '0.375rem'
            }}>
              <AlertCircle size={15} />
              <span>{error}</span>
            </div>
          )}

          {result && (
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.4rem',
              color: '#2cbb5d',
              fontSize: '0.825rem',
              backgroundColor: 'rgba(44, 187, 93, 0.1)',
              padding: '0.6rem 0.75rem',
              borderRadius: '0.375rem',
              fontWeight: 500
            }}>
              <Check size={16} />
              <span>{result.message} Total problems in DB now: {result.totalNow}</span>
            </div>
          )}

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.6rem', marginTop: '0.5rem' }}>
            <button onClick={handleClose} disabled={loading} className="btn btn-secondary">
              Cancel
            </button>
            <button
              onClick={handleUpload}
              disabled={loading || (tab === 'file' && !file) || (tab === 'text' && !jsonText.trim())}
              className="btn btn-primary"
            >
              {loading ? (
                <>
                  <Loader2 size={15} className="animate-spin" />
                  Importing...
                </>
              ) : (
                <>
                  <Upload size={15} />
                  Import and Persist
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

