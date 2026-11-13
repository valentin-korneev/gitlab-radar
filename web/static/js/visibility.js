import { api } from './api.js';
import { API } from './config.js';
import { bindEditorAction } from './editors.js';
import { invalidateReads, readLatest } from './requests.js';
import { pageEdit } from './page-updates.js';
import { showError, showSuccess } from './toasts.js';
import { canonicalLanguageCode, confirmAction, element, iconButton, languageDisplayName } from './shared.js';
import { catalogPages, catalogState, projectState, state } from './state.js';

function visibilityRuleRow(rule = { action: 'include', target: 'path', pattern: '' }) {
  const row = element('div', 'visibility-rule-row');
  const action = document.createElement('select');
  action.className = 'visibility-rule-action';
  action.innerHTML = '<option value="include">Включить</option><option value="exclude">Исключить</option>';
  action.value = rule.action;
  const target = document.createElement('select');
  target.className = 'visibility-rule-target';
  target.innerHTML = '<option value="path">Путь проекта</option><option value="language">Язык</option>';
  target.value = rule.target || 'path';
  const createPatternControl = (value = '') => {
    if (target.value === 'language') {
      const select = document.createElement('select');
      select.className = 'visibility-rule-pattern';
      select.required = true;
      select.append(new Option('Выберите язык', ''));
      const languages = new Map();
      state.programmingLanguages.forEach((language) => {
        const code = canonicalLanguageCode(language.code);
        if (!languages.has(code)) languages.set(code, languageDisplayName(code, language.name));
      });
      languages.forEach((name, code) => select.add(new Option(name, code)));
      const selectedCode = canonicalLanguageCode(value);
      if (value && !languages.has(selectedCode)) {
        select.add(new Option(value, value));
      }
      select.value = selectedCode;
      return select;
    }
    const input = document.createElement('input');
    input.className = 'visibility-rule-pattern';
    input.required = true;
    input.maxLength = 500;
    input.placeholder = 'mlops/*';
    input.value = value;
    return input;
  };
  let pattern = createPatternControl(rule.pattern);
  target.addEventListener('change', () => {
    const replacement = createPatternControl();
    pattern.replaceWith(replacement);
    pattern = replacement;
  });
  const remove = iconButton('trash', 'danger-button', 'Удалить правило');
  remove.addEventListener('click', () => row.remove());
  row.append(action, target, pattern, remove);
  return row;
}

function appendVisibilityRule(container, rule) {
  container.append(visibilityRuleRow(rule));
}

function visibilityRulesPayload(container) {
  return [...container.querySelectorAll('.visibility-rule-row')].map((row) => ({
    action: row.querySelector('.visibility-rule-action').value,
    target: row.querySelector('.visibility-rule-target').value,
    pattern: row.querySelector('.visibility-rule-pattern').value.trim(),
  })).filter((rule) => rule.pattern);
}

