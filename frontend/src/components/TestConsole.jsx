import React, { useEffect, useRef, useState } from 'react';
import { Terminal, CheckCircle2, XCircle, AlertTriangle, Clock, Plus, Trash2, History, Sparkles, Loader2 } from 'lucide-react';
import SubmissionHistory from './SubmissionHistory';
import { generateTestCases } from '../services/api';
import LLMModel, { useLLMModel } from './LLMModel';

export default function TestConsole({
  testCases,
  onTestCasesChange,
  activeTab,
  onTabChange,
  runResult,
  submissionResult,
  problemId,
  submissions,
  executionStatus
}) {
  const [selectedCaseIdx, setSelectedCaseIdx] = useState(0);
  const [isGeneratingCases, setIsGeneratingCases] = useState(false);
  const [generateError, setGenerateError] = useState(null);
  const [usedModel, setUsedModel] = useState(null);
  const { model, ready } = useLLMModel();
  const active = useRef(true);
  const latestCases = useRef(testCases);
  latestCases.current = testCases;
  useEffect(() => {
    active.current = true;
    return () => { active.current = false; };
  }, []);

  const handleAddCase = () => {
    const newCases = [...(testCases || []), { input: '' }];
    onTestCasesChange(newCases);
    setSelectedCaseIdx(newCases.length - 1);
  };

  const handleRemoveCase = (index) => {
    if (testCases.length <= 1) return;
    const newCases = testCases.filter((_, i) => i !== index);
    onTestCasesChange(newCases);
    setSelectedCaseIdx(Math.max(0, index - 1));
  };

  const handleCaseChange = (field, value) => {
    const newCases = [...testCases];
    newCases[selectedCaseIdx] = {
      ...newCases[selectedCaseIdx],
      [field]: value
    };
    onTestCasesChange(newCases);
  };

  const handleGenerateTestCases = async () => {
    if (!problemId || isGeneratingCases || !ready) return;
    setIsGeneratingCases(true);
    setGenerateError(null);
    try {
      const res = await generateTestCases({ problemId, model });
      if (!active.current) return;
      if (res.success && Array.isArray(res.testCases) && res.testCases.length > 0) {
        const appended = [...(latestCases.current || []), ...res.testCases];
        onTestCasesChange(appended);
        setSelectedCaseIdx(latestCases.current?.length || 0);
        setUsedModel(res.model || model);
      } else {
        throw new Error('The AI returned no usable test cases. Please try again.');
      }
    } catch (err) {
      if (active.current) setGenerateError(err.message);
    } finally {
      if (active.current) setIsGeneratingCases(false);
    }
  };

  const getStatusBadge = (status) => {
    switch (status) {
      case 'Accepted':
        return (
          <span className="badge badge-accepted" style={{ display: 'flex', gap: '0.3rem' }}>
            <CheckCircle2 size={13} /> Accepted
          </span>
        );
      case 'Wrong Answer':
        return (
          <span className="badge badge-wrong" style={{ display: 'flex', gap: '0.3rem' }}>
            <XCircle size={13} /> Wrong Answer
          </span>
        );
      case 'Time Limit Exceeded':
      case 'Not Judged':
        return (
          <span className="badge badge-warning" style={{ display: 'flex', gap: '0.3rem' }}>
            <Clock size={13} /> {status}
          </span>
        );
      case 'Compilation Error':
      case 'Runtime Error':
      case 'Submission Error':
        return (
          <span className="badge badge-wrong" style={{ display: 'flex', gap: '0.3rem' }}>
            <AlertTriangle size={13} /> {status}
          </span>
        );
      default:
        return (
          <span className="badge badge-medium">
            {status || 'Finished'}
          </span>
        );
    }
  };

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      height: '100%',
      backgroundColor: '#202020',
      borderTop: '1px solid #333'
    }}>
      {/* Console Tab Headers */}
      <div className="test-console-toolbar" style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        borderBottom: '1px solid #333',
        padding: '0 0.5rem',
        backgroundColor: '#262626'
      }}>
        <div style={{ display: 'flex', gap: '0.25rem' }}>
          <button
            onClick={() => onTabChange('testcase')}
            style={{
              padding: '0.5rem 0.85rem',
              fontSize: '0.825rem',
              fontWeight: 500,
              background: 'none',
              border: 'none',
              color: activeTab === 'testcase' ? '#eff2f6' : '#9ea3ab',
              borderBottom: activeTab === 'testcase' ? '2px solid #ffa116' : '2px solid transparent',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '0.35rem'
            }}
          >
            <Terminal size={14} />
            Test Cases
          </button>
          <button
            onClick={() => onTabChange('result')}
            style={{
              padding: '0.5rem 0.85rem',
              fontSize: '0.825rem',
              fontWeight: 500,
              background: 'none',
              border: 'none',
              color: activeTab === 'result' ? '#eff2f6' : '#9ea3ab',
              borderBottom: activeTab === 'result' ? '2px solid #ffa116' : '2px solid transparent',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '0.35rem'
            }}
          >
            Test Result
            {(runResult || submissionResult) && (
              <span style={{
                width: 6,
                height: 6,
                borderRadius: '50%',
                backgroundColor: (runResult?.passed || submissionResult?.grading?.status === 'Accepted') ? '#2cbb5d' : '#ef4743'
              }} />
            )}
          </button>
          <button
            onClick={() => onTabChange('submissions')}
            style={{
              padding: '0.5rem 0.85rem',
              fontSize: '0.825rem',
              fontWeight: 500,
              background: 'none',
              border: 'none',
              color: activeTab === 'submissions' ? '#eff2f6' : '#9ea3ab',
              borderBottom: activeTab === 'submissions' ? '2px solid #ffa116' : '2px solid transparent',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '0.35rem'
            }}
          >
            <History size={14} />
            Submissions
          </button>
        </div>

        {activeTab === 'testcase' && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
            {/* Requirement (1): Generate Test Cases by Limitations */}
            <button
              onClick={handleGenerateTestCases}
              disabled={!problemId || isGeneratingCases || !ready}
              className="btn btn-secondary"
              title="Generate boundary and edge cases matching problem limitations"
              style={{
                fontSize: '0.725rem',
                padding: '0.2rem 0.5rem',
                color: '#ffa116',
                border: '1px solid rgba(255, 161, 22, 0.3)',
                display: 'flex',
                alignItems: 'center',
                gap: '0.3rem'
              }}
            >
              {isGeneratingCases ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} />}
              Generate Edge Cases
            </button>
            <button
              onClick={handleAddCase}
              className="btn btn-ghost"
              title="Add Custom Test Case"
              style={{ padding: '0.2rem 0.4rem', fontSize: '0.75rem', gap: '0.2rem' }}
            >
              <Plus size={14} /> Add Case
            </button>
          </div>
        )}
      </div>

      {activeTab === 'testcase' && <div style={{ padding: '0.3rem 0.85rem', borderBottom: '1px solid #333' }}><LLMModel usedModel={usedModel} /></div>}
      {generateError && (
        <div style={{ padding: '0.35rem 0.85rem', backgroundColor: '#381616', color: '#ff8d89', fontSize: '0.75rem' }}>
          Failed to generate test cases: {generateError}
        </div>
      )}

      {/* Tab 1: Test Cases Tab */}
      {activeTab === 'testcase' && (
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          {/* Case Pills */}
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.4rem',
            padding: '0.4rem 0.85rem',
            backgroundColor: '#1b1b1b',
            borderBottom: '1px solid #2d2d2d',
            overflowX: 'auto'
          }}>
            {(testCases || []).map((caseItem, idx) => (
              <div
                key={idx}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  borderRadius: '0.25rem',
                  backgroundColor: selectedCaseIdx === idx ? '#333' : '#222',
                  border: selectedCaseIdx === idx ? '1px solid #555' : '1px solid #2a2a2a',
                  padding: '0.15rem 0.35rem 0.15rem 0.55rem',
                  gap: '0.3rem'
                }}
              >
                <button
                  onClick={() => setSelectedCaseIdx(idx)}
                  style={{
                    background: 'none',
                    border: 'none',
                    color: selectedCaseIdx === idx ? '#eff2f6' : '#888',
                    fontSize: '0.75rem',
                    cursor: 'pointer'
                  }}
                >
                  Case {idx + 1}
                </button>
                {testCases.length > 1 && (
                  <button
                    onClick={() => handleRemoveCase(idx)}
                    style={{
                      background: 'none',
                      border: 'none',
                      color: '#666',
                      cursor: 'pointer',
                      padding: 0,
                      display: 'flex',
                      alignItems: 'center'
                    }}
                    title="Delete Case"
                  >
                    <Trash2 size={12} />
                  </button>
                )}
              </div>
            ))}
          </div>

          {/* Selected Case Inputs */}
          {!testCases?.length && <p style={{ padding: '1rem', color: '#aaa', fontSize: '0.8rem' }}>No test cases are available. Add a case with input and expected output, or generate edge cases before submitting for a verdict.</p>}
          {testCases && testCases[selectedCaseIdx] && (
            <div style={{ flex: 1, padding: '0.75rem 1rem', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '0.65rem' }}>
              {testCases[selectedCaseIdx].explanation && (
                <div style={{ fontSize: '0.75rem', color: '#ffa116', backgroundColor: '#282015', padding: '0.3rem 0.55rem', borderRadius: '0.25rem' }}>
                  💡 {testCases[selectedCaseIdx].explanation}
                </div>
              )}
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                <label style={{ fontSize: '0.75rem', color: '#888', fontWeight: 500 }}>Input:</label>
                <textarea
                  value={testCases[selectedCaseIdx].input || ''}
                  onChange={(e) => handleCaseChange('input', e.target.value)}
                  rows={3}
                  className="font-mono"
                  style={{
                    backgroundColor: '#161616',
                    border: '1px solid #333',
                    borderRadius: '0.375rem',
                    padding: '0.45rem 0.65rem',
                    color: '#eff2f6',
                    fontSize: '0.8rem',
                    resize: 'vertical'
                  }}
                  placeholder="Enter custom input..."
                />
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                <label style={{ fontSize: '0.75rem', color: '#888', fontWeight: 500 }}>Expected Output (needed for a verdict):</label>
                <textarea
                  value={testCases[selectedCaseIdx].output || ''}
                  onChange={(e) => handleCaseChange('output', e.target.value)}
                  rows={2}
                  className="font-mono"
                  style={{
                    backgroundColor: '#161616',
                    border: '1px solid #333',
                    borderRadius: '0.375rem',
                    padding: '0.45rem 0.65rem',
                    color: '#eff2f6',
                    fontSize: '0.8rem',
                    resize: 'vertical'
                  }}
                  placeholder="Enter expected output..."
                />
                {(testCases[selectedCaseIdx].output == null || testCases[selectedCaseIdx].output === '') && (
                  <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.75rem', color: '#aaa' }}>
                    <input
                      type="checkbox"
                      checked={testCases[selectedCaseIdx].output === ''}
                      onChange={(event) => handleCaseChange('output', event.target.checked ? '' : undefined)}
                    />
                    Expected output is intentionally empty
                  </label>
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Tab 2: Test Result Tab */}
      {activeTab === 'result' && (
        <div style={{ flex: 1, padding: '1rem', overflowY: 'auto' }}>
          {executionStatus && (
            <div role="status" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: '#ffa116', fontSize: '0.85rem' }}>
              <Loader2 size={16} className="animate-spin" />{executionStatus}
            </div>
          )}
          {/* Submission Result Verdict */}
          {submissionResult && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
                  {getStatusBadge(submissionResult.grading?.status)}
                  <span style={{ fontSize: '0.8rem', color: '#888' }}>
                    {submissionResult.grading?.passedTests} / {submissionResult.grading?.totalTests} test cases passed
                  </span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', color: '#888', fontSize: '0.8rem' }}>
                  <Clock size={13} />
                  <span>{submissionResult.grading?.totalRuntimeMs} ms</span>
                </div>
              </div>

              {submissionResult.grading?.error && (
                <div style={{
                  backgroundColor: '#301515',
                  border: '1px solid #5a2525',
                  padding: '0.65rem',
                  borderRadius: '0.375rem',
                  color: '#ff8d89',
                  fontSize: '0.8rem',
                  fontFamily: 'JetBrains Mono',
                  whiteSpace: 'pre-wrap'
                }}>
                  {submissionResult.grading.error}
                </div>
              )}
              {(submissionResult.grading?.results || submissionResult.submission?.test_results || []).map((result, index) => (
                <details key={index} open={result.passed === false} style={{ backgroundColor: '#181818', border: '1px solid #333', padding: '0.55rem', borderRadius: '0.35rem', fontSize: '0.8rem' }}>
                  <summary style={{ cursor: 'pointer', color: result.passed === true ? '#2cbb5d' : '#bbb' }}>Case {index + 1}: {result.status}{result.runtimeMs != null ? ` (${result.runtimeMs} ms)` : ''}</summary>
                  <div style={{ marginTop: '0.5rem' }}>Your output:</div>
                  <pre style={{ whiteSpace: 'pre-wrap' }}>{(result.actualOutput ?? result.stdout) || '<empty>'}</pre>
                  <div style={{ marginTop: '0.5rem' }}>Expected output:</div>
                  <pre style={{ whiteSpace: 'pre-wrap' }}>{result.expectedOutput == null ? 'Not provided; this case was not judged.' : result.expectedOutput || '<empty>'}</pre>
                  {(result.error || result.stderr) && <pre style={{ whiteSpace: 'pre-wrap', color: '#ff8d89' }}>{result.error || result.stderr}</pre>}
                </details>
              ))}
            </div>
          )}

          {/* Single Run Result */}
          {runResult && !submissionResult && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                {getStatusBadge(runResult.status)}
                <span style={{ fontSize: '0.8rem', color: '#888' }}>Runtime: {runResult.runtimeMs} ms</span>
              </div>

              {runResult.error && (
                <div style={{
                  backgroundColor: '#301515',
                  border: '1px solid #5a2525',
                  padding: '0.65rem',
                  borderRadius: '0.375rem',
                  color: '#ff8d89',
                  fontSize: '0.8rem',
                  fontFamily: 'JetBrains Mono',
                  whiteSpace: 'pre-wrap'
                }}>
                  {runResult.error}
                </div>
              )}

              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                <span style={{ fontSize: '0.75rem', color: '#888', fontWeight: 600 }}>Your Output:</span>
                <pre style={{
                  backgroundColor: '#161616',
                  padding: '0.5rem 0.75rem',
                  borderRadius: '0.375rem',
                  border: '1px solid #333',
                  fontSize: '0.825rem',
                  color: '#eff2f6',
                  whiteSpace: 'pre-wrap'
                }}>
                  {runResult.stdout || runResult.normalizedOutput || '<empty>'}
                </pre>
              </div>

              {runResult.expectedOutput && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                  <span style={{ fontSize: '0.75rem', color: '#888', fontWeight: 600 }}>Expected Output:</span>
                  <pre style={{
                    backgroundColor: '#161616',
                    padding: '0.5rem 0.75rem',
                    borderRadius: '0.375rem',
                    border: '1px solid #333',
                    fontSize: '0.825rem',
                    color: '#2cbb5d',
                    whiteSpace: 'pre-wrap'
                  }}>
                    {runResult.expectedOutput}
                  </pre>
                </div>
              )}
            </div>
          )}

          {!runResult && !submissionResult && !executionStatus && (
            <div style={{ color: '#888', fontSize: '0.825rem', textAlign: 'center', padding: '2rem 0' }}>
              Run code against custom input or Submit to evaluate all test cases.
            </div>
          )}
        </div>
      )}

      {/* Tab 3: Submissions Tab */}
      {activeTab === 'submissions' && (
        <div style={{ flex: 1, overflowY: 'auto' }}>
          <SubmissionHistory submissions={submissions} />
        </div>
      )}
    </div>
  );
}
