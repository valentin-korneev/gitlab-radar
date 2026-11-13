import { api } from './api.js';
import { API, ITEM_TITLES } from './config.js';
import { bindEditorAction } from './editors.js';
import { readLatest } from './requests.js';
import { element, formatDate, iconButton, languageDisplayName } from './shared.js';
import { showError } from './toasts.js';

const CHANGE_TITLES = { added: 'Добавлен', removed: 'Удален', updated: 'Изменен' };
const history = { projectId: null, targetId: null, scanId: null, rows: [], cursor: null, changesCursor: '', view: 'changes', periodKey: null, periodCursor: null, generation: 0 };
let initialized = false;
function base() { return `${API.projects}${history.projectId}`; }
function versions(values) { return values.length ? values.map((value) => value ?? 'Без ограничения версии').join(', ') : '—'; }
function scopeTitle(scope) {
  if (scope.startsWith('optional:')) return `Группа ${scope.slice(9)}`;
  return scope === 'transitive' ? 'Транзитивная' : 'Прямая';
}
function valid(generation) { return generation === history.generation && document.querySelector('#project-history-dialog').open; }
function initializeProjectHistory() {
  if (initialized) return;
  initialized = true;
  const dialog = document.querySelector('#project-history-dialog');
  dialog.addEventListener('close', () => { history.generation += 1; });
  document.querySelector('#project-history-close').addEventListener('click', () => dialog.close());
  document.querySelector('#project-history-target').addEventListener('change', (event) => {
    history.targetId = Number(event.target.value); history.scanId = null; history.periodKey = null;
    document.querySelector('#project-observation-list').replaceChildren(element('p', 'empty-state', 'Загрузка истории…'));
    document.querySelector('#project-changes-content').replaceChildren();
    loadObservations().catch(showError);
  });
  ['#project-history-module', '#project-history-name'].forEach((selector) => {
    document.querySelector(selector).addEventListener('change', () => { if (history.scanId) loadChanges().catch(showError); });
  });
  bindEditorAction(document.querySelector('#project-history-refresh'), () => loadObservations());
  bindEditorAction(document.querySelector('#project-history-more'), () => loadObservations(true));
  bindEditorAction(document.querySelector('#package-changes-more'), () => loadChanges(true));
  bindEditorAction(document.querySelector('#package-periods-more'), () => loadPeriods(true));
  ['changes', 'inventory'].forEach((view) => {
    document.querySelector(`#package-view-${view}`).addEventListener('click', () => {
      history.view = view;
      document.querySelectorAll('.package-history-tabs button').forEach((button) => button.setAttribute('aria-selected', String(button.id === `package-view-${view}`)));
      loadChanges().catch(showError);
    });
  });
  document.querySelector('#package-periods-close').addEventListener('click', () => {
    history.periodKey = null;
    document.querySelector('#package-periods-panel').hidden = true;
    document.querySelector('#package-changes-panel').hidden = false;
  });
}
async function openProjectHistory(project, modulePath = '') {
  initializeProjectHistory(); history.generation += 1;
  const generation = history.generation;
  history.projectId = project.id; history.scanId = null; history.targetId = null;
  document.querySelector('#project-history-title').textContent = project.path_with_namespace;
  document.querySelector('#project-history-module').value = modulePath;
  document.querySelector('#project-history-name').value = '';
  document.querySelector('#project-observation-list').replaceChildren(element('p', 'empty-state', 'Загрузка истории…'));
  document.querySelector('#project-changes-content').replaceChildren();
  const select = document.querySelector('#project-history-target'); select.replaceChildren();
  const dialog = document.querySelector('#project-history-dialog'); if (!dialog.open) dialog.showModal();
  const targets = await readLatest('project-history-targets', (signal) => api(`${base()}/history/targets`, { signal }));
  if (!targets || !valid(generation)) return;
  targets.forEach((target) => {
    const option = element('option', '', `${target.kind === 'merge_request' ? 'MR' : 'Ветка'}: ${target.ref}${target.is_default ? ' · основная' : ''}`);
    option.value = target.id; select.append(option);
  });
  history.targetId = targets.find((target) => target.is_default)?.id || targets[0]?.id;
  if (!history.targetId) {
    document.querySelector('#project-observation-list').replaceChildren(element('p', 'empty-state', 'Истории целей пока нет.'));
    return;
  }
  select.value = history.targetId; await loadObservations();
}
async function loadObservations(append = false) {
  if (!history.targetId) return;
  const generation = history.generation; const targetId = history.targetId;
  const query = new URLSearchParams({ target_id: targetId, limit: 30 });
  if (append && history.cursor) query.set('before', history.cursor);
  const result = await readLatest('project-observations', (signal) => api(`${base()}/history?${query}`, { signal }));
  if (!result || !valid(generation) || targetId !== history.targetId) return;
  history.rows = append ? [...history.rows, ...result.items] : result.items;
  history.cursor = result.cursor;
  document.querySelector('#project-history-more').hidden = !result.has_more;
  renderObservations();
  if (!append) {
    history.scanId = history.rows.some((row) => row.scan_id === history.scanId) ? history.scanId : history.rows[0]?.scan_id;
    if (history.scanId) await loadChanges();
    else document.querySelector('#project-changes-content').replaceChildren(element('p', 'empty-state', 'Наблюдений проекта пока нет.'));
    renderObservations();
  }
}
function renderObservations() {
  const list = document.querySelector('#project-observation-list');
  list.replaceChildren(...history.rows.map((observation) => {
    const row = element('button', `project-row package-observation${observation.scan_id === history.scanId ? ' active' : ''}`);
    row.type = 'button';
    const identity = element('span');
    identity.append(element('strong', '', `Запуск №${observation.scan_id}`),
      element('small', '', formatDate(observation.scanned_at || observation.created_at)),
      element('small', '', observation.history_recorded
        ? `Добавлено: ${observation.added_packages} · удалено: ${observation.removed_packages} · изменено: ${observation.updated_packages}`
        : 'История подготавливается'));
    row.append(identity, element('span', `scan-state-label ${observation.state}`, ITEM_TITLES[observation.state]));
    row.addEventListener('click', () => {
      history.scanId = observation.scan_id; renderObservations(); loadChanges().catch(showError);
    });
    return row;
  }));
  if (!history.rows.length) list.append(element('p', 'empty-state', 'Наблюдений проекта пока нет.'));
}
async function loadChanges(append = false) {
  if (!history.scanId) return;
  const generation = history.generation;
  const targetId = history.targetId; const scanId = history.scanId; const view = history.view;
  history.periodKey = null;
  const query = new URLSearchParams({ target_id: targetId, limit: 50 });
  if (append) query.set('after', history.changesCursor);
  const modulePath = document.querySelector('#project-history-module').value.trim();
  if (modulePath) query.set('module_path', modulePath);
  const name = document.querySelector('#project-history-name').value.trim();
  if (name) query.set('name', name);
  const result = await readLatest('package-changes', (signal) => api(`${base()}/history/${scanId}/${view === 'inventory' ? 'packages' : 'changes'}?${query}`, { signal }));
  if (!result || !valid(generation) || targetId !== history.targetId || scanId !== history.scanId || view !== history.view) return;
  history.changesCursor = result.cursor;
  document.querySelector('#package-periods-panel').hidden = true;
  document.querySelector('#package-changes-panel').hidden = false;
  const list = document.querySelector('#project-changes-content');
  if (!append) {
    list.replaceChildren();
    let message = result.history_recorded ? 'Версии сравниваются с предыдущим полным анализом этой цели.' : 'История подготавливается. Обновите список через некоторое время.';
    if (view === 'changes' && result.history_recorded && !result.observed_languages.length) message = 'Полного наблюдения пакетов нет. Удаления и изменения версий не вычислялись.';
    if (view === 'changes' && result.baseline_languages.length) message = `Начало наблюдений: ${result.baseline_languages.map((code) => languageDisplayName(code)).join(', ')}. Исходные версии сохранены без отметки «добавлено».`;
    if (view === 'inventory') message = 'Последние подтвержденные версии к этому наблюдению. Ошибки и отключение анализа не подтверждают удаление пакетов. Выберите пакет для просмотра диапазонов версий.';
    list.append(element('p', 'scan-item-description', message));
    if (!result.items.length && (view === 'inventory' || result.observed_languages.length)) list.append(element('p', 'empty-state', 'Изменений пакетов по выбранному модулю нет.'));
  }
  result.items.forEach((change) => {
    const row = element('button', 'package-change-row'); row.type = 'button';
    row.setAttribute('aria-label', `История версий ${change.name}`);
    const heading = element('span', 'package-change-heading');
    heading.append(element('strong', '', change.name));
    if (change.kind) heading.append(element('span', `package-change-kind ${change.kind}`, CHANGE_TITLES[change.kind]));
    row.append(heading, element('small', '', `${languageDisplayName(change.language)} · ${change.module_path} · ${scopeTitle(change.scope)}`),
      element('span', 'package-version-diff', change.kind ? `${versions(change.before_versions)} → ${versions(change.after_versions)}` : versions(change.versions)));
    row.addEventListener('click', () => {
      history.periodKey = change.package_key; history.periodCursor = null;
      document.querySelector('#package-period-title').textContent = `${change.name} · ${change.module_path} · ${scopeTitle(change.scope)}`;
      loadPeriods().catch(showError);
    }); list.append(row);
  });
  document.querySelector('#package-changes-more').hidden = !result.has_more;
}
async function loadPeriods(append = false) {
  const generation = history.generation;
  const targetId = history.targetId; const key = history.periodKey;
  const query = new URLSearchParams({ target_id: targetId, limit: 30 });
  if (append && history.periodCursor) query.set('before', history.periodCursor);
  const result = await readLatest('package-periods', (signal) => api(`${base()}/package-history/${key}?${query}`, { signal }));
  if (!result || !valid(generation) || targetId !== history.targetId || key !== history.periodKey) return;
  history.periodCursor = result.cursor;
  document.querySelector('#package-periods-panel').hidden = false;
  document.querySelector('#package-changes-panel').hidden = true;
  const list = document.querySelector('#package-period-list'); if (!append) list.replaceChildren();
  result.items.forEach((period) => {
    const row = element('article', 'package-period');
    row.append(element('strong', '', versions(period.versions)),
      element('p', '', `Наблюдалась в запусках №${period.scan_from_id}–№${period.scan_to_id}`),
      element('small', '', period.closed_in_id ? `Изменена или удалена в запуске №${period.closed_in_id}` : 'Последняя известная версия'));
    list.append(row);
  });
  document.querySelector('#package-periods-more').hidden = !result.has_more;
}
export { openProjectHistory };
