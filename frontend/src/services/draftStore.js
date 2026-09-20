import { fetchDraft, saveDraft } from './api.js';
import { CODE_TEMPLATES } from '../utils/codeTemplates.js';

// One queue per problem/language keeps slow responses from overwriting newer edits.
export class DraftStore {
  constructor({ load = fetchDraft, save = saveDraft, delay = 600 } = {}) {
    this.load = load;
    this.save = save;
    this.delay = delay;
    this.entries = new Map();
    this.listeners = new Set();
  }

  notify() { this.listeners.forEach(listener => listener()); }
  subscribe(listener) { this.listeners.add(listener); return () => this.listeners.delete(listener); }
  key(problemId, language) { return `${problemId}:${language}`; }
  get(problemId, language) { return this.entries.get(this.key(problemId, language)); }
  isCurrent(entry) { return this.get(entry.problemId, entry.language) === entry; }

  async ensure(problemId, language) {
    if (!problemId || !language) return;
    let entry = this.get(problemId, language);
    if (entry) return entry.loading;
    entry = { problemId, language, code: '', revision: 0, loaded: false, dirty: false, status: 'loading', error: null };
    this.entries.set(this.key(problemId, language), entry);
    return this.loadEntry(entry);
  }

  async loadEntry(entry) {
    entry.status = 'loading';
    entry.error = null;
    this.notify();
    entry.loading = this.load(entry.problemId, entry.language).then(({ draft }) => {
      if (!this.isCurrent(entry)) return;
      entry.code = draft.code ?? CODE_TEMPLATES[entry.language] ?? '';
      entry.revision = draft.revision;
      entry.loaded = true;
      entry.dirty = false;
      entry.status = draft.saved ? 'saved' : 'default';
    }).catch(error => {
      if (!this.isCurrent(entry)) return;
      entry.status = 'error';
      entry.error = error.message;
    }).finally(() => {
      entry.loading = null;
      this.notify();
    });
    return entry.loading;
  }

  change(problemId, language, code) {
    const entry = this.get(problemId, language);
    if (!entry?.loaded || entry.status === 'loading' || code === entry.code) return;
    entry.code = code;
    entry.dirty = true;
    clearTimeout(entry.timer);
    // Preserve an error until the user explicitly retries or resolves a conflict.
    if (!['error', 'conflict'].includes(entry.status)) {
      entry.status = 'unsaved';
      entry.timer = setTimeout(() => this.flush(entry), this.delay);
    }
    this.notify();
  }

  async importCode(problemId, language, code, isCurrent = () => true) {
    await this.ensure(problemId, language);
    if (!isCurrent()) return false;
    const entry = this.get(problemId, language);
    if (!entry?.loaded || entry.status === 'loading') {
      throw new Error(entry?.error || 'The saved draft could not be loaded. Retry the draft before importing.');
    }
    if (entry.status === 'conflict') {
      throw new Error('Resolve this language\'s draft conflict before importing a file.');
    }
    this.change(problemId, language, code);
    return true;
  }

  async flush(entry) {
    if (!entry) return;
    clearTimeout(entry.timer);
    if (entry.saving) return entry.saving;
    if (!entry.dirty || !entry.loaded || ['error', 'conflict'].includes(entry.status)) return;
    entry.saving = (async () => {
      while (entry.dirty && this.isCurrent(entry)) {
        const code = entry.code;
        entry.status = 'saving';
        this.notify();
        try {
          const { draft } = await this.save(entry.problemId, entry.language, code, entry.revision);
          if (!this.isCurrent(entry)) return;
          entry.revision = draft.revision;
          entry.dirty = entry.code !== code;
          entry.status = entry.dirty ? 'unsaved' : 'saved';
          entry.error = null;
        } catch (error) {
          entry.status = error.status === 409 ? 'conflict' : 'error';
          entry.error = error.message;
          break;
        }
      }
    })().finally(() => { entry.saving = null; this.notify(); });
    return entry.saving;
  }

  flushAll() { return Promise.all([...this.entries.values()].map(entry => this.flush(entry))); }
  hasPending() { return [...this.entries.values()].some(entry => entry.dirty || entry.saving); }

  async retry(problemId, language) {
    const entry = this.get(problemId, language);
    if (!entry) return this.ensure(problemId, language);
    if (!entry.loaded) return this.loadEntry(entry);
    if (entry.status === 'conflict') return;
    entry.status = 'unsaved';
    entry.error = null;
    return this.flush(entry);
  }

  async resolveConflict(problemId, language, keepMine) {
    const entry = this.get(problemId, language);
    if (!entry || entry.status !== 'conflict') return;
    if (!keepMine) return this.loadEntry(entry);
    // Explicit user choice: reread only the revision, preserving all local edits.
    try {
      const { draft } = await this.load(problemId, language);
      if (!this.isCurrent(entry)) return;
      entry.revision = draft.revision;
      entry.status = 'unsaved';
      entry.error = null;
      return this.flush(entry);
    } catch (error) {
      entry.error = error.message;
      this.notify();
    }
  }

  clear() {
    this.entries.forEach(entry => clearTimeout(entry.timer));
    this.entries.clear();
    this.notify();
  }
}
