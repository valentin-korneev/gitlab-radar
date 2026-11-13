import { api } from './api.js';
import { API } from './config.js';
import { bindEditorAction, bindEditorChange, bindEditorForm } from './editors.js';
import { readLatest } from './requests.js';
import { fillScanOptions, readScanOptions, scanOptionsFields, scanOptionsText } from './scan-options.js';
import { confirmAction, element, formatDate, iconButton } from './shared.js';
import { showError, showSuccess } from './toasts.js';

const WEEKDAYS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];
const scheduleState = { rows: [], editingId: null };
const base = `${API.scan}schedules`;
function closeScheduleEditor() {
  scheduleState.editingId = null;
  const form = document.querySelector('#schedule-form');
  form.reset();
  form.hidden = true;
  const dialog = document.querySelector('#schedule-dialog');
  if (dialog.open) dialog.close();
}
async function editSchedule(row = null) {
  if (!document.querySelector('#schedule-form').hidden && !await confirmAction(
    'Сменить расписание', 'Несохраненные изменения открытого расписания будут потеряны.', 'Продолжить',
  )) return;
  scheduleState.editingId = row?.id || null;
  const form = document.querySelector('#schedule-form');
  form.reset();
  form.elements.namedItem('name').value = row?.name || '';
  const [hour, minute] = (row?.time_of_day || '09:00').split(':');
  form.elements.namedItem('hour').value = hour;
  form.elements.namedItem('minute').value = minute;
  form.elements.namedItem('enabled').checked = Boolean(row?.enabled);
  form.querySelectorAll('[name=weekday]').forEach((input) => { input.checked = !row || row.weekdays.includes(Number(input.value)); });
  fillScanOptions(form, row?.options);
  document.querySelector('#schedule-editor-title').textContent = row ? 'Изменить расписание' : 'Новое расписание';
  form.hidden = false;
  const dialog = document.querySelector('#schedule-dialog');
  if (!dialog.open) dialog.showModal();
  form.elements.namedItem('name').focus();
}
function scheduleCard(row) {
  const card = element('article', 'dashboard-card schedule-card');
  card.dataset.scheduleId = row.id;
  const heading = element('div', 'card-heading');
  heading.append(element('p', '', row.name));
  const toggle = element('label', 'switch');
  const enabled = element('input');
  enabled.type = 'checkbox'; enabled.checked = row.enabled;
  enabled.setAttribute('aria-label', `Включить расписание «${row.name}»`);
  toggle.append(enabled, element('span'), document.createTextNode('Включено'));
  heading.append(toggle); card.append(heading);
  const overdue = row.enabled && row.next_run_at && new Date(row.next_run_at).getTime() <= Date.now();
  const stats = element('div', 'compact-list');
  [
    ['Дни и время', `${row.weekdays.map((day) => WEEKDAYS[day]).join(', ')} · ${row.time_of_day.slice(0, 5)}`],
    ['Следующий запуск', !row.enabled ? 'Выключено' : overdue ? 'Ожидает исполнителя' : formatDate(row.next_run_at)],
    ['Последний запуск', formatDate(row.last_run_at)],
  ].forEach(([label, value]) => {
    const line = element('div'); line.append(element('span', '', label), element('b', '', value)); stats.append(line);
  });
  card.append(stats, element('p', 'schedule-scope', scanOptionsText(row.options)));
  const actions = element('div', 'visibility-editor-actions');
  const edit = iconButton('edit', 'secondary-button', 'Изменить расписание');
  edit.addEventListener('click', () => editSchedule(row).catch(showError));
  bindEditorChange(enabled, card, async () => {
    try {
      const updated = await api(`${base}/${row.id}/enabled`, {
        method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ enabled: enabled.checked }),
      });
      scheduleState.rows = scheduleState.rows.map((item) => item.id === row.id ? updated : item);
      if (scheduleState.editingId === row.id) document.querySelector('#schedule-form').elements.namedItem('enabled').checked = updated.enabled;
      card.replaceWith(scheduleCard(updated));
    } catch (error) { enabled.checked = row.enabled; throw error; }
  });
  const remove = iconButton('trash', 'danger-button', 'Удалить расписание');
  bindEditorAction(remove, async () => {
    if (!await confirmAction('Удалить расписание', `«${row.name}» будет удалено. Текущий запуск продолжит работу.`, 'Удалить')) return;
    await api(`${base}/${row.id}`, { method: 'DELETE' });
    scheduleState.rows = scheduleState.rows.filter((item) => item.id !== row.id);
    if (scheduleState.editingId === row.id) closeScheduleEditor();
    card.remove();
    if (!scheduleState.rows.length) renderSchedules();
  }, card);
  const history = iconButton('history', 'secondary-button', 'История запусков');
  history.addEventListener('click', () => window.dispatchEvent(new CustomEvent('radar-schedule-history', { detail: row })));
  actions.append(edit, history, remove);
  card.append(actions);
  return card;
}
function renderSchedules() {
  const list = document.querySelector('#schedule-list');
  list.replaceChildren(...scheduleState.rows.map(scheduleCard));
  if (!scheduleState.rows.length) list.append(element('p', 'empty-state', 'Расписаний нет. Сканирование запускается вручную.'));
}
async function loadSchedules() {
  const rows = await readLatest('scan-schedules', (signal) => api(base, { signal }));
  if (!rows) return;
  scheduleState.rows = rows;
  renderSchedules();
}
function initializeSchedules() {
  const form = document.querySelector('#schedule-form');
  document.querySelector('#schedule-dialog').addEventListener('close', () => {
    form.hidden = true; scheduleState.editingId = null;
  });
  ['hour', 'minute'].forEach((name) => {
    const select = form.elements.namedItem(name);
    const count = name === 'hour' ? 24 : 60;
    for (let value = 0; value < count; value += 1) {
      const text = String(value).padStart(2, '0');
      const option = element('option', '', text); option.value = text;
      option.defaultSelected = value === (name === 'hour' ? 9 : 0);
      select.append(option);
    }
  });
  scanOptionsFields(form.querySelector('.scan-options'));
  const days = form.querySelector('#schedule-weekdays');
  WEEKDAYS.forEach((name, day) => {
    const label = element('label', 'switch');
    const input = element('input');
    input.type = 'checkbox'; input.name = 'weekday'; input.value = day; input.defaultChecked = true;
    label.append(input, element('span'), document.createTextNode(name)); days.append(label);
  });
  document.querySelector('#schedule-create').addEventListener('click', () => editSchedule().catch(showError));
  document.querySelector('#schedule-cancel').addEventListener('click', closeScheduleEditor);
  document.querySelector('#schedule-refresh').addEventListener('click', () => loadSchedules().catch(showError));
  bindEditorForm('#schedule-form', async () => {
    const weekdays = [...form.querySelectorAll('[name=weekday]:checked')].map((input) => Number(input.value));
    if (!weekdays.length) throw new Error('Выберите хотя бы один день недели');
    const payload = {
      name: form.elements.namedItem('name').value.trim(), time_of_day: `${form.elements.namedItem('hour').value}:${form.elements.namedItem('minute').value}`,
      enabled: form.elements.namedItem('enabled').checked, weekdays, options: readScanOptions(form),
    };
    const id = scheduleState.editingId;
    const updated = await api(id ? `${base}/${id}` : base, {
      method: id ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
    });
    const index = scheduleState.rows.findIndex((row) => row.id === updated.id);
    if (index < 0) scheduleState.rows.push(updated); else scheduleState.rows[index] = updated;
    closeScheduleEditor(); renderSchedules(); showSuccess('Расписание сохранено');
  });
}
export { initializeSchedules, loadSchedules };
