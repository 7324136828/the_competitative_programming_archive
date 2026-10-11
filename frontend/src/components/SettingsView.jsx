import React, { useEffect, useRef, useState } from 'react';
import { FolderOpen, HardDrive, Loader2, RefreshCw, Save, Trash2, Volume2 } from 'lucide-react';
import { AUDIO_CACHE_CLEARED_EVENT, clearAudioCache, getAudioCache } from '../services/audio';
import { fetchSettings, updateSettings } from '../services/api';
import './SettingsView.css';

function formatBytes(bytes) {
  if (!bytes) return '0 bytes';
  if (bytes < 1024) return `${bytes} bytes`;
  const units = ['KB', 'MB', 'GB'];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)) - 1, units.length - 1);
  return `${(bytes / 1024 ** (index + 1)).toLocaleString(undefined, { maximumFractionDigits: 1 })} ${units[index]}`;
}

const storageLocationNames = {
  DATABASE_PATH: 'Main database',
  JIRA_DB_PATH: 'Jira database',
  WORKSPACE_STORAGE_DIR: 'Workspaces',
  UPLOAD_DIR: 'Uploads',
};

export default function SettingsView({ embedded = false }) {
  const [cache, setCache] = useState(null);
  const [loading, setLoading] = useState(true);
  const [clearing, setClearing] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [revision, setRevision] = useState(0);
  const [storage, setStorage] = useState(null);
  const [dataDir, setDataDir] = useState('');
  const [storageLoading, setStorageLoading] = useState(true);
  const [storageSaving, setStorageSaving] = useState(false);
  const [storageError, setStorageError] = useState('');
  const [storageNotice, setStorageNotice] = useState('');
  const [storageRevision, setStorageRevision] = useState(0);
  const mounted = useRef(true);
  const usageRequest = useRef(null);
  const usageGeneration = useRef(0);

  useEffect(() => {
    const controller = new AbortController();
    setStorageLoading(true);
    setStorageError('');
    fetchSettings({ signal: controller.signal })
      .then(result => {
        if (controller.signal.aborted) return;
        setStorage(result);
        setDataDir(result.data_dir);
      })
      .catch(failure => { if (!controller.signal.aborted) setStorageError(failure.message); })
      .finally(() => { if (!controller.signal.aborted) setStorageLoading(false); });
    return () => controller.abort();
  }, [storageRevision]);

  useEffect(() => {
    const controller = new AbortController();
    const currentGeneration = ++usageGeneration.current;
    usageRequest.current = controller;
    const current = () => !controller.signal.aborted && currentGeneration === usageGeneration.current;
    setLoading(true);
    setError('');
    getAudioCache(controller.signal)
      .then(result => { if (current()) setCache(result); })
      .catch(failure => { if (current()) setError(failure.message); })
      .finally(() => { if (current()) setLoading(false); });
    return () => controller.abort();
  }, [revision]);

  useEffect(() => {
    mounted.current = true;
    function cacheCleared(event) {
      // A deletion started in a previous Settings instance may finish after
      // navigation. Its result supersedes every earlier usage request here.
      usageGeneration.current += 1;
      usageRequest.current?.abort();
      const result = event.detail;
      if (result && Number.isFinite(result.files) && Number.isFinite(result.bytes)) {
        setCache(result);
        setLoading(false);
        setError('');
      } else {
        setRevision(value => value + 1);
      }
    }
    window.addEventListener(AUDIO_CACHE_CLEARED_EVENT, cacheCleared);
    return () => {
      mounted.current = false;
      window.removeEventListener(AUDIO_CACHE_CLEARED_EVENT, cacheCleared);
    };
  }, []);

  async function clear() {
    setClearing(true);
    setError('');
    setNotice('');
    try {
      // Let the deletion finish if the user changes views so all active players
      // still receive its cache-cleared event after the server removes files.
      const result = await clearAudioCache();
      if (!mounted.current) return;
      setCache(result);
      setNotice(`Cleared ${result.removedFiles} saved audio ${result.removedFiles === 1 ? 'file' : 'files'} (${formatBytes(result.removedBytes)}). Read aloud can generate them again.`);
    } catch (failure) {
      if (mounted.current) setError(failure.message);
    } finally {
      if (mounted.current) setClearing(false);
    }
  }

  async function saveStorage(nextDataDir) {
    if (!storage || storage.editable === false || storageSaving) return;
    setStorageSaving(true);
    setStorageError('');
    setStorageNotice('');
    try {
      const result = await updateSettings(nextDataDir);
      if (!mounted.current) return;
      setStorage(result);
      setDataDir(result.data_dir);
      setStorageNotice(result.restart_required
        ? 'Storage setting saved. Restart The Study Platform to use the selected folder.'
        : 'Storage setting saved. The selected folder is already active.');
    } catch (failure) {
      if (mounted.current) setStorageError(failure.message);
    } finally {
      if (mounted.current) setStorageSaving(false);
    }
  }

  const storageEditable = storage?.editable !== false;
  const storageChanged = storage && dataDir.trim() !== storage.data_dir;

  return (
    <div className={`settings-view${embedded ? ' settings-view-embedded' : ''}`}>
      <div className="settings-content">
        {!embedded && <>
          <h1>Settings</h1>
          <p className="settings-intro">Manage files saved on the computer running The Study Platform.</p>
        </>}
        <section className="settings-card" aria-labelledby="data-storage-title">
          <h2 id="data-storage-title"><FolderOpen size={20} /> Data storage</h2>
          <p>Choose the folder The Study Platform uses to store its data. When connected over LAN, these paths refer to the host computer.</p>
          {storageLoading ? <p role="status">Loading storage settings...</p> : storage && (
            <form onSubmit={event => { event.preventDefault(); saveStorage(dataDir); }}>
              <label className="settings-field-label" htmlFor="data-storage-folder">Data storage folder</label>
              <input
                id="data-storage-folder"
                className="settings-folder-input"
                type="text"
                value={dataDir}
                onChange={event => { setDataDir(event.target.value); setStorageNotice(''); }}
                placeholder={storage.default_data_dir}
                disabled={!storageEditable || storageSaving}
                spellCheck={false}
                autoComplete="off"
                aria-describedby="data-storage-help"
              />
              <p id="data-storage-help" className="settings-cleanup-note">Enter an absolute folder path on the host, or leave this field blank to use the default folder. Changing folders does not move existing data. To keep your data, stop the app and copy it to the selected folder before starting again.</p>
              <dl className="settings-storage-paths">
                <div><dt>Active storage folder</dt><dd><code>{storage.active_data_dir}</code></dd></div>
                <div><dt>Default storage folder</dt><dd><code>{storage.default_data_dir}</code></dd></div>
                <div><dt>Settings file</dt><dd><code>{storage.settings_path}</code></dd></div>
              </dl>
              {Object.keys(storage.overrides || {}).length > 0 && <>
                <p className="settings-cleanup-note">These storage locations are configured separately and will keep their current paths:</p>
                <dl className="settings-storage-paths">
                  {Object.entries(storage.overrides).map(([key, path]) => <div key={key}><dt>{storageLocationNames[key] || key}</dt><dd><code>{path}</code></dd></div>)}
                </dl>
              </>}
              {storage.restart_required && <p className="settings-restart-note" role="status">Restart required. The app will continue using the active storage folder until the host restarts it.</p>}
              {!storageEditable && <p className="settings-cleanup-note">Storage settings can only be changed from a browser on the host computer.</p>}
              <div className="settings-actions">
                <button type="submit" className="btn btn-secondary" disabled={!storageEditable || storageSaving || !storageChanged}>
                  {storageSaving ? <Loader2 size={16} className="settings-spinner" /> : <Save size={16} />}
                  {storageSaving ? 'Saving storage setting...' : 'Save storage folder'}
                </button>
                <button type="button" className="btn btn-ghost" onClick={() => saveStorage('')} disabled={!storageEditable || storageSaving || (!storageChanged && storage.data_dir === storage.default_data_dir)}>
                  <RefreshCw size={15} /> Use default folder
                </button>
              </div>
            </form>
          )}
          {storageNotice && <p className="settings-success" role="status">{storageNotice}</p>}
          {storageError && <p className="settings-error" role="alert">{storageError}</p>}
          {!storageLoading && !storage && <button type="button" className="btn btn-secondary" onClick={() => setStorageRevision(value => value + 1)}><RefreshCw size={15} /> Retry storage settings</button>}
        </section>
        <section className="settings-card" aria-labelledby="saved-audio-title">
          <h2 id="saved-audio-title"><Volume2 size={20} /> Saved audio</h2>
          <p>Problem descriptions and AI responses are read aloud with Kokoro. Their MP3 files are saved to disk and reused when you listen again.</p>
          <div className="settings-audio-stats" aria-live="polite">
            <HardDrive size={17} aria-hidden="true" />
            {loading ? 'Checking saved audio...' : cache ? `${cache.files} saved audio ${cache.files === 1 ? 'file' : 'files'} · ${formatBytes(cache.bytes)}` : 'Audio storage information is unavailable.'}
          </div>
          <p className="settings-cleanup-note">Clearing stops current narration and removes saved audio for every problem and AI response. Read aloud will generate a new file the next time you use it. Your code, submissions, and problems stay saved.</p>
          <div className="settings-actions">
            <button type="button" className="btn btn-secondary" onClick={clear} disabled={loading || clearing}>
              {clearing ? <Loader2 size={16} className="settings-spinner" /> : <Trash2 size={16} />}
              {clearing ? 'Clearing saved audio...' : 'Clear saved audio'}
            </button>
            <button type="button" className="btn btn-ghost" onClick={() => setRevision(value => value + 1)} disabled={loading || clearing}>
              <RefreshCw size={15} /> Refresh usage
            </button>
          </div>
          {notice && <p className="settings-success" role="status">{notice}</p>}
          {error && <p className="settings-error" role="alert">{error}</p>}
        </section>
      </div>
    </div>
  );
}
