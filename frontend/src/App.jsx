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
import { CODE_TEMPLATES, DEFAULT_LANGUAGE } from './utils/codeTemplates';
import { clearDatabase, fetchProblem, runCode, submitCode, fetchSubmissions, fetchProblems, fetchLanguages } from './services/api';

export default function App() {
  const [view, setView] = useState('list'); // 'list' or 'solve'
  const [problemId, setProblemId] = useState(null);
  const [problem, setProblem] = useState(null);
  const [loadingProblem, setLoadingProblem] = useState(false);
  const [databaseVersion, setDatabaseVersion] = useState(0);
  const [isClearingDatabase, setIsClearingDatabase] = useState(false);
  const [databaseNotice, setDatabaseNotice] = useState(null);
  const problemRequest = useRef(0);
  const databaseGeneration = useRef(0);
  const clearingDatabase = useRef(false);

  // Editor State
  const [language, setLanguage] = useState(DEFAULT_LANGUAGE);
  const [availableLanguages, setAvailableLanguages] = useState([]);
  const [isLoadingLanguages, setIsLoadingLanguages] = useState(true);
  const [languagesError, setLanguagesError] = useState(null);
  const [languageDetectionVersion, setLanguageDetectionVersion] = useState(0);
  const [codes, setCodes] = useState({
    python: CODE_TEMPLATES.python,
    cpp: CODE_TEMPLATES.cpp,
    java: CODE_TEMPLATES.java
  });

  // Test Console State
  const [testCases, setTestCases] = useState([]);
  const [consoleTab, setConsoleTab] = useState('testcase'); // 'testcase', 'result', 'submissions'
  const [runResult, setRunResult] = useState(null);
  const [submissionResult, setSubmissionResult] = useState(null);
  const [submissions, setSubmissions] = useState([]);
  const [isRunning, setIsRunning] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

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
    setLoadingProblem(true);
    setRunResult(null);
    setSubmissionResult(null);
    setTranslatedData(null);
    try {
      const res = await fetchProblem(id);
      if (request !== problemRequest.current) return;
      if (res.success && res.problem) {
        setProblem(res.problem);
        setTestCases(res.problem.sample_input_output || [{ input: '', output: '' }]);
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
    if (!window.confirm('Permanently delete ALL problems and submission history from the database? Your current workspace will also be reset. This cannot be undone.')) return;

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
      setCodes({ ...CODE_TEMPLATES });
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
    if (!isLanguageAvailable) return;
    setCodes(prev => ({
      ...prev,
      [language]: newCode
    }));
  };

  // Run code against active testcase
  const handleRunCode = async () => {
    if (clearingDatabase.current || !isLanguageAvailable || isRunning || isSubmitting) return;
    setIsRunning(true);
    setSubmissionResult(null);
    setConsoleTab('result');

    const activeCase = testCases[0] || { input: '', output: '' };
    try {
      const res = await runCode({
        language,
        code: codes[language],
        input: activeCase.input,
        expectedOutput: activeCase.output,
        timeoutMs: 5000
      });

      if (res.success) {
        setRunResult(res.result);
      }
    } catch (err) {
      setRunResult({
        status: 'Runtime Error',
        error: err.message,
        stdout: '',
        runtimeMs: 0
      });
    } finally {
      setIsRunning(false);
    }
  };

  // Submit code against all problem test cases
  const handleSubmitCode = async () => {
    if (!problem || clearingDatabase.current || !isLanguageAvailable || isRunning || isSubmitting) return;
    setIsSubmitting(true);
    setRunResult(null);
    setConsoleTab('result');

    try {
      const res = await submitCode({
        problemId: problem.id,
        language,
        code: codes[language],
        customTestCases: testCases
      });

      if (res.success) {
        setSubmissionResult(res);

        // Refresh submission history
        const subRes = await fetchSubmissions(problem.id);
        if (subRes.success) {
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
      setSubmissionResult({
        grading: {
          status: 'Runtime Error',
          totalTests: 1,
          passedTests: 0,
          totalRuntimeMs: 0,
          error: err.message
        }
      });
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', overflow: 'hidden' }}>
      {/* Top Navbar */}
      <Navbar
        currentView={view}
        onViewChange={setView}
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
      <main inert={isClearingDatabase} aria-busy={isClearingDatabase} style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
        {view === 'list' ? (
          <div style={{ flex: 1, overflowY: 'auto' }}>
            <ProblemList key={databaseVersion} onSelectProblem={handleSelectProblem} />
          </div>
        ) : (
          /* Split Solve View: Left Problem Detail, Right Editor + Console */
          <div style={{ display: 'grid', gridTemplateColumns: '48% 52%', height: '100%', overflow: 'hidden' }}>
            {/* Left Pane: Problem Details & AI Assist */}
            <div style={{ height: '100%', overflow: 'hidden', borderRight: '1px solid #333' }}>
              {loadingProblem ? (
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
            </div>

            {/* Right Pane: CodeMirror Editor (Top) & Test Console (Bottom) */}
            <div style={{ display: 'grid', gridTemplateRows: '58% 42%', height: '100%', overflow: 'hidden' }}>
              {/* CodeMirror Code Editor */}
              <CodeEditor
                language={language}
                availableLanguages={availableLanguages}
                isLoadingLanguages={isLoadingLanguages}
                languagesError={languagesError}
                onRetryLanguages={() => setLanguageDetectionVersion(version => version + 1)}
                onLanguageChange={handleLanguageChange}
                code={codes[language] || ''}
                onCodeChange={handleCodeChange}
                onRun={handleRunCode}
                onSubmit={handleSubmitCode}
                isRunning={isRunning}
                isSubmitting={isSubmitting}
              />

              {/* Bottom Test & Results Console */}
              <TestConsole
                testCases={testCases}
                onTestCasesChange={setTestCases}
                activeTab={consoleTab}
                onTabChange={setConsoleTab}
                runResult={runResult}
                submissionResult={submissionResult}
                problemId={problem ? problem.id : null}
                problem={problem}
                submissions={submissions}
              />
            </div>
          </div>
        )}
      </main>

      {/* AI Chat Drawer */}
      <ChatDrawer
        isOpen={isChatOpen}
        onClose={() => setIsChatOpen(false)}
        problem={problem}
        code={codes[language] || ''}
        language={language}
      />

      {/* Modals */}
      <TranslateModal
        key={`translate-${databaseVersion}`}
        isOpen={isTranslateOpen}
        onClose={() => setIsTranslateOpen(false)}
        problem={problem}
        onApplyTranslation={(data) => setTranslatedData(data)}
      />

      <GenerateProblemModal
        key={`generate-${databaseVersion}`}
        isOpen={isGenerateOpen}
        onClose={() => setIsGenerateOpen(false)}
        problem={problem}
        onProblemCreated={(newProb) => {
          setIsGenerateOpen(false);
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

