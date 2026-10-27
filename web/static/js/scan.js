function renderScanStatus(scan) {
  document.querySelector('#scan-state').textContent = scan.state_title;
  const administrator = !state.auth.config?.required || Boolean(state.auth.user?.is_admin);
  document.querySelector('#scan-button').disabled = scan.state === 'running' || !administrator;
  document.querySelector('#scan-dot').className = scan.state;
  let description = 'Сканирование еще не запускалось.';
  if (scan.state === 'running') description = `${PHASE_TITLES[scan.phase]} · запущено ${formatDate(scan.started_at)}`;
  if (scan.state === 'completed') description = `Завершено ${formatDate(scan.completed_at)} · проектов: ${scan.projects_count}`;
  if (scan.state === 'failed') description = `Завершено ${formatDate(scan.completed_at)} · ${scan.error || 'неизвестная ошибка'}`;
  document.querySelector('#scan-description').textContent = description;
  document.querySelector('#scan-progress-value').style.width = `${scan.progress_percentage}%`;
  document.querySelector('#scan-progress-label').textContent = `${scan.completed_steps} из ${scan.total_steps} этапов · собрано ${scan.collected_projects}, проанализировано ${scan.analyzed_projects}, повторно ${scan.reused_projects}`;
  document.querySelector('#scan-duration').textContent = formatDuration(scan.duration_seconds);
  document.querySelector('#scan-requests').textContent = `Обращений к GitLab: ${scan.gitlab_requests}`;
  document.querySelector('#scan-current-project').textContent = scan.current_project ? `Сейчас: ${scan.current_project}` : '';
  const errors = document.querySelector('#scan-errors');
  const errorList = document.querySelector('#scan-errors-list');
  const allErrors = [...scan.errors];
  if (scan.error && !allErrors.includes(scan.error)) allErrors.push(scan.error);
  errors.hidden = allErrors.length === 0;
  document.querySelector('#scan-errors-count').textContent = allErrors.length;
  errorList.replaceChildren(...allErrors.map((error) => element('p', '', error)));
}
async function connectScanStatusSocket() {
  const token = await accessToken();
  if (state.auth.config?.required && !token) return;
  const socketProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  window.clearTimeout(state.scanReconnectTimer);
  if (state.scanSocket?.readyState === WebSocket.OPEN || state.scanSocket?.readyState === WebSocket.CONNECTING) return;
  const ticket = state.auth.config?.required
    ? (await api(API.websocketTicket, { method: 'POST' })).ticket
    : null;
  const query = ticket ? `?ticket=${encodeURIComponent(ticket)}` : '';
  const socket = new WebSocket(`${socketProtocol}//${window.location.host}/api/scan/ws${query}`);
  state.scanSocket = socket;
  socket.addEventListener('message', (event) => {
    handleScanStatus(JSON.parse(event.data)).catch(showError);
  });
  socket.addEventListener('close', () => {
    if (state.scanSocket === socket) state.scanSocket = null;
    if (window.location.hash === '#admin') state.scanReconnectTimer = window.setTimeout(connectScanStatusSocket, 3000);
  });
  socket.addEventListener('error', () => socket.close());
}
async function handleScanStatus(scan) {
  const previousState = state.scanState;
  state.scanState = scan.state;
  state.scanStatus = scan;
  renderScanStatus(scan);
  if (previousState === 'running' && scan.state === 'completed') {
    state.dependencyCache = {};
    const reloads = [loadDashboard()];
    if (state.loaded.projects) reloads.push(loadProjects());
    if (state.loaded.dependencies) reloads.push(loadDependencies());
    await Promise.all(reloads);
  }
}
function updateScanDuration() {
  const scan = state.scanStatus;
  if (scan?.state !== 'running' || !scan.started_at) return;
  const seconds = Math.max(0, (Date.now() - new Date(scan.started_at).getTime()) / 1000);
  document.querySelector('#scan-duration').textContent = formatDuration(seconds);
}
let toastTimer = null;
function showToast(message, type) {
  const toast = document.querySelector('#global-error');
  toast.textContent = message;
  toast.classList.toggle('success', type === 'success');
  toast.classList.toggle('error', type === 'error');
  toast.hidden = false;
  if (toastTimer) window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => { toast.hidden = true; }, 4000);
}
function showSuccess(message) {
  showToast(message, 'success');
}
function showError(error) {
  showToast(error.message, 'error');
}

