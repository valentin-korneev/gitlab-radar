import { api } from './api.js';
import { API } from './config.js';
import { bindEditorAction } from './editors.js';
import { readLatest } from './requests.js';
import { scanOptionsText } from './scan-options.js';
import { handleScanStatus } from './scan.js';
import { element, formatDate, formatDuration, iconButton } from './shared.js';
import { scanState } from './state.js';
import { showError, showSuccess } from './toasts.js';

const ITEM_TITLES = {
  pending: 'Ожидает обработки', collected: 'Файлы собраны', success: 'Готово', partial: 'Частичный анализ',
  failed: 'Ошибка', reused: 'Анализ использован повторно', missing: 'Не найден', skipped: 'Пропущен',
};
const historyState = { rows: [], cursor: null, selectedId: null, run: null, items: [], itemsCursor: 0, scheduleId: null };
function terminal(run) { return ['completed', 'failed', 'cancelled'].includes(run.state); }
function busy() { return ['queued', 'running', 'stopping'].includes(scanState.scanStatus?.state); }
function sourceText(run) {
  if (run.source === 'schedule') return `Расписание: ${run.schedule_name || 'удалено'}`;
  return `${run.retry_of_id ? `Повтор №${run.retry_of_id}` : 'Ручной запуск'} · ${run.requested_by || 'администратор'}`;
}
async function repeatScan(run, itemId = null) {
  const path = itemId ? `${API.scan}${run.id}/items/${itemId}/retry` : `${API.scan}${run.id}/retry`;
  const next = await api(path, { method: 'POST' });
  await handleScanStatus(next);
  const dialog = document.querySelector('#scan-item-dialog');
  if (dialog.open) dialog.close();
  window.dispatchEvent(new CustomEvent('radar-scan-tab', { detail: 'current' }));
  showSuccess(`Повторный запуск №${next.id} принят`);
}
function renderHistory() {
  const list = document.querySelector('#scan-history-list');
  list.replaceChildren(...historyState.rows.map((run) => {
    const row = element('button', `project-row scan-history-row${run.id === historyState.selectedId ? ' active' : ''}`);
    row.type = 'button';
    const identity = element('span');
    identity.append(element('strong', '', `Запуск №${run.id}`),
      element('small', '', sourceText(run)),
      element('small', '', `${formatDate(run.created_at)} · ${formatDuration(run.duration_seconds)} · проектов: ${run.projects_count}`));
    row.append(identity, element('span', `scan-state-label ${run.state}`, run.state_title));
    row.addEventListener('click', () => selectRun(run.id).catch(showError));
    return row;
  }));
  if (!historyState.rows.length) list.append(element('p', 'empty-state', 'Запусков по выбранным фильтрам нет.'));
}
async function loadHistory(append = false) {
  const query = new URLSearchParams({ limit: 30 });
  if (append && historyState.cursor) query.set('before', historyState.cursor);
  const stateFilter = document.querySelector('#scan-history-state').value;
  const source = document.querySelector('#scan-history-source').value;
  if (stateFilter) query.set('state', stateFilter);
  if (source) query.set('source', source);
  if (historyState.scheduleId) query.set('schedule_id', historyState.scheduleId);
  const result = await readLatest('scan-history', (signal) => api(`${API.scan}history?${query}`, { signal }));
  if (!result) return;
  historyState.rows = append ? [...historyState.rows, ...result.items.filter((run) => !historyState.rows.some((row) => row.id === run.id))] : result.items;
  historyState.cursor = result.cursor;
  document.querySelector('#scan-history-more').hidden = !result.has_more;
  renderHistory();
}
function renderRun() {
  const run = historyState.run;
  const header = document.querySelector('#scan-run-summary');
  const heading = element('div', 'card-heading');
  heading.append(element('p', '', `Запуск №${run.id}`), element('span', `scan-state-label ${run.state}`, run.state_title));
  const stats = element('div', 'compact-list');
  [
    ['Создан', formatDate(run.created_at)], ['Начало', formatDate(run.started_at)], ['Завершение', formatDate(run.completed_at)],
    ['Проектов', run.projects_count], ['Обработано', run.analyzed_projects], ['Повторно', run.reused_projects],
  ].forEach(([label, value]) => {
    const line = element('div'); line.append(element('span', '', label), element('b', '', String(value))); stats.append(line);
  });
  header.replaceChildren(heading, element('p', 'scan-run-source', sourceText(run)),
    element('p', 'schedule-scope', scanOptionsText(run.options)), stats);
  const skipped = element('button', 'scan-run-skipped');
  skipped.type = 'button';
  skipped.disabled = !run.skipped_projects;
  skipped.setAttribute('aria-label', `Показать пропущенные проекты: ${run.skipped_projects}`);
  skipped.setAttribute('aria-controls', 'scan-run-items');
  bindEditorAction(skipped, async () => {
    const filter = document.querySelector('#scan-item-state');
    filter.value = 'skipped';
    await loadRunItems();
    if (historyState.selectedId !== run.id) return;
    filter.focus({ preventScroll: true });
    filter.scrollIntoView({ block: 'nearest' });
  });
  skipped.append(element('span', '', 'Пропущено проектов'), element('b', '', String(run.skipped_projects)));
  header.append(skipped);
  if (run.error) {
    const error = element('section', 'scan-item-error scan-run-error');
    error.append(element('strong', '', 'Причина завершения'), element('p', 'error-text', run.error));
    header.append(error);
  }
  const additionalErrors = run.errors.filter((error) => error !== run.error);
  if (additionalErrors.length) {
    const errors = element('details', 'scan-item-error scan-run-errors');
    errors.append(element('summary', '', `Ошибки проектов · ${additionalErrors.length}`));
    const list = element('ul');
    additionalErrors.forEach((error) => list.append(element('li', '', error)));
    errors.append(list); header.append(errors);
  }
  const actions = element('div', 'scan-management-actions');
  const refresh = iconButton('refresh', 'secondary-button', 'Обновить пункты');
  bindEditorAction(refresh, () => selectRun(run.id));
  actions.append(refresh);
  if (terminal(run)) {
    const retry = iconButton('refresh', 'secondary-button', 'Повторить запуск'); retry.dataset.scanRetry = ''; retry.disabled = busy();
    bindEditorAction(retry, () => repeatScan(run)); actions.append(retry);
  }
  header.append(actions);
}
async function selectRun(id) {
  historyState.selectedId = id;
  historyState.run = null;
  document.querySelector('#scan-run-detail').hidden = true;
  historyState.items = []; historyState.itemsCursor = 0;
  renderHistory();
  document.querySelector('#scan-run-items').replaceChildren();
  const run = await readLatest('scan-run', (signal) => api(`${API.scan}${id}`, { signal }));
  if (!run || id !== historyState.selectedId) return;
  historyState.run = run; renderRun();
  document.querySelector('#scan-run-detail').hidden = false;
  await loadRunItems();
}
async function loadRunItems(append = false) {
  const id = historyState.selectedId;
  if (!id || historyState.run?.id !== id) return;
  const query = new URLSearchParams({ after: append ? historyState.itemsCursor : 0, limit: 50 });
  const filter = document.querySelector('#scan-item-state').value;
  if (filter) query.set('state', filter);
  const result = await readLatest('scan-items', (signal) => api(`${API.scan}${id}/items?${query}`, { signal }));
  if (!result || id !== historyState.selectedId) return;
  historyState.items = append ? [...historyState.items, ...result.items.filter((item) => !historyState.items.some((row) => row.id === item.id))] : result.items;
  historyState.itemsCursor = result.cursor;
  const list = document.querySelector('#scan-run-items');
  list.replaceChildren(...historyState.items.map((item) => {
    const row = element('button', 'project-row scan-item-row'); row.type = 'button';
    const identity = element('span');
    identity.append(element('strong', '', item.project_path), element('small', '', item.ref));
    if (item.error) identity.append(element('small', '', item.error));
    row.append(identity, element('span', `scan-state-label ${item.state}`, ITEM_TITLES[item.state]));
    row.addEventListener('click', () => openItem(id, item.id).catch(showError));
    return row;
  }));
  if (!historyState.items.length) list.append(element('p', 'empty-state', 'Пунктов пока нет или они не соответствуют фильтру.'));
  document.querySelector('#scan-items-more').hidden = !result.has_more;
}
const ITEM_DESCRIPTIONS = {
  pending: 'Проект ожидает обработки в этом запуске.',
  collected: 'Файлы получены. Локальный анализ еще не завершен.',
  success: 'Анализ проекта завершен успешно.',
  partial: 'Часть данных обработана. Ограничения анализа указаны в диагностике ниже.',
  failed: 'Сбор или анализ завершился ошибкой. Причина и доступная диагностика приведены ниже.',
  reused: 'Изменений для анализа не обнаружено. Использован готовый результат.',
  missing: 'Проект не найден среди доступных проектов при этом запуске.',
  skipped: 'Проект пропущен. Если причина сохранена, она указана ниже.',
};
let itemDialogRequest = 0;
function itemProperties(entries) {
  const list = element('dl', 'scan-item-properties');
  entries.forEach(([label, value]) => {
    const row = element('div');
    row.append(element('dt', '', label), element('dd', '', String(value)));
    list.append(row);
  });
  return list;
}
async function openItem(scanId, itemId) {
  const request = ++itemDialogRequest;
  const item = await readLatest('scan-item-detail', (signal) => api(`${API.scan}${scanId}/items/${itemId}`, { signal }));
  if (!item || scanId !== historyState.selectedId || request !== itemDialogRequest) return;
  const run = historyState.run;
  const detail = document.querySelector('#scan-item-detail');
  const status = element('div', 'scan-item-status');
  status.append(element('span', `scan-state-label ${item.state}`, ITEM_TITLES[item.state]));
  detail.replaceChildren(element('h3', 'scan-item-title', item.project_path), status,
    element('p', 'scan-item-description', ITEM_DESCRIPTIONS[item.state]),
    itemProperties([
      ['Запуск', `№${scanId}`], ['Ветка', item.ref || 'Не указана'],
      ['Обработан', item.scanned_at ? formatDate(item.scanned_at) : 'Еще не обработан'],
      ['Проект в GitLab', `№${item.project_id}`],
    ]));
  if (item.error) {
    const error = element('section', 'scan-item-error');
    error.append(element('strong', '', 'Причина'), element('p', 'error-text', item.error));
    detail.append(error);
  }
  const diagnostics = element('section', 'scan-item-diagnostics');
  diagnostics.append(element('h4', '', `Диагностика файлов · ${item.diagnostics.length}`));
  const titles = { invalid: 'Ошибка файла', unsupported: 'Формат не поддержан', partial: 'Частичный анализ' };
  item.diagnostics.forEach((diagnostic) => {
    const card = element('article', 'scan-diagnostic');
    card.append(element('code', '', diagnostic.file_path),
      element('span', `scan-diagnostic-status ${diagnostic.status}`, titles[diagnostic.status] || diagnostic.status),
      element('p', '', diagnostic.message));
    if (diagnostic.language) card.append(element('small', '', `Язык: ${diagnostic.language}`));
    diagnostics.append(card);
  });
  if (!item.diagnostics.length) diagnostics.append(element('p', 'scan-item-description',
    ['pending', 'collected'].includes(item.state) ? 'Диагностика появится после анализа.' : 'Диагностика файлов для этого пункта не сохранена.'));
  detail.append(diagnostics);
  const technical = element('details', 'scan-item-technical');
  technical.append(element('summary', '', 'Технические данные'), itemProperties([
    ['Пункт запуска', `№${item.id}`], ['Результат анализа', item.result_id ? `№${item.result_id}` : 'Не создан'],
    ['Git revision', item.revision || 'Не определена'], ['Fingerprint анализа', item.analysis_fingerprint || 'Не определен'],
  ]));
  detail.append(technical);
  if (run && terminal(run)) {
    const actions = element('div', 'scan-item-actions');
    const retry = iconButton('refresh', 'secondary-button', 'Повторить проект'); retry.dataset.scanRetry = ''; retry.disabled = busy();
    bindEditorAction(retry, () => repeatScan(run, itemId));
    actions.append(element('p', 'scan-item-description', 'Повтор проверит текущую основную ветку проекта.'), retry);
    detail.append(actions);
  }
  const dialog = document.querySelector('#scan-item-dialog'); if (!dialog.open) dialog.showModal();
}
function filterSchedule(id = null, name = '') {
  historyState.scheduleId = id;
  document.querySelector('#scan-history-schedule-filter').hidden = !id;
  document.querySelector('#scan-history-schedule').textContent = id ? `Расписание: ${name} (№${id})` : '';
  document.querySelector('#scan-history-clear-schedule').hidden = !id;
  if (id) document.querySelector('#scan-history-source').value = 'schedule';
}
function initializeHistory() {
  document.querySelector('#scan-history-clear-schedule').addEventListener('click', () => {
    filterSchedule(); loadHistory().catch(showError);
  });
  ['#scan-history-state', '#scan-history-source'].forEach((selector) => {
    document.querySelector(selector).addEventListener('change', () => {
      if (document.querySelector('#scan-history-source').value !== 'schedule') filterSchedule();
      loadHistory().catch(showError);
    });
  });
  document.querySelector('#scan-item-state').addEventListener('change', () => loadRunItems().catch(showError));
  bindEditorAction(document.querySelector('#scan-history-refresh'), () => loadHistory());
  bindEditorAction(document.querySelector('#scan-history-more'), () => loadHistory(true));
  bindEditorAction(document.querySelector('#scan-items-more'), () => loadRunItems(true));
  document.querySelector('#scan-item-dialog').addEventListener('close', () => { itemDialogRequest += 1; });
  document.querySelector('#scan-item-close').addEventListener('click', () => document.querySelector('#scan-item-dialog').close());
}
export { initializeHistory, loadHistory, selectRun, sourceText, filterSchedule };
