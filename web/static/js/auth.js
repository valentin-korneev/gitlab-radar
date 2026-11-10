function clearTokens() {
  state.auth.tokens = null;
  state.auth.user = null;
  renderAuth();
}
function accessToken() {
  return state.auth.config?.required ? (state.auth.user ? 'cookie-session' : null) : null;
}
async function startLogin(routeName = window.location.hash.slice(1) || 'dashboard') {
  sessionStorage.setItem('radar-auth-route', routeName);
  window.location.assign('/api/auth/login');
}
async function logout() {
  const csrf = document.cookie.split('; ').find((item) => item.startsWith('radar_csrf='))
    ?.split('=').slice(1).join('=');
  await fetch('/api/auth/logout', {
    method: 'POST',
    headers: { 'X-CSRF-Token': decodeURIComponent(csrf || '') },
    credentials: 'same-origin',
  });
  clearTokens();
  window.location.assign('/');
}
function renderAuth() {
  const panel = document.querySelector('#auth-panel');
  const developmentInput = document.querySelector('#development-user');
  const authenticated = Boolean(state.auth.user);
  const administrator = Boolean(state.auth.user?.is_admin);
  document.querySelectorAll('.authenticated-navigation').forEach((item) => { item.hidden = !authenticated; });
  document.querySelectorAll('.administrator-navigation').forEach((item) => { item.hidden = !administrator; });
  document.querySelectorAll('.personal-visibility-navigation').forEach((item) => { item.hidden = !authenticated; });
  if (state.scanStatus) renderScanStatus(state.scanStatus);
  if (!state.auth.config?.required) {
    panel.hidden = false;
    developmentInput.hidden = false;
    developmentInput.value = state.auth.developmentUsername || '';
    document.querySelector('#auth-user').textContent = authenticated
      ? `Тестовый пользователь: ${state.auth.user.preferred_username}` : 'Локальный режим';
    document.querySelector('#auth-button').textContent = 'Применить';
    return;
  }
  developmentInput.hidden = true;
  panel.hidden = false;
  document.querySelector('#auth-user').textContent = authenticated
    ? state.auth.user.preferred_username || state.auth.user.name || 'Пользователь' : 'Управление защищено';
  document.querySelector('#auth-button').textContent = authenticated ? 'Выйти' : 'Войти';
}
async function initializeAuth() {
  const response = await fetch(API.authConfig, { cache: 'no-store', credentials: 'same-origin' });
  if (!response.ok) throw new Error('Не удалось загрузить настройки авторизации');
  state.auth.config = await response.json();
  if (!state.auth.config.required) {
    state.auth.developmentUsername = localStorage.getItem('radar-development-user')
      || state.auth.config.development_username;
    try {
      state.auth.user = await api(API.authSession);
    } catch (error) {
      if (state.auth.developmentUsername === state.auth.config.development_username) throw error;
      state.auth.developmentUsername = state.auth.config.development_username;
      localStorage.setItem('radar-development-user', state.auth.developmentUsername);
      state.auth.user = await api(API.authSession);
    }
    renderAuth();
    return;
  }
  const parameters = new URLSearchParams(window.location.search);
  if (parameters.has('error')) throw new Error(parameters.get('error_description') || 'Авторизация отменена');
  if (parameters.has('login') || sessionStorage.getItem('radar-auth-route')) {
    const route = sessionStorage.getItem('radar-auth-route') || window.location.hash.slice(1) || 'dashboard';
    sessionStorage.removeItem('radar-auth-route');
    window.history.replaceState(null, '', `${window.location.pathname}#${route}`);
  }
  try {
    state.auth.user = await api(API.authSession);
  } catch (error) {
    state.auth.user = null;
    if (AUTHENTICATED_ROUTES.has(window.location.hash.slice(1)) || ADMINISTRATOR_ROUTES.has(window.location.hash.slice(1))) {
      await startLogin(window.location.hash.slice(1));
      return;
    }
  }
  renderAuth();
}
async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (!state.auth.config?.required && state.auth.developmentUsername) {
    headers.set('X-Radar-Development-User', state.auth.developmentUsername);
  }
  if (state.auth.config?.required && (options.method || 'GET').toUpperCase() !== 'GET') {
    const csrf = document.cookie.split('; ').find((item) => item.startsWith('radar_csrf='))
      ?.split('=').slice(1).join('=');
    if (csrf) headers.set('X-CSRF-Token', decodeURIComponent(csrf));
  }
  if (state.selectedVisibilityGroup !== null) {
    headers.set('X-Radar-Visibility-Group', String(state.selectedVisibilityGroup));
  }
  const response = await fetch(path, {
    cache: 'no-store', credentials: 'same-origin', ...options, headers,
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || `HTTP ${response.status}`);
  }
  const payload = response.status === 204 ? null : await response.json();
  if ((options.method || 'GET').toUpperCase() !== 'GET') STATE_CHANNEL?.postMessage({ path });
  return payload;
}
async function applyDevelopmentUser(preferredUsername) {
  const value = preferredUsername.trim() || state.auth.config.development_username;
  state.auth.developmentUsername = value;
  localStorage.setItem('radar-development-user', value);
  state.auth.user = await api(API.authSession);
  Object.keys(state.loaded).forEach((page) => { state.loaded[page] = false; });
  state.authorizedUsers = [];
  state.visibilityGroups = [];
  state.selectedVisibilityGroup = null;
  invalidateVisibilityData();
  renderAuth();
  await loadVisibilityGroups();
  await showPage();
}
