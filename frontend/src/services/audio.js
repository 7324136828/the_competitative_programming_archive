export const AUDIO_CACHE_CLEARED_EVENT = 'audio-cache-cleared';

async function requestAudio(path, { signal, method = 'GET', body } = {}, key = 'audio') {
  const response = await fetch(path, {
    method,
    signal,
    ...(body === undefined ? {} : {
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  });
  const result = await response.json().catch(() => ({}));
  if (!response.ok || result.success === false || !result[key]) {
    throw new Error(typeof result.error === 'string' ? result.error : 'Unable to load saved audio. Please try again.');
  }
  return result[key];
}

export function startResponseAudio(text, language, signal) {
  return requestAudio('/api/audio/responses', { method: 'POST', body: { text, language }, signal });
}

export function getResponseAudio(key, signal) {
  return requestAudio(`/api/audio/responses/${encodeURIComponent(key)}`, { signal });
}

export function getAudioCache(signal) {
  return requestAudio('/api/audio/cache', { signal }, 'cache');
}

export async function clearAudioCache(signal) {
  const cache = await requestAudio('/api/audio/cache', { method: 'DELETE', signal }, 'cache');
  window.dispatchEvent(new CustomEvent(AUDIO_CACHE_CLEARED_EVENT, { detail: cache }));
  return cache;
}
