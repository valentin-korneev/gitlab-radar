import { API } from './config.js';
import { renderScanStatus } from './scan.js';
import { scanState, state } from './state.js';

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
  if (scanState.scanStatus) renderScanStatus(scanState.scanStatus);
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


export { initializeAuth, logout, startLogin };
