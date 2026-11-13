import { STATE_CHANNEL } from './config.js';
import { state } from './state.js';

function cookieValue(name) {
  const prefix = `${encodeURIComponent(name)}=`;
  const entry = document.cookie.split('; ').find((value) => value.startsWith(prefix));
  return entry ? decodeURIComponent(entry.slice(prefix.length)) : null;
}
async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  const method = (options.method || 'GET').toUpperCase();
  if (method !== 'GET') {
    const csrfToken = cookieValue('radar_csrf');
    if (csrfToken) headers.set('X-CSRF-Token', csrfToken);
  }
  if (state.auth.user && state.selectedVisibilityGroup !== null) {
    headers.set('X-Radar-Visibility-Group', String(state.selectedVisibilityGroup));
  }
  const response = await fetch(path, { cache: 'no-store', ...options, headers });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || `HTTP ${response.status}`);
  }
  const payload = response.status === 204 ? null : await response.json();
  if (method !== 'GET') {
    window.dispatchEvent(new CustomEvent('radar-mutation', { detail: { path } }));
    STATE_CHANNEL?.postMessage({ path });
  }
  return payload;
}

export { api };
