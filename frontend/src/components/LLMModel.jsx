import React, { createContext, useContext, useEffect, useState } from 'react';
import { fetchModels } from '../services/api';

const LLMContext = createContext(null);
const MODEL_PREFERENCE_KEY = 'codejudge.ai-model';

function readPreferredModel() {
  try {
    return window.localStorage.getItem(MODEL_PREFERENCE_KEY);
  } catch {
    return null;
  }
}

export function LLMProvider({ children }) {
  const [state, setState] = useState(() => ({ loading: true, model: readPreferredModel(), models: [], error: null }));
  const [version, setVersion] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setState(current => ({ ...current, loading: true, error: null }));
    fetchModels({ signal: controller.signal })
      .then(data => {
        if (controller.signal.aborted) return;
        setState(current => ({
          ...data,
          model: data.models.some(item => item.id === current.model) ? current.model : data.model,
          loading: false,
          error: null,
        }));
      })
      .catch(error => {
        if (!controller.signal.aborted) setState(current => ({ ...current, loading: false, error: error.message }));
      });
    return () => controller.abort();
  }, [version]);

  const ready = Boolean(state.model) && !state.loading && !state.error;
  useEffect(() => {
    if (!ready) return;
    try {
      window.localStorage.setItem(MODEL_PREFERENCE_KEY, state.model);
    } catch {
      // Model selection still works when browser storage is unavailable.
    }
  }, [state.model, ready]);

  const selectModel = model => {
    setState(current => !current.loading && !current.error && current.models.some(item => item.id === model)
      ? { ...current, model }
      : current);
  };

  return <LLMContext.Provider value={{ ...state, ready, selectModel, retry: () => setVersion(current => current + 1) }}>{children}</LLMContext.Provider>;
}

export function useLLMModel() {
  return useContext(LLMContext);
}

export default function LLMModel({ usedModel }) {
  const { loading, error, model, models, ready, selectModel, retry } = useLLMModel();
  return (
    <div style={{ fontSize: '0.72rem', color: '#aaa', display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap', overflowWrap: 'anywhere', minWidth: 0 }}>
      <label style={{ display: 'flex', gap: '0.4rem', alignItems: 'center', minWidth: 0, maxWidth: '100%' }}>
        <span style={{ whiteSpace: 'nowrap' }}>AI model:</span>
        <select
          aria-label="AI model"
          value={models.some(item => item.id === model) ? model : ''}
          disabled={!ready}
          onChange={event => selectModel(event.target.value)}
          style={{ backgroundColor: '#292929', color: '#eff2f6', border: '1px solid #505050', borderRadius: '0.3rem', padding: '0.25rem 0.4rem', fontSize: 'inherit', minWidth: 0, maxWidth: '20rem', cursor: ready ? 'pointer' : 'default' }}
        >
          {models.length === 0 && <option value="">{loading ? 'Discovering models...' : 'Models unavailable'}</option>}
          {models.map(item => <option key={item.id} value={item.id}>{item.name && item.name !== item.id ? `${item.name} (${item.id})` : item.id}</option>)}
        </select>
      </label>
      {loading && <span role="status">{models.length ? 'Refreshing AI models...' : 'Discovering AI models...'}</span>}
      {error && <span role="alert" style={{ color: '#ff8d89' }}>{error}</span>}
      {usedModel && <span>Result model: {usedModel}</span>}
      {!loading && <button className="btn btn-ghost" onClick={retry} style={{ fontSize: '0.72rem', padding: '0.15rem 0.35rem' }}>{error ? 'Retry models' : 'Refresh models'}</button>}
    </div>
  );
}
