import React, { useEffect, useMemo, useRef, useState } from 'react';
import CodeMirror from '@uiw/react-codemirror';
import { python } from '@codemirror/lang-python';
import { cpp } from '@codemirror/lang-cpp';
import { java } from '@codemirror/lang-java';
import { oneDark } from '@codemirror/theme-one-dark';
import { Play, Send, RotateCcw, Code, Upload } from 'lucide-react';
import { CODE_TEMPLATES } from '../utils/codeTemplates';
import { readSourceFile, SOURCE_FILE_ACCEPT } from '../utils/sourceFiles';
import './CodeEditor.css';

export default function CodeEditor({
  language,
  availableLanguages,
  isLoadingLanguages,
  languagesError,
  onRetryLanguages,
  onLanguageChange,
  code,
  onCodeChange,
  onImportCode,
  draft,
  onRun,
  onSubmit,
  isRunning,
  isSubmitting,
  executionDisabled = false
}) {
  const selectedLanguage = availableLanguages.find(item => item.id === language);
  const isLanguageAvailable = !isLoadingLanguages && !languagesError && Boolean(selectedLanguage);
  const actionsDisabled = executionDisabled || !isLanguageAvailable || isRunning || isSubmitting;
  const editorLanguage = selectedLanguage?.editorLanguage;
  const [importStatus, setImportStatus] = useState(null);
  const [isImporting, setIsImporting] = useState(false);
  const [isDraggingFile, setIsDraggingFile] = useState(false);
  const inputRef = useRef(null);
  const dragDepth = useRef(0);
  const operation = useRef(0);
  const editVersion = useRef(0);
  const mounted = useRef(true);
  const context = useRef(null);
  const nextContext = { key: draft?.key ?? language, code, ready: isLanguageAvailable && (!draft || draft.ready) };
  if (context.current && (context.current.key !== nextContext.key || (context.current.ready && !nextContext.ready))) editVersion.current += 1;
  context.current = nextContext;
  const canImport = Boolean(onImportCode && context.current.ready && !executionDisabled && !isImporting);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; operation.current += 1; };
  }, []);

  const updateCode = value => {
    if (value !== code) editVersion.current += 1;
    onCodeChange(value);
  };

  const importFiles = async files => {
    if (!canImport) {
      setImportStatus({ error: true, message: 'Wait for the editor and saved draft to finish loading before uploading.' });
      return;
    }
    const token = ++operation.current;
    const original = context.current;
    const originalVersion = editVersion.current;
    const isCurrent = () => mounted.current && operation.current === token &&
      context.current.key === original.key && context.current.code === original.code &&
      context.current.ready && editVersion.current === originalVersion;
    setIsImporting(true);
    setImportStatus({ message: 'Reading source file...' });
    try {
      const source = await readSourceFile(files, language, availableLanguages);
      if (!isCurrent() || !await onImportCode(source, isCurrent)) {
        if (mounted.current && operation.current === token) setImportStatus({ error: true, message: 'Import canceled because the editor changed. Choose the file again to replace the current code.' });
        return;
      }
      if (mounted.current && operation.current === token) {
        setImportStatus({ message: `Loaded ${source.name} (${source.label}). Ready to run or submit.` });
      }
    } catch (error) {
      if (mounted.current && operation.current === token) setImportStatus({ error: true, message: error.message });
    } finally {
      if (mounted.current && operation.current === token) setIsImporting(false);
    }
  };

  const hasFiles = event => Array.from(event.dataTransfer.types || []).includes('Files');
  const handleDragEnter = event => {
    if (!hasFiles(event)) return;
    event.preventDefault();
    event.stopPropagation();
    dragDepth.current += 1;
    setIsDraggingFile(true);
  };
  const handleDragOver = event => {
    if (!hasFiles(event)) return;
    event.preventDefault();
    event.stopPropagation();
    event.dataTransfer.dropEffect = canImport ? 'copy' : 'none';
  };
  const handleDragLeave = event => {
    if (!dragDepth.current) return;
    event.stopPropagation();
    dragDepth.current = Math.max(0, dragDepth.current - 1);
    if (!dragDepth.current) setIsDraggingFile(false);
  };
  const handleDrop = event => {
    if (!hasFiles(event) && !event.dataTransfer.files.length) return;
    // Capture file drops before CodeMirror's own drop handler can insert them.
    event.preventDefault();
    event.stopPropagation();
    dragDepth.current = 0;
    setIsDraggingFile(false);
    void importFiles(Array.from(event.dataTransfer.files));
  };
  const languageExtension = useMemo(() => {
    switch (editorLanguage) {
      case 'cpp':
        return cpp();
      case 'java':
        return java();
      case 'python':
      default:
        return python();
    }
  }, [editorLanguage]);

  const handleReset = () => {
    if (window.confirm('Reset editor to default starter template? Current changes will be lost.')) {
      updateCode(CODE_TEMPLATES[language] || '');
    }
  };

  return (
    <div className="code-editor" onDragEnterCapture={handleDragEnter} onDragOverCapture={handleDragOver} onDragLeaveCapture={handleDragLeave} onDropCapture={handleDrop} style={{
      display: 'flex',
      flexDirection: 'column',
      height: '100%',
      backgroundColor: '#1e1e1e',
      borderLeft: '1px solid #333'
    }}>
      {/* Editor Toolbar */}
      <div className="editor-toolbar" style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0.5rem 1rem',
        backgroundColor: '#262626',
        borderBottom: '1px solid #333'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <Code size={16} color="#ffa116" />
          
          {/* Language Selector */}
          <select
            aria-label="Programming language"
            value={isLanguageAvailable ? language : ''}
            disabled={!isLanguageAvailable}
            onChange={(e) => { editVersion.current += 1; onLanguageChange(e.target.value); }}
            style={{
              backgroundColor: '#1f1f1f',
              color: '#eff2f6',
              border: '1px solid #444',
              borderRadius: '0.25rem',
              padding: '0.3rem 0.6rem',
              fontSize: '0.85rem',
              fontWeight: 500,
              outline: 'none',
              cursor: 'pointer'
            }}
          >
            {!isLanguageAvailable && (
              <option value="">{isLoadingLanguages ? 'Detecting languages...' : languagesError ? 'Language detection failed' : 'No languages available'}</option>
            )}
            {availableLanguages.map(item => <option key={item.id} value={item.id}>{item.label}</option>)}
          </select>

          <input ref={inputRef} type="file" accept={SOURCE_FILE_ACCEPT} aria-label="Choose source code file" hidden onChange={event => {
            const files = Array.from(event.target.files || []);
            event.target.value = '';
            if (files.length) void importFiles(files);
          }} />
          <button className="btn btn-ghost" disabled={!canImport} onClick={() => inputRef.current?.click()} title="Upload UTF-8 source code (.py, .cpp, .cc, .cxx, .java, .txt; up to 2 MiB)" style={{ padding: '0.3rem 0.5rem', fontSize: '0.8rem' }}>
            <Upload size={14} />
            <span>{isImporting ? 'Importing...' : 'Upload code'}</span>
          </button>

          {/* Reset Template */}
          <button
            onClick={handleReset}
            disabled={!isLanguageAvailable || (draft && !draft.ready)}
            className="btn btn-ghost"
            title="Reset to default template"
            style={{ padding: '0.3rem 0.5rem', fontSize: '0.8rem' }}
          >
            <RotateCcw size={14} />
            <span>Reset</span>
          </button>
        </div>

        {/* Action Buttons */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
          <button
            onClick={onRun}
            disabled={actionsDisabled}
            className="btn btn-secondary"
            style={{
              padding: '0.35rem 0.85rem',
              fontSize: '0.825rem',
              opacity: actionsDisabled ? 0.6 : 1
            }}
          >
            <Play size={14} fill={isRunning ? 'none' : '#eff2f6'} />
            <span>{isRunning ? 'Running...' : 'Run Code'}</span>
          </button>

          <button
            onClick={onSubmit}
            disabled={actionsDisabled}
            className="btn btn-success"
            style={{
              padding: '0.35rem 1rem',
              fontSize: '0.825rem',
              opacity: actionsDisabled ? 0.6 : 1
            }}
          >
            <Send size={14} />
            <span>{isSubmitting ? 'Submitting...' : 'Submit'}</span>
          </button>
        </div>
      </div>

      <div className={`source-import-status${importStatus?.error ? ' source-import-error' : ''}`} role={importStatus?.error ? 'alert' : 'status'} aria-live="polite">
        <span>{importStatus?.message || 'Drop a source file here, or choose Upload code.'}</span>
        {importStatus && !isImporting && <button className="btn btn-ghost" aria-label="Dismiss upload message" onClick={() => setImportStatus(null)}>Dismiss</button>}
      </div>
      {isDraggingFile && <div className="source-drop-overlay" aria-hidden="true"><Upload size={30} /><strong>{canImport ? 'Drop to load code' : 'Wait for the editor to be ready'}</strong><span>.py, .cpp, .cc, .cxx, .java, .txt · up to 2 MiB</span></div>}

      {!isLoadingLanguages && (languagesError || availableLanguages.length === 0) && (
        <div
          role={languagesError ? 'alert' : 'status'}
          style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.75rem', padding: '0.65rem 1rem', borderBottom: '1px solid #333', color: languagesError ? '#ff8d89' : '#bbb', fontSize: '0.8rem' }}
        >
          <span>{languagesError || 'No supported runtimes were found. Install Python 3, a C++ compiler, or a Java JDK, then check again.'}</span>
          <button className="btn btn-ghost" onClick={onRetryLanguages} style={{ flexShrink: 0, fontSize: '0.8rem' }}>
            {languagesError ? 'Retry' : 'Check again'}
          </button>
        </div>
      )}

      {/* CodeMirror Surface */}
      {draft && (
        <div role={draft.error ? 'alert' : 'status'} aria-live="polite" style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: '0.4rem', padding: '0.35rem 1rem', borderBottom: '1px solid #333', fontSize: '0.75rem', color: draft.error ? '#ff8d89' : '#aaa' }}>
          <span>{draft.error || ({ loading: 'Loading saved draft...', default: 'Starter template · edits save automatically', saved: 'Saved to disk', saving: 'Saving draft...', unsaved: 'Unsaved changes' }[draft.status])}</span>
          {draft.status === 'error' && <button className="btn btn-ghost" style={{ padding: '0.1rem 0.4rem', fontSize: '0.75rem' }} onClick={draft.retry}>Retry draft</button>}
          {draft.status === 'conflict' && <>
            <span>Another tab changed this draft.</span>
            <button className="btn btn-ghost" style={{ padding: '0.1rem 0.4rem', fontSize: '0.75rem' }} onClick={() => draft.resolve(true)}>Keep my version</button>
            <button className="btn btn-ghost" style={{ padding: '0.1rem 0.4rem', fontSize: '0.75rem' }} onClick={() => { if (window.confirm('Replace the edits in this tab with the saved draft?')) draft.resolve(false); }}>Load saved version</button>
          </>}
        </div>
      )}
      <div style={{ flex: 1, minHeight: 0, overflow: 'auto', position: 'relative' }}>
        <CodeMirror
          key={`${draft?.key ?? language}-${draft?.ready ? 'ready' : 'loading'}`}
          value={code}
          editable={isLanguageAvailable && (!draft || draft.ready)}
          height="100%"
          extensions={[languageExtension]}
          theme={oneDark}
          onChange={updateCode}
          basicSetup={{
            lineNumbers: true,
            highlightActiveLineGutter: true,
            highlightSpecialChars: true,
            history: true,
            foldGutter: true,
            drawSelection: true,
            dropCursor: true,
            allowMultipleSelections: true,
            indentOnInput: true,
            syntaxHighlighting: true,
            bracketMatching: true,
            closeBrackets: true,
            autocompletion: true,
            rectangularSelection: true,
            crosshairCursor: true,
            highlightActiveLine: true,
            highlightSelectionMatches: true,
            closeBracketsKeymap: true,
            defaultKeymap: true,
            searchKeymap: true,
            historyKeymap: true,
            foldKeymap: true,
            completionKeymap: true,
            lintKeymap: true
          }}
        />
      </div>
    </div>
  );
}
