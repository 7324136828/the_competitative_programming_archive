import React, { useState, useEffect, useRef } from 'react';
import confetti from 'canvas-confetti';
import { AlertCircle, CheckCircle2, Sparkles, MessageSquare } from 'lucide-react';
import SolveWorkspace from '../SolveWorkspace';
import ProblemDetail from '../ProblemDetail';
import CodeEditor from '../CodeEditor';
import TestConsole from '../TestConsole';
import ChatDrawer from '../ChatDrawer';
import TranslateModal from '../TranslateModal';
import useEditorDraft from '../../hooks/useEditorDraft';
import { CODE_TEMPLATES, DEFAULT_LANGUAGE } from '../../utils/codeTemplates';
import { fetchProblem, runCode, submitCode, fetchSubmissions, fetchLanguages } from '../../services/api';
import { api } from '../../api/client';
import { Issue } from '../../types';

interface CodingActivityProps {
  issue: Issue;
  onStatusUpdated?: (newStatus: string) => void;
  onClose: () => void;
}

export const CodingActivity: React.FC<CodingActivityProps> = ({
  issue,
  onStatusUpdated,
  onClose,
}) => {
  const [problem, setProblem] = useState<any>(null);
  const [loadingProblem, setLoadingProblem] = useState(true);
  const [testCases, setTestCases] = useState<any[]>([]);
  const [submissions, setSubmissions] = useState<any[]>([]);
  const [consoleTab, setConsoleTab] = useState<'testcase' | 'result' | 'submissions'>('testcase');
  const [runResult, setRunResult] = useState<any>(null);
  const [submissionResult, setSubmissionResult] = useState<any>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [executionStatus, setExecutionStatus] = useState<string | null>(null);
  const [statusNotice, setStatusNotice] = useState<{ type: 'success' | 'info' | 'error'; text: string } | null>(null);

  // Language & editor draft
  const [language, setLanguage] = useState(DEFAULT_LANGUAGE);
  const [availableLanguages, setAvailableLanguages] = useState<any[]>([]);
  const [isLoadingLanguages, setIsLoadingLanguages] = useState(true);
  const [languagesError, setLanguagesError] = useState<string | null>(null);
  const [isChatOpen, setIsChatOpen] = useState(false);
  const [isTranslateOpen, setIsTranslateOpen] = useState(false);
  const [translatedData, setTranslatedData] = useState<any>(null);

  const execution = useRef<AbortController | null>(null);
  const activeProblemId = issue.problem_id || issue.key;

  const draft = useEditorDraft(
    activeProblemId,
    language,
    Boolean(activeProblemId && !loadingProblem)
  );

  // Load languages
  useEffect(() => {
    const controller = new AbortController();
    setIsLoadingLanguages(true);
    setLanguagesError(null);

    fetchLanguages({ signal: controller.signal })
      .then(langs => {
        if (controller.signal.aborted) return;
        const supported = langs.filter((item: any) => Object.hasOwn(CODE_TEMPLATES, item.id));
        setAvailableLanguages(supported);
        setLanguage((curr: string) => {
          if (supported.some((item: any) => item.id === curr)) return curr;
          return supported.find((item: any) => item.id === DEFAULT_LANGUAGE)?.id || supported[0]?.id || '';
        });
      })
      .catch((err: any) => {
        if (controller.signal.aborted) return;
        setAvailableLanguages([]);
        setLanguagesError(err.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setIsLoadingLanguages(false);
      });

    return () => controller.abort();
  }, []);

  const isLanguageAvailable = !isLoadingLanguages && !languagesError && availableLanguages.some((item: any) => item.id === language);

  // Load problem statement and details
  useEffect(() => {
    let unmounted = false;
    setLoadingProblem(true);

    const fallbackProblem = {
      id: issue.problem_id || issue.key,
      title: issue.summary,
      problem_statements: issue.description || 'Solve this programming challenge.',
      difficulty: issue.difficulty || 'Medium',
      sample_input_output: issue.sample_input_output || [],
      hints: issue.hints || [],
      tags: issue.tags || [],
      is_solved: (issue.submission_status || '').toLowerCase() === 'accepted' || issue.status === 'Done',
      source: `Story ${issue.key}`,
      language: 'en'
    };

    if (issue.problem_id) {
      fetchProblem(issue.problem_id)
        .then(res => {
          if (unmounted) return;
          if (res.success && res.problem) {
            setProblem(res.problem);
            setTestCases(res.problem.sample_input_output?.length ? res.problem.sample_input_output : fallbackProblem.sample_input_output);
          } else {
            setProblem(fallbackProblem);
            setTestCases(fallbackProblem.sample_input_output);
          }
        })
        .catch(() => {
          if (unmounted) return;
          setProblem(fallbackProblem);
          setTestCases(fallbackProblem.sample_input_output);
        })
        .finally(() => {
          if (!unmounted) setLoadingProblem(false);
        });

      // Load past submissions
      fetchSubmissions(issue.problem_id)
        .then(res => {
          if (unmounted) return;
          if (res.success) setSubmissions(res.submissions || []);
        })
        .catch(() => {});
    } else {
      setProblem(fallbackProblem);
      setTestCases(fallbackProblem.sample_input_output);
      setLoadingProblem(false);
    }

    return () => {
      unmounted = true;
      execution.current?.abort();
    };
  }, [issue.id, issue.problem_id, issue.summary, issue.description]);

  // Handle run code
  const handleRunCode = async () => {
    if (!problem || loadingProblem || !draft.ready || !isLanguageAvailable || isRunning || isSubmitting) return;
    const controller = new AbortController();
    execution.current = controller;
    setIsRunning(true);
    setRunResult(null);
    setSubmissionResult(null);
    setExecutionStatus(language === 'cpp' || language === 'java' ? 'Compiling and running...' : 'Running code...');
    setConsoleTab('result');

    const activeCase = testCases[0] || { input: '' };
    try {
      const res = await runCode({
        language,
        code: draft.code,
        input: activeCase.input,
        expectedOutput: activeCase.output,
        timeoutMs: 5000,
      }, { signal: controller.signal });

      if (controller.signal.aborted) return;
      if (res.success) {
        setRunResult(res.result);
      }
    } catch (err: any) {
      if (controller.signal.aborted) return;
      setRunResult({
        status: 'Runtime Error',
        error: err.message,
        stdout: '',
        runtimeMs: 0,
      });
    } finally {
      if (!controller.signal.aborted) {
        setIsRunning(false);
        setExecutionStatus(null);
      }
    }
  };

  // Handle submit code
  const handleSubmitCode = async () => {
    if (!problem || loadingProblem || !draft.ready || !isLanguageAvailable || isRunning || isSubmitting) return;
    const controller = new AbortController();
    execution.current = controller;
    setIsSubmitting(true);
    setRunResult(null);
    setSubmissionResult(null);
    setStatusNotice(null);
    setExecutionStatus('Queued for judging...');
    setConsoleTab('result');

    try {
      const res = await submitCode({
        problemId: issue.problem_id || 1, // Fallback to problem 1 if not linked
        language,
        code: draft.code,
        customTestCases: testCases,
      }, {
        signal: controller.signal,
        onProgress: (job: any) => {
          if (controller.signal.aborted) return;
          const labels: Record<string, string> = {
            queued: 'Queued for judging...',
            compiling: 'Compiling code...',
            running: 'Running test cases...',
          };
          setExecutionStatus(labels[job.phase] || job.status || 'Judging submission...');
        }
      });

      if (controller.signal.aborted) return;
      if (res.success) {
        setSubmissionResult(res);
        setExecutionStatus(null);

        const verdict = res.grading?.status || 'Unknown';

        // Sync with Jira issue backend
        try {
          await api.submitCodingResult(issue.id, {
            verdict,
            test_results: res.grading,
          });
        } catch (e) {
          console.warn('Backend sync error:', e);
        }

        if (verdict === 'Accepted') {
          confetti({
            particleCount: 100,
            spread: 70,
            origin: { y: 0.6 }
          });
          setProblem((curr: any) => curr ? { ...curr, is_solved: true } : curr);
          setStatusNotice({
            type: 'success',
            text: `🎉 Problem Accepted! Story ${issue.key} has been automatically marked as "Done".`,
          });
          onStatusUpdated?.('Done');
        } else {
          setStatusNotice({
            type: 'info',
            text: `Submission verdict: ${verdict}. Status transitioned to "In Progress". Please fix errors and resubmit to achieve "Done".`,
          });
          onStatusUpdated?.('In Progress');
        }

        // Refresh submission list
        if (issue.problem_id) {
          fetchSubmissions(issue.problem_id).then(subRes => {
            if (subRes?.success) setSubmissions(subRes.submissions || []);
          }).catch(() => {});
        }
      }
    } catch (err: any) {
      if (controller.signal.aborted) return;
      setSubmissionResult({
        grading: {
          status: 'Submission Error',
          totalTests: 0,
          passedTests: 0,
          totalRuntimeMs: 0,
          error: err.message,
        }
      });
      setStatusNotice({
        type: 'error',
        text: `Submission error: ${err.message}`,
      });
    } finally {
      if (!controller.signal.aborted) {
        setIsSubmitting(false);
        setExecutionStatus(null);
      }
    }
  };

  const handleLanguageChange = (newLang: string) => {
    if (availableLanguages.some((item: any) => item.id === newLang)) {
      setLanguage(newLang);
    }
  };

  const handleCodeChange = (newCode: string) => {
    if (!isLanguageAvailable || !draft.ready) return;
    draft.change(newCode);
  };

  const handleImportCode = async (source: any, isCurrent: boolean) => {
    if (!isLanguageAvailable || !draft.ready) return false;
    const imported = await draft.importCode(source.language, source.code, isCurrent);
    if (imported) setLanguage(source.language);
    return imported;
  };

  return (
    <div className="flex-1 flex flex-col h-full bg-[#1e1e1e] text-gray-200 overflow-hidden relative">
      {/* Top Banner Notice if submission verdict changed status */}
      {statusNotice && (
        <div className={`px-4 py-2 flex items-center justify-between text-xs z-30 font-medium ${
          statusNotice.type === 'success' ? 'bg-emerald-900/80 text-emerald-200 border-b border-emerald-700' :
          statusNotice.type === 'error' ? 'bg-rose-900/80 text-rose-200 border-b border-rose-700' :
          'bg-amber-900/80 text-amber-200 border-b border-amber-700'
        }`}>
          <div className="flex items-center space-x-2">
            {statusNotice.type === 'success' ? <CheckCircle2 className="w-4 h-4 text-emerald-400" /> : <AlertCircle className="w-4 h-4 text-amber-400" />}
            <span>{statusNotice.text}</span>
          </div>
          <button onClick={() => setStatusNotice(null)} className="text-gray-400 hover:text-white ml-4 text-sm font-bold">
            &times;
          </button>
        </div>
      )}

      {/* Main Resizable Split Workspace */}
      <div className="flex-1 flex overflow-hidden">
        <SolveWorkspace
          problem={
            <ProblemDetail
              problem={problem}
              translatedData={translatedData}
              onOpenTranslate={() => setIsTranslateOpen(true)}
              onOpenGenerateSimilar={() => {}}
              onSelectProblem={() => {}}
              onResetTranslation={() => setTranslatedData(null)}
            />
          }
          editor={
            <CodeEditor
              language={language}
              availableLanguages={availableLanguages}
              isLoadingLanguages={isLoadingLanguages}
              languagesError={languagesError}
              onRetryLanguages={() => {}}
              onLanguageChange={handleLanguageChange}
              code={draft.code}
              onCodeChange={handleCodeChange}
              onImportCode={handleImportCode}
              draft={draft}
              onRun={handleRunCode}
              onSubmit={handleSubmitCode}
              isRunning={isRunning}
              isSubmitting={isSubmitting}
              executionDisabled={loadingProblem || !problem || !draft.ready}
            />
          }
          tests={
            <TestConsole
              key={problem?.id || 'empty'}
              testCases={testCases}
              onTestCasesChange={setTestCases}
              activeTab={consoleTab}
              onTabChange={setConsoleTab}
              runResult={runResult}
              submissionResult={submissionResult}
              problemId={problem?.id}
              submissions={submissions}
              executionStatus={executionStatus}
            />
          }
        />
      </div>

      {/* AI Assistant Chat Trigger Floating Button */}
      <button
        onClick={() => setIsChatOpen(!isChatOpen)}
        className="fixed bottom-4 right-4 z-40 px-3.5 py-2 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 text-white rounded-full shadow-lg flex items-center space-x-2 text-xs font-semibold transition transform hover:scale-105"
        title="Open AI Coding Tutor"
      >
        <Sparkles className="w-4 h-4" />
        <span>AI Tutor</span>
      </button>

      {/* AI Chat Drawer */}
      <ChatDrawer
        isOpen={isChatOpen}
        onClose={() => setIsChatOpen(false)}
        currentProblem={problem}
        currentCode={draft.code}
        currentLanguage={language}
      />

      {/* Translate Modal */}
      <TranslateModal
        isOpen={isTranslateOpen}
        onClose={() => setIsTranslateOpen(false)}
        problem={problem}
        onApplyTranslation={(data: any) => setTranslatedData(data)}
      />
    </div>
  );
};
