import { pageEdit } from './page-updates.js';
import { api } from './api.js';
import { API } from './config.js';
import { bindAsyncInput } from './editors.js';
import { readLatest } from './requests.js';
import { showError, showSuccess } from './toasts.js';
import { element, iconButton } from './shared.js';
import { state } from './state.js';

function blacklistRuleRow(rule) {
  const row = element('div', 'blacklist-rule-row');
  const input = element('input');
  input.value = rule.pattern;
  input.maxLength = 500;
  input.required = true;
  input.readOnly = true;
  input.setAttribute('aria-label', 'Путь или шаблон проекта');
  bindAsyncInput(input, {
    scope: row,
    read: () => rule.pattern,
    save: (pattern) => {
      if (!pattern) throw new Error('Введите путь или шаблон проекта');
      return api(`${API.projectBlacklist}${rule.id}`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ pattern }),
      });
    },
    onSaved: (updated) => { Object.assign(rule, updated); input.readOnly = true; },
    success: 'Правило сохранено',
  });
  input.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
      event.preventDefault();
      input.blur();
    }
    if (event.key === 'Escape') {
      input.value = rule.pattern;
      input.readOnly = true;
      input.blur();
    }
  });
  const edit = iconButton('edit', 'secondary-button', 'Редактировать правило');
  edit.addEventListener('click', () => {
    input.readOnly = false;
    input.focus();
    input.select();
  });
  const remove = iconButton('trash', 'danger-button', 'Удалить правило');
  remove.addEventListener('click', async () => {
    try {
      await api(`${API.projectBlacklist}${rule.id}`, { method: 'DELETE' });
      state.blacklistRules = state.blacklistRules.filter((item) => item.id !== rule.id);
      row.remove();
      if (!state.blacklistRules.length) renderProjectBlacklist();
      showSuccess('Правило удалено');
    } catch (error) { showError(error); }
  });
  row.append(input, edit, remove);
  return row;
}

function renderProjectBlacklist() {
  const list = document.querySelector('#blacklist-rules');
  list.replaceChildren(...state.blacklistRules.map(blacklistRuleRow));
  if (!state.blacklistRules.length) {
    list.append(element('p', 'empty-state', 'Черный список пуст.'));
  }
}

async function addProjectBlacklistRule() {
  const input = document.querySelector('#blacklist-pattern');
  const pattern = input.value.trim();
  if (!pattern) return;
  const rule = await api(API.projectBlacklist, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pattern }),
  });
  state.blacklistRules.push(rule);
  input.value = '';
  const list = document.querySelector('#blacklist-rules');
  list.querySelector('.empty-state')?.remove();
  list.append(blacklistRuleRow(rule));
  showSuccess('Правило добавлено');
}

async function loadProjectBlacklist() {
  const result = await readLatest('blacklist', (signal) => api(API.projectBlacklist, { signal }));
  if (!result || pageEdit('blacklist').dirty) return;
  state.blacklistRules = result;
  renderProjectBlacklist();
  state.loaded.blacklist = true;
}

export { addProjectBlacklistRule, loadProjectBlacklist };