function visibilityEditorCard(item, kind) {
  const card = element('article', 'dashboard-card visibility-editor-card');
  card.dataset.visibilityKind = kind;
  card.dataset.visibilityId = item.id || '';
  const fields = element('div', 'visibility-editor-fields');
  const nameLabel = element('label', 'visibility-field', 'Название');
  const name = document.createElement('input');
  name.required = true;
  name.maxLength = 100;
  name.value = item.name || '';
  nameLabel.append(name);
  fields.append(nameLabel);
  const rules = element('div', 'visibility-rules');
  (item.rules || []).forEach((rule) => appendVisibilityRule(rules, rule));
  const actions = element('div', 'visibility-editor-actions');
  const add = iconButton('plus', 'secondary-button', 'Добавить правило');
  add.addEventListener('click', () => appendVisibilityRule(rules));
  const save = iconButton('check', 'primary-button', 'Сохранить');
  bindEditorAction(save, async () => {
    try {
      if (!name.value.trim()) {
        name.focus();
        return;
      }
      const path = kind === 'policy'
        ? `${API.visibilityAdmin}policy${item.id ? `/${item.id}` : ''}`
        : `${API.visibility}${item.id || ''}`;
      const updated = await api(path, {
        method: item.id ? 'PUT' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: name.value.trim(),
          rules: visibilityRulesPayload(rules),
        }),
      });
      const key = kind === 'policy' ? 'visibilityPolicies' : 'visibilityGroups';
      const index = state[key].findIndex((entry) => entry.id === updated.id);
      if (index < 0) state[key].push(updated);
      else state[key][index] = updated;
      card.replaceWith(visibilityEditorCard(updated, kind));
      renderVisibilitySwitcher();
      invalidateVisibilityData();
      showSuccess(kind === 'policy' ? 'Политика сохранена' : 'Группа фильтров сохранена');
    } catch (error) { showError(error); }
  }, card);
  actions.append(add, save);
  if (kind === 'group' && item.id) {
    const defaultButton = iconButton(
      'star',
      item.is_default ? 'primary-button' : 'secondary-button',
      item.is_default ? 'Снять фильтр по умолчанию' : 'Сделать фильтром по умолчанию',
    );
    defaultButton.dataset.visibilityDefault = '';
    bindEditorAction(defaultButton, async () => {
      try {
        const current = state.visibilityGroups.find((group) => group.id === item.id);
        const groupId = current?.is_default ? null : item.id;
        await api(`${API.visibility}default`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ group_id: groupId }),
        });
        state.selectedVisibilityGroup = groupId === null ? 'all' : String(groupId);
        state.visibilityGroups.forEach((group) => { group.is_default = group.id === groupId; });
        document.querySelectorAll('[data-visibility-kind="group"]').forEach((entry) => {
          const button = entry.querySelector('[data-visibility-default]');
          if (!button) return;
          const selected = Number(entry.dataset.visibilityId) === groupId;
          button.classList.toggle('primary-button', selected);
          button.classList.toggle('secondary-button', !selected);
          button.title = selected ? 'Снять фильтр по умолчанию' : 'Сделать фильтром по умолчанию';
          button.setAttribute('aria-label', button.title);
        });
        renderVisibilitySwitcher();
        invalidateVisibilityData();
        showSuccess(groupId === null ? 'Фильтр по умолчанию снят' : 'Фильтр по умолчанию сохранен');
      } catch (error) { showError(error); }
    }, card);
    actions.append(defaultButton);
  }
  if (item.id) {
    const remove = iconButton('trash', 'danger-button', kind === 'policy' ? 'Удалить политику' : 'Удалить группу');
    bindEditorAction(remove, async () => {
      try {
        const title = kind === 'policy' ? 'Удалить политику' : 'Удалить группу';
        if (!await confirmAction(title, `«${item.name}» будет удалена.`, title)) return;
        const base = kind === 'policy' ? `${API.visibilityAdmin}policy/` : API.visibility;
        await api(`${base}${item.id}`, { method: 'DELETE' });
        const key = kind === 'policy' ? 'visibilityPolicies' : 'visibilityGroups';
        state[key] = state[key].filter((entry) => entry.id !== item.id);
        card.remove();
        if (kind === 'group' && state.selectedVisibilityGroup === String(item.id)) state.selectedVisibilityGroup = 'all';
        renderVisibilitySwitcher();
        invalidateVisibilityData();
        showSuccess(kind === 'policy' ? 'Политика удалена' : 'Группа фильтров удалена');
      } catch (error) { showError(error); }
    }, card);
    actions.append(remove);
  }
  card.append(fields, rules, actions);
  return card;
}

function renderVisibilityGroups() {
  const list = document.querySelector('#visibility-group-list');
  list.replaceChildren();
  if (!state.visibilityGroups.length) {
    list.append(element('p', 'empty-state', 'Групп пока нет. В режиме «Все*» действуют только ограничения администратора.'));
    return;
  }
  state.visibilityGroups.forEach((group) => list.append(visibilityEditorCard(group, 'group')));
}

function renderVisibilitySwitcher() {
  const wrapper = document.querySelector('#visibility-switcher');
  const select = document.querySelector('#active-visibility-group');
  const visible = Boolean(state.auth.user && state.visibilityGroups.length);
  wrapper.hidden = !visible;
  if (!visible) return;
  select.replaceChildren(new Option('Все*', 'all'));
  state.visibilityGroups.forEach((group) => select.add(new Option(group.name, String(group.id))));
  select.value = String(state.selectedVisibilityGroup || 'all');
}

async function loadVisibilityGroups() {
  if (!state.auth.user) {
    state.visibilityGroups = [];
    renderVisibilitySwitcher();
    return;
  }
  const groups = await readLatest('visibility-groups', (signal) => api(API.visibility, { signal }));
  if (!groups) return;
  state.visibilityGroups = groups;
  const selectedExists = state.selectedVisibilityGroup === 'all' || state.visibilityGroups.some(
    (group) => String(group.id) === String(state.selectedVisibilityGroup)
  );
  if (!selectedExists) {
    state.selectedVisibilityGroup = String(state.visibilityGroups.find((group) => group.is_default)?.id || 'all');
  }
  renderVisibilitySwitcher();
  return true;
}

async function reloadVisibilityGroups() {
  const loaded = await loadVisibilityGroups();
  if (!loaded || pageEdit('visibility').dirty || pageEdit('visibility').stale) return;
  renderVisibilityGroups();
  state.loaded.visibility = true;
}

async function loadVisibilityPage() {
  await ensureVisibilityProgrammingLanguages();
  await reloadVisibilityGroups();
}

