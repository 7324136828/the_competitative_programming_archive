import React, { useEffect, useState } from 'react';
import { Download, History, RefreshCw, ArrowRight, X } from 'lucide-react';
import { exportSubmissions, fetchAllSubmissions, fetchSubmissionRecord } from '../services/api';
import './SubmissionArchive.css';

function statusColor(status) {
  if (status === 'Accepted') return '#2cbb5d';
  if (['Queued', 'Compiling', 'Running', 'Not Judged'].includes(status)) return '#ffa116';
  return '#ff8d89';
}

function SubmissionInspector({ id, onClose, onSelectProblem }) {
  const [record, setRecord] = useState(null);
  const [error, setError] = useState(null);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setRecord(null);
    setError(null);
    fetchSubmissionRecord(id, { signal: controller.signal }).then(data => {
      if (!controller.signal.aborted) setRecord(data.submission);
    }).catch(err => { if (!controller.signal.aborted) setError(err.message); });
    return () => controller.abort();
  }, [id, attempt]);

  return (
    <section className="submission-inspector" aria-label={`Submission ${id} details`}>
      <div className="submission-archive-toolbar">
        <h2>Submission #{id}</h2>
        <button className="btn btn-ghost" aria-label="Close submission details" onClick={onClose}><X size={16} /> Close</button>
      </div>
      {error ? <div role="alert">{error} <button className="btn btn-secondary" onClick={() => setAttempt(value => value + 1)}>Retry details</button></div> : !record ? <p role="status">Loading submission...</p> : <>
        <div className="submission-archive-toolbar">
          <p><strong style={{ color: statusColor(record.status) }}>{record.status}</strong> · {record.language} · {record.runtime_ms ?? 0} ms · {record.created_at}</p>
          {record.problem_id && <button className="btn btn-secondary" onClick={() => onSelectProblem(record.problem_id)}>Open problem <ArrowRight size={14} /></button>}
        </div>
        <h3>Submitted code</h3>
        <pre aria-label="Submitted code">{record.code || '<empty source>'}</pre>
        <h3>Output</h3>
        <pre>{record.output || '<empty output>'}</pre>
        {record.error && <pre className="submission-error">{record.error}</pre>}
        <h3>Test results</h3>
        {(record.test_results || []).length === 0 && <p>No test results were recorded.</p>}
        {(record.test_results || []).map((result, index) => <details key={index} className="submission-case">
          <summary>Case {index + 1}: {result.status}{result.passed === false ? ' · failed' : ''}{result.runtimeMs != null ? ` · ${result.runtimeMs} ms` : ''}</summary>
          {result.input != null && <><h4>Input</h4><pre>{result.input || '<empty>'}</pre></>}
          <h4>Your output</h4>
          <pre>{(result.actualOutput ?? result.stdout) || '<empty>'}</pre>
          <h4>Expected output</h4>
          <pre>{result.expectedOutput == null ? 'Not provided; this case was not judged.' : result.expectedOutput || '<empty>'}</pre>
          {(result.error || result.stderr) && <pre className="submission-error">{result.error || result.stderr}</pre>}
        </details>)}
      </>}
    </section>
  );
}

export default function SubmissionArchive({ onSelectProblem }) {
  const [page, setPage] = useState(1);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [version, setVersion] = useState(0);
  const [selected, setSelected] = useState(null);
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState(null);
  const [exportNotice, setExportNotice] = useState(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);
    fetchAllSubmissions({ page, limit: 25, signal: controller.signal }).then(result => {
      if (controller.signal.aborted) return;
      if (page > Math.max(1, result.totalPages)) setPage(Math.max(1, result.totalPages));
      else setData(result);
    }).catch(err => { if (!controller.signal.aborted) setError(err.message); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [page, version]);

  const download = async () => {
    setExporting(true);
    setExportError(null);
    setExportNotice(null);
    try { await exportSubmissions(); setExportNotice('ZIP download started. Includes every submission, source file, and recorded result.'); }
    catch (err) { setExportError(err.message); }
    finally { setExporting(false); }
  };

  return (
    <div className="submission-archive">
      <div className="submission-archive-inner">
        <div className="submission-archive-toolbar">
          <div>
            <h1><History size={23} /> Submission history</h1>
            <p>Browse submitted solutions across all problems. Editor drafts are saved separately.</p>
          </div>
          <div className="submission-archive-actions">
            <button className="btn btn-secondary" disabled={loading} onClick={() => setVersion(value => value + 1)}><RefreshCw size={15} /> Refresh history</button>
            <button className="btn btn-primary" disabled={exporting} onClick={download}><Download size={15} /> {exporting ? 'Preparing ZIP...' : 'Export all submissions (ZIP)'}</button>
          </div>
        </div>
        {exportError && <p role="alert" className="submission-error">{exportError}</p>}
        {exportNotice && <p role="status">{exportNotice}</p>}
        {error ? <p role="alert" className="submission-error">{error} <button className="btn btn-secondary" onClick={() => setVersion(value => value + 1)}>Retry history</button></p> : loading ? <p role="status">Loading submission history...</p> : <>
          <p>{data?.total ?? 0} submissions</p>
          {data?.submissions?.length ? <div className="submission-table-scroll">
            <table className="submission-table">
              <thead><tr><th>Submission</th><th>Problem</th><th>Status</th><th>Language</th><th>Runtime</th><th>Submitted</th></tr></thead>
              <tbody>{data.submissions.map(record => <tr key={record.id} aria-selected={selected === record.id}>
                <td><button className="btn btn-ghost" aria-label={`View submission ${record.id}`} onClick={() => setSelected(record.id)}>#{record.id} · View</button></td>
                <td>{record.problem_title || `Problem #${record.problem_id}`}</td>
                <td style={{ color: statusColor(record.status), fontWeight: 600 }}>{record.status}</td>
                <td>{record.language}</td>
                <td>{record.runtime_ms ?? 0} ms</td>
                <td>{record.created_at}</td>
              </tr>)}</tbody>
            </table>
          </div> : <p>No submissions yet. Open a problem and submit a solution to start your history.</p>}
          <div className="submission-archive-toolbar submission-pagination">
            <button className="btn btn-secondary" disabled={page <= 1} onClick={() => setPage(value => value - 1)}>Previous page</button>
            <span>Page {page} of {Math.max(1, data?.totalPages ?? 1)}</span>
            <button className="btn btn-secondary" disabled={page >= (data?.totalPages ?? 1)} onClick={() => setPage(value => value + 1)}>Next page</button>
          </div>
        </>}
        {selected != null && <SubmissionInspector key={`${selected}-${version}`} id={selected} onClose={() => setSelected(null)} onSelectProblem={onSelectProblem} />}
      </div>
    </div>
  );
}
