import { useEffect, useReducer, useRef } from 'react';
import { DraftStore } from '../services/draftStore';

export default function useEditorDraft(problemId, language, active) {
  const storeRef = useRef(null);
  if (!storeRef.current) storeRef.current = new DraftStore();
  const store = storeRef.current;
  const [, render] = useReducer(value => value + 1, 0);
  useEffect(() => store.subscribe(render), [store]);
  useEffect(() => {
    if (active) store.ensure(problemId, language);
    return () => { store.flush(store.get(problemId, language)); };
  }, [store, problemId, language, active]);
  useEffect(() => {
    const flush = () => { store.flushAll(); };
    const beforeUnload = event => {
      if (!store.hasPending()) return;
      flush();
      // Browsers cannot guarantee delivery of large/in-flight saves when closing.
      event.preventDefault();
      event.returnValue = '';
    };
    const visibility = () => { if (document.visibilityState === 'hidden') flush(); };
    window.addEventListener('pagehide', flush);
    window.addEventListener('beforeunload', beforeUnload);
    document.addEventListener('visibilitychange', visibility);
    return () => {
      window.removeEventListener('pagehide', flush);
      window.removeEventListener('beforeunload', beforeUnload);
      document.removeEventListener('visibilitychange', visibility);
      flush();
    };
  }, [store]);
  const entry = store.get(problemId, language);
  return {
    key: `${problemId}:${language}`,
    code: entry?.code ?? '',
    ready: Boolean(active && entry?.loaded && entry.status !== 'loading'),
    status: entry?.status ?? 'loading',
    error: entry?.error,
    change: code => store.change(problemId, language, code),
    importCode: (targetLanguage, code, isCurrent) => store.importCode(problemId, targetLanguage, code, isCurrent),
    retry: () => store.retry(problemId, language),
    resolve: keepMine => store.resolveConflict(problemId, language, keepMine),
    clear: () => store.clear(),
    flush: () => store.flushAll(),
  };
}
