const KEY = 'jira_model_override';
const EVENT = 'jira-model-changed';

/** Per-browser AI model override; null means "use the server default". */
export function getModelOverride(): string | null {
  return localStorage.getItem(KEY);
}

export function setModelOverride(model: string | null) {
  if (model) localStorage.setItem(KEY, model);
  else localStorage.removeItem(KEY);
  window.dispatchEvent(new Event(EVENT));
}

export function onModelChange(cb: () => void): () => void {
  const handler = () => cb();
  window.addEventListener(EVENT, handler);
  return () => window.removeEventListener(EVENT, handler);
}