function renderVisibilityPolicies() {
  const list = document.querySelector('#visibility-policy-list');
  list.replaceChildren();
  if (!state.visibilityPolicies.length) list.append(element('p', 'empty-state', 'Политики пока не созданы.'));
  state.visibilityPolicies.forEach((policy) => list.append(visibilityEditorCard(policy, 'policy')));
}

async function reloadVisibilityPolicies() {
  const policies = await readLatest('visibility-policies', (signal) => api(`${API.visibilityAdmin}policy`, { signal }));
  if (!policies) return;
  state.visibilityPolicies = policies;
  renderVisibilityPolicies();
}

async function openAdminUserVisibility(preferredUsername) {
  state.visibilityAdminUser = preferredUsername;
  await ensureVisibilityProgrammingLanguages();
  const policies = await readLatest('visibility-policies', (signal) => api(`${API.visibilityAdmin}policy`, { signal }));
  if (!policies) return;
  state.visibilityPolicies = policies;
  document.querySelector('#visibility-user-dialog-name').textContent = preferredUsername;
  const rendered = await renderAdminUserVisibility(preferredUsername);
  if (!rendered || preferredUsername !== state.visibilityAdminUser) return;
  const dialog = document.querySelector('#visibility-user-dialog');
  if (!dialog.open) dialog.showModal();
}

async function renderAdminUserVisibility(preferredUsername) {
  const editor = document.querySelector('#visibility-admin-user-editor');
  editor.replaceChildren();
  if (!preferredUsername) {
    editor.append(element('p', 'empty-state', 'Добавьте пользователя, чтобы настроить видимость.'));
    return;
  }
  const config = await readLatest('visibility-user', (signal) => api(`${API.visibilityAdmin}user/${encodeURIComponent(preferredUsername)}`, { signal }));
  if (!config || preferredUsername !== state.visibilityAdminUser) return;
  const policies = element('div', 'visibility-policy-assignments');
  policies.append(element('strong', '', 'Назначенные политики'));
  state.visibilityPolicies.forEach((policy) => {
    const label = element('label', 'visibility-policy-option');
    const input = document.createElement('input');
    input.type = 'checkbox';
    input.value = policy.id;
    input.checked = config.policy_ids.includes(policy.id);
    label.append(input, document.createTextNode(policy.name));
    policies.append(label);
  });
  const rules = element('div', 'visibility-rules');
  config.rules.forEach((rule) => appendVisibilityRule(rules, rule));
  const add = iconButton('plus', 'secondary-button', 'Добавить индивидуальное правило');
  add.addEventListener('click', () => appendVisibilityRule(rules));
  const save = iconButton('check', 'primary-button', 'Сохранить настройки пользователя');
  bindEditorAction(save, async () => {
    try {
      save.disabled = true;
      await api(`${API.visibilityAdmin}user/${encodeURIComponent(preferredUsername)}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          policy_ids: [...policies.querySelectorAll('input:checked')].map((input) => Number(input.value)),
          rules: visibilityRulesPayload(rules),
        }),
      });
      invalidateVisibilityData();
      document.querySelector('#visibility-user-dialog').close();
      showSuccess('Настройки пользователя сохранены');
    } catch (error) {
      showError(error);
    } finally {
      save.disabled = false;
    }
  });
  const actions = element('div', 'visibility-editor-actions');
  actions.append(add, save);
  editor.append(
    policies,
    element('h3', 'visibility-subheading', 'Индивидуальные правила администратора'),
    rules,
    actions,
  );
  return true;
}

async function loadAdminVisibilityPage() {
  await ensureVisibilityProgrammingLanguages();
  const policies = await readLatest('visibility-policies', (signal) => api(`${API.visibilityAdmin}policy`, { signal }));
  if (!policies) return;
  if (pageEdit('visibility-admin').dirty || pageEdit('visibility-admin').stale) return;
  state.visibilityPolicies = policies;
  renderVisibilityPolicies();
  state.loaded['visibility-admin'] = true;
}

async function ensureVisibilityProgrammingLanguages() {
  if (!state.programmingLanguages.length) {
    state.programmingLanguages = await api(API.programmingLanguages);
  }
}

function invalidateVisibilityData() {
  invalidateReads();
  ['dashboard', 'projects', 'dependencies'].forEach((page) => { state.loaded[page] = false; });
  projectState.projects = [];
  catalogPages.forEach((page) => { page.dependencies = []; page.selectedDependency = null; });
  state.dependencyCache = {};
  projectState.selectedId = null;
  catalogState.selectedDependency = null;
}

export { invalidateVisibilityData, loadAdminVisibilityPage, loadVisibilityGroups, loadVisibilityPage, openAdminUserVisibility, visibilityEditorCard };
