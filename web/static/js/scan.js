import { showError } from './toasts.js';
import { api } from './api.js';
import { API, PHASE_TITLES } from './config.js';
import { loadDashboard } from './dashboard.js';
import { loadDependencies } from './dependencies.js';
import { loadProjects, upsertScannedProjects } from './projects.js';
import { element, formatDate, formatDuration } from './shared.js';
import { scanState, state } from './state.js';

function renderScanStatus(scan) {
  document.querySelector('#scan-state').textContent = scan.state_title;
  const administrator = Boolean(state.auth.user?.is_admin);
  const active = ['running', 'stopping'].includes(scan.state);
  const queued = scan.state === 'queued';
  const button = document.querySelector('#scan-button');
  button.disabled = scanState.scanSubmitting || !administrator || scan.state === 'stopping';
  button.textContent = scan.state === 'stopping' ? 'Останавливается…' : active || queued ? 'Остановить' : 'Запустить сканирование';
  document.querySelector('#scan-dot').className = scan.state;
  let description = 'Сканирование еще не запускалось.';
  if (scan.state === 'queued') description = `Ожидает свободного исполнителя · создано ${formatDate(scan.created_at)}`;
  if (scan.state === 'stopping') description = 'Ожидание завершения текущей операции; новые запросы не начинаются.';
  if (scan.state === 'cancelled') description = `Остановлено ${formatDate(scan.completed_at)} · ${scan.error || 'запуск отменён'}`;
  if (scan.state === 'running') description = `${PHASE_TITLES[scan.phase]} · запущено ${formatDate(scan.started_at)}`;
  if (scan.state === 'completed') description = `Завершено ${formatDate(scan.completed_at)} · проектов: ${scan.projects_count}`;
  if (scan.state === 'failed') description = `Завершено ${formatDate(scan.completed_at)} · ${scan.error || 'неизвестная ошибка'}`;
  document.querySelector('#scan-description').textContent = description;
  document.querySelector('#scan-progress-value').style.width = `${scan.progress_percentage}%`;
  document.querySelector('#scan-progress-label').textContent = `${scan.completed_steps} из ${scan.total_steps} этапов · собрано ${scan.collected_projects}, проанализировано ${scan.analyzed_projects}, повторно ${scan.reused_projects}`;
  document.querySelector('#scan-duration').textContent = formatDuration(scan.duration_seconds);
  document.querySelector('#scan-requests').textContent = `Обращений к GitLab: ${scan.gitlab_requests}`;
  let currentActivity = '';
  if (scan.current_project) currentActivity = `Сейчас: ${scan.current_project}`;
  else if (scan.state === 'running' && scan.phase === 'collecting' && scan.total_steps === 0) {
    currentActivity = 'Сейчас: Получение списка проектов из GitLab';
  } else if (scan.state === 'running') currentActivity = `Сейчас: ${PHASE_TITLES[scan.phase]}`;
  document.querySelector('#scan-current-project').textContent = currentActivity;
  const errors = document.querySelector('#scan-errors');
  const errorList = document.querySelector('#scan-errors-list');
  const allErrors = [...scan.errors];
  if (scan.error && !allErrors.includes(scan.error)) allErrors.push(scan.error);
  errors.hidden = allErrors.length === 0;
  document.querySelector('#scan-errors-count').textContent = allErrors.length;
  errorList.replaceChildren(...allErrors.map((error) => element('p', '', error)));
}
async function connectScanStatusSocket() {
  if (!state.auth.user) return;
  const socketProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  window.clearTimeout(scanState.scanReconnectTimer);
  if (scanState.scanSocket?.readyState === WebSocket.OPEN || scanState.scanSocket?.readyState === WebSocket.CONNECTING) return;
  const ticket = (await api(API.websocketTicket, { method: 'POST' })).ticket;
  const query = `?ticket=${encodeURIComponent(ticket)}`;
  const socket = new WebSocket(`${socketProtocol}//${window.location.host}/api/scan/ws${query}`);
  scanState.scanSocket = socket;
  let messages = Promise.resolve();
  socket.addEventListener('message', (event) => {
    messages = messages.then(() => handleScanStatus(JSON.parse(event.data))).catch(showError);
  });
  socket.addEventListener('close', () => {
    if (scanState.scanSocket === socket) scanState.scanSocket = null;
    if (state.auth.user && ['admin', 'projects'].includes(state.currentRoute)) {
      scanState.scanReconnectTimer = window.setTimeout(connectScanStatusSocket, 3000);
    }
  });
  socket.addEventListener('error', () => socket.close());
}
let scanStatusQueue = Promise.resolve();
function handleScanStatus(scan) {
  const update = scanStatusQueue.then(() => applyScanStatus(scan));
  scanStatusQueue = update.catch(() => {});
  return update;
}
async function applyScanStatus(scan) {
  const previous = scanState.scanStatus;
  if (previous?.id && scan.id && scan.id < previous.id) return;
  if (previous?.id === scan.id) {
    if (['completed', 'failed', 'cancelled'].includes(previous.state) && ['queued', 'running', 'stopping'].includes(scan.state)) return;
    if (previous.state === 'stopping' && scan.state === 'running') return;
    if (scan.completed_steps < previous.completed_steps) return;
  }
  const previousState = scanState.scanState;
  const previousCompletedSteps = scanState.scanStatus?.completed_steps;
  const streamChanged = scanState.scanStreamId !== scan.id;
  scanState.scanState = scan.state;
  scanState.scanStatus = scan;
  renderScanStatus(scan);
  window.dispatchEvent(new CustomEvent('radar-scan-status', { detail: scan }));
  const began = previousState === 'queued' && ['running', 'stopping'].includes(scan.state);
  if (streamChanged || began) {
    scanState.scanStreamId = scan.id;
    if (state.loaded.projects && scan.state !== 'queued') await loadProjects();
    scanState.scanUpdatesCursor = 0;
  }
  while (state.loaded.projects && scanState.scanUpdatesCursor < (scan.updates_count || 0)) {
    const batch = await api(`${API.scan}${scan.id}/updates?after=${scanState.scanUpdatesCursor}&limit=100`);
    if (!await upsertScannedProjects(batch.project_ids, scan.id)) return;
    scanState.scanUpdatesCursor = batch.cursor;
    if (!batch.has_more) break;
  }
  const progressChanged = scan.state === 'running' && scan.completed_steps !== previousCompletedSteps;
  const finished = ['queued', 'running', 'stopping'].includes(previousState) && ['completed', 'failed', 'cancelled'].includes(scan.state);
  if (finished) {
    window.clearTimeout(scanState.dashboardRefreshTimer);
    scanState.dashboardRefreshTimer = null;
    state.dependencyCache = {};
    const reloads = [loadDashboard()];
    if (state.loaded.projects) reloads.push(loadProjects());
    if (state.loaded.dependencies) reloads.push(loadDependencies());
    await Promise.all(reloads);
  } else if (progressChanged && !scanState.dashboardRefreshTimer) {
    scanState.dashboardRefreshTimer = window.setTimeout(() => {
      scanState.dashboardRefreshTimer = null;
      loadDashboard().catch(showError);
    }, 5000);
  }
}
function updateScanDuration() {
  const scan = scanState.scanStatus;
  if (!['running', 'stopping'].includes(scan?.state) || !scan.started_at) return;
  const seconds = Math.max(0, (Date.now() - new Date(scan.started_at).getTime()) / 1000);
  document.querySelector('#scan-duration').textContent = formatDuration(seconds);
}

export { connectScanStatusSocket, handleScanStatus, renderScanStatus, updateScanDuration };
