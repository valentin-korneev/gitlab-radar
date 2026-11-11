function renderScanStatus(scan) {
  document.querySelector('#scan-state').textContent = scan.state_title;
  const administrator = Boolean(state.auth.user?.is_admin);
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
  window.clearTimeout(state.scanReconnectTimer);
  if (state.scanSocket?.readyState === WebSocket.OPEN || state.scanSocket?.readyState === WebSocket.CONNECTING) return;
  const ticket = (await api(API.websocketTicket, { method: 'POST' })).ticket;
  const query = `?ticket=${encodeURIComponent(ticket)}`;
  const socket = new WebSocket(`${socketProtocol}//${window.location.host}/api/scan/ws${query}`);
  state.scanSocket = socket;
  socket.addEventListener('message', (event) => {
    handleScanStatus(JSON.parse(event.data)).catch(showError);
  });
  socket.addEventListener('close', () => {
    if (state.scanSocket === socket) state.scanSocket = null;
    if (state.auth.user && ['admin', 'projects'].includes(state.currentRoute)) {
      state.scanReconnectTimer = window.setTimeout(connectScanStatusSocket, 3000);
    }
  });
  socket.addEventListener('error', () => socket.close());
}
async function handleScanStatus(scan) {
  const previousState = state.scanState;
  const previousCompletedSteps = state.scanStatus?.completed_steps;
  const streamChanged = state.scanStreamId !== scan.id;
  state.scanState = scan.state;
  state.scanStatus = scan;
  renderScanStatus(scan);
  if (streamChanged) {
    state.scanStreamId = scan.id;
    if (state.loaded.projects && scan.state === 'running') await loadProjects();
    state.streamedProjectIds = new Set(
      state.projects
        .filter((project) => project.data_status === 'current')
        .map((project) => project.id),
    );
  }
  for (const projectId of scan.updated_project_ids || []) {
    if (state.streamedProjectIds.has(projectId)) continue;
    state.streamedProjectIds.add(projectId);
    await upsertScannedProject(projectId);
  }
  const progressChanged = scan.state === 'running' && scan.completed_steps !== previousCompletedSteps;
  const finished = previousState === 'running' && ['completed', 'failed'].includes(scan.state);
  if (progressChanged || finished) {
    state.dependencyCache = {};
    const reloads = [loadDashboard()];
    if (finished && state.loaded.projects) reloads.push(loadProjects());
    if (finished && state.loaded.dependencies) reloads.push(loadDependencies());
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

