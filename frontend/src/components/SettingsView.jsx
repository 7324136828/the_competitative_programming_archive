import React, { useEffect, useRef, useState } from 'react';
import { HardDrive, Loader2, RefreshCw, Trash2, Volume2 } from 'lucide-react';
import { AUDIO_CACHE_CLEARED_EVENT, clearAudioCache, getAudioCache } from '../services/audio';
import './SettingsView.css';

function formatBytes(bytes) {
  if (!bytes) return '0 bytes';
  if (bytes < 1024) return `${bytes} bytes`;
  const units = ['KB', 'MB', 'GB'];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)) - 1, units.length - 1);
  return `${(bytes / 1024 ** (index + 1)).toLocaleString(undefined, { maximumFractionDigits: 1 })} ${units[index]}`;
}

export default function SettingsView() {
  const [cache, setCache] = useState(null);
  const [loading, setLoading] = useState(true);
  const [clearing, setClearing] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [revision, setRevision] = useState(0);
  const mounted = useRef(true);
  const usageRequest = useRef(null);
  const usageGeneration = useRef(0);

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

  return (
    <div className="settings-view">
      <div className="settings-content">
        <h1>Settings</h1>
        <p className="settings-intro">Manage files saved by CodeJudge on this computer.</p>
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
