function cookieValue(name) {
  const prefix = `${encodeURIComponent(name)}=`;
  const entry = document.cookie.split('; ').find((value) => value.startsWith(prefix));
  return entry ? decodeURIComponent(entry.slice(prefix.length)) : null;
}
async function startLogin(routeName = window.location.hash.slice(1) || 'dashboard') {
  const url = new URL(state.auth.config.login_url, window.location.origin);
  url.searchParams.set('return_to', routeName);
  window.location.assign(url);
}
async function logout() {
  window.location.assign(state.auth.config.logout_url);
}
function renderAuth() {
  const authenticated = Boolean(state.auth.user);
  const administrator = Boolean(state.auth.user?.is_admin);
  document.querySelectorAll('.authenticated-navigation, .authenticated-action').forEach((item) => {
    item.hidden = !authenticated;
  });
  document.querySelectorAll('.administrator-navigation').forEach((item) => { item.hidden = !administrator; });
  document.querySelectorAll('.personal-visibility-navigation').forEach((item) => {
    item.hidden = !authenticated;
  });
  if (state.scanStatus) renderScanStatus(state.scanStatus);
  document.querySelector('#auth-panel').hidden = false;
  document.querySelector('#auth-user').textContent = authenticated
    ? state.auth.user.preferred_username || state.auth.user.name || 'Пользователь'
    : 'Публичный доступ';
  document.querySelector('#auth-button').textContent = authenticated ? 'Выйти' : 'Войти';
}
async function initializeAuth() {
  const configResponse = await fetch(API.authConfig, { cache: 'no-store' });
  if (!configResponse.ok) throw new Error('Не удалось загрузить настройки авторизации');
  state.auth.config = await configResponse.json();
  const sessionResponse = await fetch(API.authSession, { cache: 'no-store' });
  state.auth.user = sessionResponse.ok ? await sessionResponse.json() : null;
  renderAuth();
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
  if (method !== 'GET') STATE_CHANNEL?.postMessage({ path });
  return payload;
}
