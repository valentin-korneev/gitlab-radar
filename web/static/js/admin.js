import { api } from './api.js';
import { API } from './config.js';
import { renderDataQuality, renderLastScan } from './dashboard.js';
import { filterSchedule, initializeHistory, loadHistory, selectRun, sourceText } from './scan-history.js';
import { scanOptionsFields, scanOptionsText } from './scan-options.js';
import { initializeSchedules, loadSchedules } from './schedules.js';
import { readLatest } from './requests.js';
import { connectScanStatusSocket, handleScanStatus } from './scan.js';
import { scanState, state } from './state.js';
import { showError } from './toasts.js';

let initialized = false;
async function switchScanTab(tab) {
  if (tab !== 'current' && !state.auth.user?.is_admin) return;
  document.querySelectorAll('[data-scan-tab]').forEach((button) => {
    const active = button.dataset.scanTab === tab;
    button.setAttribute('aria-selected', String(active)); button.tabIndex = active ? 0 : -1;
  });
  document.querySelectorAll('[data-scan-panel]').forEach((panel) => { panel.hidden = panel.dataset.scanPanel !== tab; });
  if (tab === 'schedules') await loadSchedules();
  if (tab === 'history') await loadHistory();
}
function renderCurrentMetadata(scan) {
  document.querySelector('#scan-run-metadata').textContent = scan.id
    ? `№${scan.id} · ${sourceText(scan)} · ${scanOptionsText(scan.options)}` : '';
  const busy = ['queued', 'running', 'stopping'].includes(scan.state);
  document.querySelector('#manual-scan-options').disabled = busy;
  document.querySelectorAll('[data-scan-retry]').forEach((button) => { button.disabled = busy; });
  document.querySelector('#scan-current-items').hidden = !state.auth.user?.is_admin || !scan.id;
}
function initializeScanManagement() {
  if (initialized) return;
  initialized = true;
  scanOptionsFields(document.querySelector('#manual-scan-options'));
  initializeSchedules(); initializeHistory();
  document.querySelectorAll('[data-scan-tab]').forEach((button) => {
    button.addEventListener('click', () => switchScanTab(button.dataset.scanTab).catch(showError));
    button.addEventListener('keydown', (event) => {
      if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
      event.preventDefault();
      const buttons = [...document.querySelectorAll('[data-scan-tab]')];
      const next = event.key === 'Home' ? 0 : event.key === 'End' ? buttons.length - 1
        : (buttons.indexOf(button) + (event.key === 'ArrowRight' ? 1 : -1) + buttons.length) % buttons.length;
      buttons[next].focus(); switchScanTab(buttons[next].dataset.scanTab).catch(showError);
    });
  });
  document.querySelector('#scan-current-items').addEventListener('click', async () => {
    const id = scanState.scanStatus?.id;
    if (!id) return;
    try { await switchScanTab('history'); await selectRun(id); } catch (error) { showError(error); }
  });
  window.addEventListener('radar-scan-status', (event) => renderCurrentMetadata(event.detail));
  window.addEventListener('radar-schedule-history', (event) => {
    filterSchedule(event.detail.id, event.detail.name); switchScanTab('history').catch(showError);
  });
  window.addEventListener('radar-scan-tab', (event) => switchScanTab(event.detail).catch(showError));
}
async function loadAdmin() {
  initializeScanManagement();
  const administrator = Boolean(state.auth.user?.is_admin);
  document.querySelector('#scan-management-tabs').hidden = !administrator;
  document.querySelector('#manual-scan-options').hidden = !administrator;
  const result = await readLatest('admin', (signal) => Promise.all([
    api(API.dashboard, { signal }), api(API.scan, { signal }),
  ]));
  if (!result) return;
  const [dashboard, scan] = result;
  renderLastScan(dashboard.last_scan); renderDataQuality(dashboard.data_quality);
  await handleScanStatus(scan); renderCurrentMetadata(scan);
  await connectScanStatusSocket();
  state.loaded.admin = true;
}
export { loadAdmin };
