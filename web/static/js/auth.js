function base64Url(bytes) {
  return btoa(String.fromCharCode(...bytes)).replaceAll('+', '-').replaceAll('/', '_').replaceAll('=', '');
}
function decodeToken(token) {
  const encoded = token.split('.')[1].replaceAll('-', '+').replaceAll('_', '/');
  const padded = encoded.padEnd(Math.ceil(encoded.length / 4) * 4, '=');
  return JSON.parse(new TextDecoder().decode(Uint8Array.from(atob(padded), (character) => character.charCodeAt(0))));
}
function tokenEndpoint() {
  return `${state.auth.config.issuer}/protocol/openid-connect/token`;
}
function saveTokens(tokens) {
  const payload = decodeToken(tokens.access_token);
  state.auth.tokens = { ...state.auth.tokens, ...tokens, expires_at: payload.exp };
  sessionStorage.setItem('radar-auth-tokens', JSON.stringify(state.auth.tokens));
}
function clearTokens() {
  state.auth.tokens = null;
  state.auth.user = null;
  sessionStorage.removeItem('radar-auth-tokens');
  renderAuth();
}
async function accessToken() {
  if (!state.auth.config?.required) return null;
  if (!state.auth.tokens) return null;
  if (state.auth.tokens.expires_at * 1000 > Date.now() + 30000) return state.auth.tokens.access_token;
  if (!state.auth.tokens.refresh_token) {
    clearTokens();
    return null;
  }
  const body = new URLSearchParams({
    grant_type: 'refresh_token',
    client_id: state.auth.config.client_id,
    refresh_token: state.auth.tokens.refresh_token,
  });
  const response = await fetch(tokenEndpoint(), {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body,
  });
  if (!response.ok) {
    clearTokens();
    return null;
  }
  saveTokens(await response.json());
  return state.auth.tokens.access_token;
}
async function startLogin(routeName = window.location.hash.slice(1) || 'dashboard') {
  const redirectUrl = new URL(state.auth.config.redirect_uri);
  if (window.location.origin !== redirectUrl.origin) {
    redirectUrl.searchParams.set('login', '1');
    redirectUrl.hash = routeName;
    window.location.assign(redirectUrl);
    return;
  }
  if (!globalThis.crypto?.subtle) {
    throw new Error('Авторизация требует безопасный адрес. Откройте приложение через 127.0.0.1 или HTTPS.');
  }
  const verifier = base64Url(crypto.getRandomValues(new Uint8Array(48)));
  const challenge = base64Url(new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier))));
  const oauthState = base64Url(crypto.getRandomValues(new Uint8Array(24)));
  sessionStorage.setItem('radar-auth-verifier', verifier);
  sessionStorage.setItem('radar-auth-state', oauthState);
  sessionStorage.setItem('radar-auth-route', routeName);
  const parameters = new URLSearchParams({
    client_id: state.auth.config.client_id,
    redirect_uri: state.auth.config.redirect_uri,
    response_type: 'code',
    scope: 'openid profile email',
    state: oauthState,
    code_challenge: challenge,
    code_challenge_method: 'S256',
  });
  window.location.assign(`${state.auth.config.issuer}/protocol/openid-connect/auth?${parameters}`);
}
async function finishLogin(code, returnedState) {
  const expectedState = sessionStorage.getItem('radar-auth-state');
  const verifier = sessionStorage.getItem('radar-auth-verifier');
  if (!expectedState || returnedState !== expectedState || !verifier) throw new Error('Не удалось проверить ответ авторизации');
  const response = await fetch(tokenEndpoint(), {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      grant_type: 'authorization_code',
      client_id: state.auth.config.client_id,
      redirect_uri: state.auth.config.redirect_uri,
      code,
      code_verifier: verifier,
    }),
  });
  if (!response.ok) throw new Error('Keycloak отклонил авторизацию');
  saveTokens(await response.json());
  const route = sessionStorage.getItem('radar-auth-route') || 'dashboard';
  ['radar-auth-state', 'radar-auth-verifier', 'radar-auth-route'].forEach((key) => sessionStorage.removeItem(key));
  window.history.replaceState(null, '', `${window.location.pathname}#${route}`);
}
async function logout() {
  const idToken = state.auth.tokens?.id_token;
  clearTokens();
  if (!idToken) return;
  const parameters = new URLSearchParams({
    client_id: state.auth.config.client_id,
    id_token_hint: idToken,
    post_logout_redirect_uri: state.auth.config.redirect_uri,
  });
  window.location.assign(`${state.auth.config.issuer}/protocol/openid-connect/logout?${parameters}`);
}
function renderAuth() {
  const panel = document.querySelector('#auth-panel');
  const authenticated = Boolean(state.auth.user);
  const administrator = !state.auth.config?.required || Boolean(state.auth.user?.is_admin);
  document.querySelectorAll('.authenticated-navigation').forEach((item) => {
    item.hidden = Boolean(state.auth.config?.required) && !authenticated;
  });
  document.querySelectorAll('.administrator-navigation').forEach((item) => { item.hidden = !administrator; });
  if (state.scanStatus) renderScanStatus(state.scanStatus);
  if (!state.auth.config?.required) {
    panel.hidden = true;
    return;
  }
  panel.hidden = false;
  document.querySelector('#auth-user').textContent = authenticated
    ? state.auth.user.preferred_username || state.auth.user.name || 'Пользователь'
    : 'Управление защищено';
  document.querySelector('#auth-button').textContent = authenticated ? 'Выйти' : 'Войти';
}
async function initializeAuth() {
  const response = await fetch(API.authConfig, { cache: 'no-store' });
  if (!response.ok) throw new Error('Не удалось загрузить настройки авторизации');
  state.auth.config = await response.json();
  if (!state.auth.config.required) {
    state.auth.tokens = null;
    state.auth.user = null;
    sessionStorage.removeItem('radar-auth-tokens');
    renderAuth();
    return;
  }
  const stored = sessionStorage.getItem('radar-auth-tokens');
  if (stored) {
    try {
      state.auth.tokens = JSON.parse(stored);
    } catch (error) {
      clearTokens();
    }
  }
  const parameters = new URLSearchParams(window.location.search);
  if (parameters.has('error')) throw new Error(parameters.get('error_description') || 'Авторизация отменена');
  if (parameters.has('code')) await finishLogin(parameters.get('code'), parameters.get('state'));
  if (parameters.get('login') === '1') {
    window.history.replaceState(null, '', `${window.location.pathname}${window.location.hash}`);
    await startLogin(window.location.hash.slice(1) || 'dashboard');
    return;
  }
  if (state.auth.tokens) {
    try {
      state.auth.user = await api(API.authSession);
    } catch (error) {
      clearTokens();
      showError(error);
      if (AUTHENTICATED_ROUTES.has(window.location.hash.slice(1)) || ADMINISTRATOR_ROUTES.has(window.location.hash.slice(1))) {
        window.history.replaceState(null, '', `${window.location.pathname}#dashboard`);
      }
    }
  }
  renderAuth();
}

async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  const token = await accessToken();
  if (token) headers.set('Authorization', `Bearer ${token}`);
  const response = await fetch(path, { cache: 'no-store', ...options, headers });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || `HTTP ${response.status}`);
  }
  const payload = response.status === 204 ? null : await response.json();
  if ((options.method || 'GET').toUpperCase() !== 'GET') STATE_CHANNEL?.postMessage({ path });
  return payload;
}
