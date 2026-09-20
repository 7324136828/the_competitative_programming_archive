import React, { useState, useEffect, useRef } from 'react';
import confetti from 'canvas-confetti';
import Navbar from './components/Navbar';
import ProblemList from './components/ProblemList';
import ProblemDetail from './components/ProblemDetail';
import CodeEditor from './components/CodeEditor';
import TestConsole from './components/TestConsole';
import TranslateModal from './components/TranslateModal';
import GenerateProblemModal from './components/GenerateProblemModal';
import UploadModal from './components/UploadModal';
import ChatDrawer from './components/ChatDrawer';
import LLMModel from './components/LLMModel';
import SolveWorkspace from './components/SolveWorkspace';
import SubmissionArchive from './components/SubmissionArchive';
import SettingsView from './components/SettingsView';
import useEditorDraft from './hooks/useEditorDraft';
import { CODE_TEMPLATES, DEFAULT_LANGUAGE } from './utils/codeTemplates';
import { clearDatabase, fetchProblem, runCode, submitCode, fetchSubmissions, fetchProblems, fetchLanguages } from './services/api';

export default function App() {
  const [view, setView] = useState('list');
  const [problemId, setProblemId] = useState(null);
  const [problem, setProblem] = useState(null);
  const [loadingProblem, setLoadingProblem] = useState(false);
  const [databaseVersion, setDatabaseVersion] = useState(0);
  const [archiveVersion, setArchiveVersion] = useState(0);
  const [isClearingDatabase, setIsClearingDatabase] = useState(false);
  const [databaseNotice, setDatabaseNotice] = useState(null);
  const problemRequest = useRef(0);
  const databaseGeneration = useRef(0);
  const clearingDatabase = useRef(false);
  const execution = useRef(null);

  // Editor State
  const [language, setLanguage] = useState(DEFAULT_LANGUAGE);
  const [availableLanguages, setAvailableLanguages] = useState([]);
  const [isLoadingLanguages, setIsLoadingLanguages] = useState(true);
  const [languagesError, setLanguagesError] = useState(null);
  const [languageDetectionVersion, setLanguageDetectionVersion] = useState(0);
  const draft = useEditorDraft(problemId, language, view === 'solve' && problem?.id === problemId && !loadingProblem);

  // Test Console State
  const [testCases, setTestCases] = useState([]);
  const [consoleTab, setConsoleTab] = useState('testcase'); // 'testcase', 'result', 'submissions'
  const [runResult, setRunResult] = useState(null);
  const [submissionResult, setSubmissionResult] = useState(null);
  const [submissions, setSubmissions] = useState([]);
  const [isRunning, setIsRunning] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [executionStatus, setExecutionStatus] = useState(null);

  useEffect(() => () => execution.current?.abort(), []);

  // Modals & AI State
  const [isUploadOpen, setIsUploadOpen] = useState(false);
  const [isTranslateOpen, setIsTranslateOpen] = useState(false);
  const [isGenerateOpen, setIsGenerateOpen] = useState(false);
  const [isChatOpen, setIsChatOpen] = useState(false);
  const [translatedData, setTranslatedData] = useState(null);

  useEffect(() => {
    const controller = new AbortController();
    setIsLoadingLanguages(true);
    setLanguagesError(null);

    fetchLanguages({ signal: controller.signal })
      .then(languages => {
        if (controller.signal.aborted) return;
        const supportedLanguages = languages.filter(item => Object.hasOwn(CODE_TEMPLATES, item.id));
        setAvailableLanguages(supportedLanguages);
        setLanguage(current => {
          if (supportedLanguages.some(item => item.id === current)) return current;
          return supportedLanguages.find(item => item.id === DEFAULT_LANGUAGE)?.id || supportedLanguages[0]?.id || '';
        });
      })
      .catch(err => {
        if (controller.signal.aborted) return;
        setAvailableLanguages([]);
        setLanguagesError(err.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setIsLoadingLanguages(false);
      });

    return () => controller.abort();
  }, [languageDetectionVersion]);

  const isLanguageAvailable = !isLoadingLanguages && !languagesError && availableLanguages.some(item => item.id === language);

  // Load problem details
  const loadProblemData = async (id) => {
    const request = ++problemRequest.current;
    execution.current?.abort();
    setIsRunning(false);
    setIsSubmitting(false);
    setExecutionStatus(null);
    setLoadingProblem(true);
    setProblem(null);
    setTestCases([]);
    setSubmissions([]);
    setRunResult(null);
    setSubmissionResult(null);
    setTranslatedData(null);
    try {
      const res = await fetchProblem(id);
      if (request !== problemRequest.current) return;
      if (res.success && res.problem) {
        setProblem(res.problem);
        setTestCases(res.problem.sample_input_output || []);
      }
      // Load submissions
      const subRes = await fetchSubmissions(id);
      if (request !== problemRequest.current) return;
      if (subRes.success) {
        setSubmissions(subRes.submissions);
      }
    } catch (err) {
      console.error('Error loading problem:', err);
    } finally {
      if (request === problemRequest.current) setLoadingProblem(false);
    }
  };

  useEffect(() => {
    if (problemId) {
      loadProblemData(problemId);
    }
  }, [problemId]);

  const handleSelectProblem = (id) => {
    if (clearingDatabase.current) return;
    if (id !== problemId) execution.current?.abort();
    setProblemId(id);
    setView('solve');
  };

  const handleRandomProblem = async () => {
    if (clearingDatabase.current) return;
    const generation = databaseGeneration.current;
    try {
      const list = await fetchProblems({ limit: 50 });
      if (generation !== databaseGeneration.current || clearingDatabase.current) return;
      if (list.success && list.problems.length > 0) {
        const randomIndex = Math.floor(Math.random() * list.problems.length);
        const randomP = list.problems[randomIndex];
        handleSelectProblem(randomP.id);
      }
    } catch (e) {
      console.error('Error picking random problem:', e);
    }
  };

  const handleClearDatabase = async () => {
    if (clearingDatabase.current || isRunning || isSubmitting || isUploadOpen || isTranslateOpen || isGenerateOpen) return;
    if (!window.confirm('Permanently delete ALL problems, submission history, and saved editor draft references from the database? Your current workspace will also be reset. This cannot be undone.')) return;

    clearingDatabase.current = true;
    setIsClearingDatabase(true);
    setDatabaseNotice(null);
    databaseGeneration.current += 1;
    problemRequest.current += 1;

    try {
      const result = await clearDatabase();
      setProblemId(null);
      setProblem(null);
      setLoadingProblem(false);
      setTranslatedData(null);
      setTestCases([]);
      setRunResult(null);
      setSubmissionResult(null);
      setSubmissions([]);
      setConsoleTab('testcase');
      setLanguage(availableLanguages.find(item => item.id === DEFAULT_LANGUAGE)?.id || availableLanguages[0]?.id || '');
      draft.clear();
      setIsUploadOpen(false);
      setIsTranslateOpen(false);
      setIsGenerateOpen(false);
      setDatabaseVersion(version => version + 1);
      setView('list');
      setDatabaseNotice({
        type: 'success',
        message: `Database cleared: ${result.deletedProblems} problems and ${result.deletedSubmissions} submissions deleted.`
      });
    } catch (err) {
      setDatabaseNotice({ type: 'error', message: err.message });
      if (loadingProblem && problemId) loadProblemData(problemId);
    } finally {
      clearingDatabase.current = false;
      setIsClearingDatabase(false);
    }
  };

  const handleLanguageChange = (newLang) => {
    if (availableLanguages.some(item => item.id === newLang)) setLanguage(newLang);
  };

  const handleCodeChange = (newCode) => {
    if (!isLanguageAvailable || !draft.ready) return;
    draft.change(newCode);
  };

  const handleImportCode = async (source, isCurrent) => {
    if (!isLanguageAvailable || !draft.ready || clearingDatabase.current) return false;
    const imported = await draft.importCode(source.language, source.code, isCurrent);
    if (imported) setLanguage(source.language);
    return imported;
  };

  // Run code against active testcase
  const handleRunCode = async () => {
    if (!problem || loadingProblem || clearingDatabase.current || !draft.ready || !isLanguageAvailable || isRunning || isSubmitting) return;
    const controller = new AbortController();
    execution.current = controller;
    const request = problemRequest.current;
    setIsRunning(true);
    setRunResult(null);
    setSubmissionResult(null);
    setExecutionStatus(language === 'cpp' || language === 'java' ? 'Compiling and running code...' : 'Running code...');
    setConsoleTab('result');

    const activeCase = testCases[0] || { input: '' };
    try {
      const res = await runCode({
        language,
        code: draft.code,
        input: activeCase.input,
        expectedOutput: activeCase.output,
        timeoutMs: 5000
      }, { signal: controller.signal });

      if (controller.signal.aborted || request !== problemRequest.current) return;
      if (res.success) {
        setRunResult(res.result);
      }
    } catch (err) {
      if (controller.signal.aborted || request !== problemRequest.current) return;
      setRunResult({
        status: 'Runtime Error',
        error: err.message,
        stdout: '',
        runtimeMs: 0
      });
    } finally {
      if (!controller.signal.aborted && request === problemRequest.current) {
        setIsRunning(false);
        setExecutionStatus(null);
      }
    }
  };

  // Submit code against all problem test cases
  const handleSubmitCode = async () => {
    if (!problem || loadingProblem || clearingDatabase.current || !draft.ready || !isLanguageAvailable || isRunning || isSubmitting) return;
    const controller = new AbortController();
    execution.current = controller;
    const request = problemRequest.current;
    setIsSubmitting(true);
    setRunResult(null);
    setSubmissionResult(null);
    setExecutionStatus('Queued for judging...');
    setConsoleTab('result');

    try {
      const res = await submitCode({
        problemId: problem.id,
        language,
        code: draft.code,
        customTestCases: testCases
      }, {
        signal: controller.signal,
        onProgress: job => {
          if (controller.signal.aborted || request !== problemRequest.current) return;
          const labels = { queued: 'Queued for judging...', compiling: 'Compiling code...', running: 'Running test cases...' };
          setExecutionStatus(labels[job.phase] || job.status || 'Judging submission...');
        }
      });

      if (controller.signal.aborted || request !== problemRequest.current) return;
      if (res.success) {
        setSubmissionResult(res);
        setExecutionStatus(null);

        if (res.grading?.status === 'Accepted') {
          setProblem(current => current?.id === problem.id ? { ...current, is_solved: true } : current);
          setArchiveVersion(version => version + 1);
        }

        // Refresh submission history
        const subRes = await fetchSubmissions(problem.id).catch(err => {
          if (!controller.signal.aborted && request === problemRequest.current) {
            setDatabaseNotice({ type: 'error', message: `Submission finished, but history could not refresh: ${err.message}` });
          }
          return null;
        });
        if (controller.signal.aborted || request !== problemRequest.current) return;
        if (subRes?.success) {
          setSubmissions(subRes.submissions);
        }

        // Celebrate if Accepted!
        if (res.grading && res.grading.status === 'Accepted') {
          confetti({
            particleCount: 80,
            spread: 60,
            origin: { y: 0.6 }
          });
        }
      }
    } catch (err) {
      if (controller.signal.aborted || request !== problemRequest.current) return;
      setSubmissionResult({
        grading: {
          status: 'Submission Error',
          totalTests: 0,
          passedTests: 0,
          totalRuntimeMs: 0,
          error: err.message
        }
      });
    } finally {
      if (!controller.signal.aborted && request === problemRequest.current) {
        setIsSubmitting(false);
        setExecutionStatus(null);
      }
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', overflow: 'hidden' }}>
      {/* Top Navbar */}
      <Navbar
        currentView={view}
        onViewChange={nextView => {
          setView(nextView);
          if (nextView === 'settings') setIsChatOpen(false);
        }}
        currentProblem={problem}
        onRandomProblem={handleRandomProblem}
        onOpenUpload={() => setIsUploadOpen(true)}
        onOpenGenerate={() => setIsGenerateOpen(true)}
        onClearDatabase={handleClearDatabase}
        isClearingDatabase={isClearingDatabase}
        isDatabaseBusy={isRunning || isSubmitting || isUploadOpen || isTranslateOpen || isGenerateOpen}
        onToggleChat={() => setIsChatOpen(!isChatOpen)}
        isChatOpen={isChatOpen}
      />

      <div style={{ padding: '0.35rem 1.25rem', backgroundColor: '#202020', borderBottom: '1px solid #333' }}><LLMModel /></div>

      {databaseNotice && (
        <div
          role={databaseNotice.type === 'error' ? 'alert' : 'status'}
          style={{ padding: '0.65rem 1.25rem', backgroundColor: '#222', borderBottom: '1px solid #3a3a3a', color: databaseNotice.type === 'error' ? '#ff8d89' : '#2cbb5d', fontSize: '0.85rem', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '1rem' }}
        >
          <span>{databaseNotice.message}</span>
          <button className="btn btn-ghost" onClick={() => setDatabaseNotice(null)} style={{ fontSize: '0.75rem', padding: '0.2rem 0.5rem' }}>Dismiss</button>
        </div>
      )}

      {/* Main Content Area */}
      <main inert={isClearingDatabase} aria-busy={isClearingDatabase} style={{ flex: 1, minHeight: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
        {view === 'list' ? (
          <div style={{ flex: 1, overflowY: 'auto' }}>
            <ProblemList key={`${databaseVersion}-${archiveVersion}`} onSelectProblem={handleSelectProblem} />
          </div>
        ) : view === 'submissions' ? (
          <SubmissionArchive key={databaseVersion} onSelectProblem={handleSelectProblem} />
        ) : view === 'settings' ? (
          <SettingsView />
        ) : (
          <SolveWorkspace
            problem={loadingProblem ? (
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#888' }}>
                  Loading problem statement...
                </div>
              ) : (
                <ProblemDetail
                  problem={problem}
                  translatedData={translatedData}
                  onOpenTranslate={() => setIsTranslateOpen(true)}
                  onOpenGenerateSimilar={() => setIsGenerateOpen(true)}
                  onSelectProblem={handleSelectProblem}
                  onResetTranslation={() => setTranslatedData(null)}
                />
              )}
            editor={
              <CodeEditor
                language={language}
                availableLanguages={availableLanguages}
                isLoadingLanguages={isLoadingLanguages}
                languagesError={languagesError}
                onRetryLanguages={() => setLanguageDetectionVersion(version => version + 1)}
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
                problemId={problem ? problem.id : null}
                problem={problem}
                submissions={submissions}
                executionStatus={executionStatus}
              />
            }
          />
        )}
      </main>

      {/* AI Chat Drawer */}
      <ChatDrawer
        isOpen={isChatOpen}
        onClose={() => setIsChatOpen(false)}
        currentProblem={problem}
        currentCode={draft.code}
        currentLanguage={language}
      />

      {/* Modals */}
      <TranslateModal
        key={`translate-${databaseVersion}-${problem?.id}`}
        isOpen={isTranslateOpen}
        onClose={() => setIsTranslateOpen(false)}
        problem={problem}
        onApplyTranslation={(data) => setTranslatedData(data)}
      />

      <GenerateProblemModal
        key={`generate-${databaseVersion}-${problem?.id}`}
        isOpen={isGenerateOpen}
        onClose={() => setIsGenerateOpen(false)}
        problem={problem}
        onProblemCreated={(newProb) => {
          setIsGenerateOpen(false);
          setDatabaseVersion(version => version + 1);
          handleSelectProblem(newProb.id);
        }}
      />

      <UploadModal
        key={`upload-${databaseVersion}`}
        isOpen={isUploadOpen}
        onClose={() => setIsUploadOpen(false)}
        onUploadComplete={() => {
          setIsUploadOpen(false);
          setDatabaseVersion(version => version + 1);
          setDatabaseNotice(null);
        }}
      />
    </div>
  );
}
