import React, { useEffect, useRef, useState } from 'react';
import { Download, Loader2, Volume2, X } from 'lucide-react';
import { AUDIO_CACHE_CLEARED_EVENT } from '../services/audio';
import './ProblemAudio.css';

async function requestAudio(problemId, method, signal) {
  const response = await fetch(`/api/problems/${encodeURIComponent(problemId)}/audio`, { method, signal });
  const body = await response.json().catch(() => ({}));
  if (!response.ok || body.success === false || !body.audio) {
    throw new Error(body.error || 'Unable to load problem narration. Please try again.');
  }
  return body.audio;
}

export default function ProblemAudio({ problem }) {
  const [audio, setAudio] = useState(null);
  const [visible, setVisible] = useState(false);
  const [checking, setChecking] = useState(true);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState('');
  const [cacheVersion, setCacheVersion] = useState(0);
  const startRequest = useRef(null);
  const checkRequest = useRef(null);
  const pollRequest = useRef(null);
  const player = useRef(null);
  const generation = useRef(0);
  const problemId = problem?.id;

  useEffect(() => {
    function resetAudio() {
      generation.current += 1;
      startRequest.current?.abort();
      checkRequest.current?.abort();
      pollRequest.current?.abort();
      player.current?.pause();
      setAudio(null);
      setVisible(false);
      setStarting(false);
      setError('');
      setCacheVersion(value => value + 1);
    }
    window.addEventListener(AUDIO_CACHE_CLEARED_EVENT, resetAudio);
    return () => window.removeEventListener(AUDIO_CACHE_CLEARED_EVENT, resetAudio);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    generation.current += 1;
    const currentGeneration = generation.current;
    checkRequest.current = controller;
    setAudio(null);
    setVisible(false);
    setChecking(true);
    setStarting(false);
    setError('');
    if (problemId == null) {
      setChecking(false);
      return () => controller.abort();
    }
    requestAudio(problemId, 'GET', controller.signal)
      .then(result => {
        if (!controller.signal.aborted && currentGeneration === generation.current) {
          setAudio(result);
          if (!result.done) setVisible(true);
        }
      })
      .catch(failure => {
        if (!controller.signal.aborted && currentGeneration === generation.current) setError(failure.message);
      })
      .finally(() => {
        if (!controller.signal.aborted && currentGeneration === generation.current) setChecking(false);
      });
    return () => {
      controller.abort();
      startRequest.current?.abort();
    };
  }, [problemId, problem?.title, problem?.problem_statements, problem?.language, cacheVersion]);

  useEffect(() => {
    if (!audio || audio.done || problemId == null) return undefined;
    const controller = new AbortController();
    const currentGeneration = generation.current;
    pollRequest.current = controller;
    const timer = setTimeout(() => {
      requestAudio(problemId, 'GET', controller.signal)
        .then(result => {
          if (!controller.signal.aborted && currentGeneration === generation.current) setAudio(result);
        })
        .catch(failure => {
          if (!controller.signal.aborted && currentGeneration === generation.current) {
            setError(failure.message);
            setAudio(previous => ({ ...previous, status: 'failed', done: true }));
          }
        });
    }, 1500);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [audio, problemId]);

  useEffect(() => {
    // Explicitly stop the captured media element even after React detaches it
    // when the user closes the player or opens a different problem.
    const currentPlayer = player.current;
    return () => currentPlayer?.pause();
  }, [visible, audio?.key, audio?.status]);

  async function listen() {
    setVisible(true);
    if (audio?.status === 'ready' || (audio && !audio.done)) return;
    setError('');
    setStarting(true);
    const currentGeneration = generation.current;
    const controller = new AbortController();
    startRequest.current = controller;
    try {
      const result = await requestAudio(problemId, 'POST', controller.signal);
      if (!controller.signal.aborted && currentGeneration === generation.current) setAudio(result);
    } catch (failure) {
      if (!controller.signal.aborted && currentGeneration === generation.current) setError(failure.message);
    } finally {
      if (!controller.signal.aborted && currentGeneration === generation.current) setStarting(false);
    }
  }

  if (problemId == null) return null;
  const busy = starting || (audio && !audio.done);
  const message = error || (audio?.status === 'failed' ? audio.error : '');

  return (
    <div className="problem-audio">
      <button type="button" className="btn btn-secondary problem-audio-button" onClick={listen} disabled={checking || starting} aria-expanded={visible} aria-controls={`problem-narration-${problemId}`}>
        {busy ? <Loader2 size={15} className="problem-audio-spinner" /> : <Volume2 size={15} />}
        {checking ? 'Checking narration…' : busy ? (audio?.status === 'queued' ? 'Narration queued…' : 'Generating narration…') : audio?.status === 'ready' ? 'Listen to problem' : 'Read problem aloud'}
      </button>
      {visible && (
        <section id={`problem-narration-${problemId}`} className="problem-audio-player" aria-label="Problem narration">
          <div className="problem-audio-heading">
            <span>Saved problem narration · Kokoro</span>
            <button type="button" className="problem-audio-close" aria-label="Close narration player" onClick={() => { player.current?.pause(); setVisible(false); }}><X size={16} /></button>
          </div>
          {busy && <p role="status">Creating your MP3. The first narration may take longer while the voice model loads.</p>}
          {message && <p className="problem-audio-error" role="alert">{message}</p>}
          {audio?.status === 'missing' && !busy && <p>Click Read problem aloud to generate narration.</p>}
          {audio?.status === 'ready' && audio.url && (
            <>
              <audio ref={player} key={audio.key} controls preload="metadata" src={audio.url} aria-label="Read problem description aloud" onError={() => setError('The saved narration could not be loaded. Refresh the page and try again.')} />
              <a className="problem-audio-download" href={audio.url} download={`problem-${problemId}-narration.mp3`}><Download size={14} /> Download MP3</a>
            </>
          )}
        </section>
      )}
    </div>
  );
}
