import React, { useMemo } from 'react';
import CodeMirror from '@uiw/react-codemirror';
import { python } from '@codemirror/lang-python';
import { cpp } from '@codemirror/lang-cpp';
import { java } from '@codemirror/lang-java';
import { oneDark } from '@codemirror/theme-one-dark';
import { Play, Send, RotateCcw, Code } from 'lucide-react';
import { CODE_TEMPLATES } from '../utils/codeTemplates';

export default function CodeEditor({
  language,
  availableLanguages,
  isLoadingLanguages,
  languagesError,
  onRetryLanguages,
  onLanguageChange,
  code,
  onCodeChange,
  onRun,
  onSubmit,
  isRunning,
  isSubmitting
}) {
  const selectedLanguage = availableLanguages.find(item => item.id === language);
  const isLanguageAvailable = !isLoadingLanguages && !languagesError && Boolean(selectedLanguage);
  const actionsDisabled = !isLanguageAvailable || isRunning || isSubmitting;
  const editorLanguage = selectedLanguage?.editorLanguage;
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
      onCodeChange(CODE_TEMPLATES[language] || '');
    }
  };

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      height: '100%',
      backgroundColor: '#1e1e1e',
      borderLeft: '1px solid #333'
    }}>
      {/* Editor Toolbar */}
      <div style={{
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
            onChange={(e) => onLanguageChange(e.target.value)}
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

          {/* Reset Template */}
          <button
            onClick={handleReset}
            disabled={!isLanguageAvailable}
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
      <div style={{ flex: 1, minHeight: 0, overflow: 'auto', position: 'relative' }}>
        <CodeMirror
          value={code}
          editable={isLanguageAvailable}
          height="100%"
          extensions={[languageExtension]}
          theme={oneDark}
          onChange={(value) => onCodeChange(value)}
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

