import React, { useEffect, useId, useRef, useState } from 'react';
import { Download, Loader2, Volume2, X } from 'lucide-react';
import { AUDIO_CACHE_CLEARED_EVENT, getResponseAudio, startResponseAudio } from '../services/audio';
import './ResponseAudio.css';

export default function ResponseAudio({ text, language = 'en', label = 'Read aloud' }) {
  const [audio, setAudio] = useState(null);
  const [visible, setVisible] = useState(false);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState('');
  const request = useRef(null);
  const pollRequest = useRef(null);
  const player = useRef(null);
  const generation = useRef(0);
  const id = useId();
  const content = typeof text === 'string' ? text : text == null ? '' : JSON.stringify(text, null, 2);

  useEffect(() => {
    function reset() {
      generation.current += 1;
      request.current?.abort();
      pollRequest.current?.abort();
      player.current?.pause();
      setAudio(null);
      setVisible(false);
      setStarting(false);
      setError('');
    }
    reset();
    window.addEventListener(AUDIO_CACHE_CLEARED_EVENT, reset);
    return () => {
      generation.current += 1;
      request.current?.abort();
      pollRequest.current?.abort();
      window.removeEventListener(AUDIO_CACHE_CLEARED_EVENT, reset);
    };
  }, [content, language]);

  useEffect(() => {
    if (!audio || audio.done || !audio.key) return undefined;
    const controller = new AbortController();
    const currentGeneration = generation.current;
    pollRequest.current = controller;
    const timer = setTimeout(async () => {
      try {
        const result = await getResponseAudio(audio.key, controller.signal);
        if (!controller.signal.aborted && currentGeneration === generation.current) setAudio(result);
      } catch (failure) {
        if (!controller.signal.aborted && currentGeneration === generation.current) {
          setError(failure.message);
          setAudio(previous => ({ ...previous, status: 'failed', done: true }));
        }
      }
    }, 1500);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [audio]);

  useEffect(() => {
    const currentPlayer = player.current;
    return () => currentPlayer?.pause();
  }, [visible, audio?.key, audio?.status]);

  async function listen() {
    setVisible(true);
    if (audio?.status === 'ready' || (audio && !audio.done)) return;
    setStarting(true);
    setError('');
    const currentGeneration = generation.current;
    const controller = new AbortController();
    request.current = controller;
    try {
      const result = await startResponseAudio(content, language, controller.signal);
      if (!controller.signal.aborted && currentGeneration === generation.current) setAudio(result);
    } catch (failure) {
      if (!controller.signal.aborted && currentGeneration === generation.current) setError(failure.message);
    } finally {
      if (!controller.signal.aborted && currentGeneration === generation.current) setStarting(false);
    }
  }

  if (!content.trim()) return null;
  const busy = starting || (audio && !audio.done);
  const message = error || (audio?.status === 'failed' ? audio.error : '');

  return (
    <div className="response-audio">
      <button type="button" className="response-audio-button" onClick={listen} disabled={starting} aria-expanded={visible} aria-controls={id}>
        {busy ? <Loader2 size={14} className="response-audio-spinner" /> : <Volume2 size={14} />}
        {busy ? (audio?.status === 'queued' ? 'Narration queued...' : 'Generating narration...') : label}
      </button>
      {visible && (
        <section id={id} className="response-audio-player" aria-label="AI response narration">
          <div className="response-audio-heading">
            <span>Saved AI narration · Kokoro</span>
            <button type="button" className="response-audio-close" aria-label="Close AI narration player" onClick={() => { player.current?.pause(); setVisible(false); }}><X size={15} /></button>
          </div>
          {busy && <p role="status">Creating your MP3. You can keep reading while it generates.</p>}
          {message && <p role="alert" className="response-audio-error">{message}</p>}
          {audio?.status === 'missing' && !busy && <p>This narration is no longer saved. Click {label} to generate it again.</p>}
          {audio?.status === 'ready' && audio.url && (
            <>
              <audio ref={player} key={audio.key} controls preload="metadata" src={audio.url} aria-label="Read AI response aloud" onError={() => {
                setError('The saved narration could not be loaded. Click Read aloud to try again.');
                setAudio(previous => ({ ...previous, status: 'failed', done: true }));
              }} />
              <a className="response-audio-download" href={audio.url} download={`ai-response-${audio.key.slice(0, 12)}.mp3`}><Download size={13} /> Download MP3</a>
            </>
          )}
        </section>
      )}
    </div>
  );
}
