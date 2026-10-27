function visibilityRuleRow(rule = { action: 'include', pattern: '' }) {
  const row = element('div', 'visibility-rule-row');
  const action = document.createElement('select');
  action.innerHTML = '<option value="include">Включить</option><option value="exclude">Исключить</option>';
  action.value = rule.action;
  const pattern = document.createElement('input');
  pattern.required = true;
  pattern.maxLength = 500;
  pattern.placeholder = 'mlops/*';
  pattern.value = rule.pattern;
  const remove = iconButton('trash', 'danger-button', 'Удалить правило');
  remove.addEventListener('click', () => row.remove());
  row.append(action, pattern, remove);
  return row;
}

function appendVisibilityRule(container, rule) {
  container.append(visibilityRuleRow(rule));
}

function visibilityRulesPayload(container) {
  return [...container.querySelectorAll('.visibility-rule-row')].map((row) => ({
    action: row.querySelector('select').value,
    pattern: row.querySelector('input').value.trim(),
  })).filter((rule) => rule.pattern);
}

function visibilityEditorCard(item, kind) {
  const card = element('article', 'dashboard-card visibility-editor-card');
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
  save.addEventListener('click', async () => {
    try {
      if (!name.value.trim()) {
        name.focus();
        return;
      }
      const path = kind === 'policy'
        ? `${API.visibilityAdmin}policy${item.id ? `/${item.id}` : ''}`
        : `${API.visibility}${item.id || ''}`;
      await api(path, {
        method: item.id ? 'PUT' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: name.value.trim(),
          rules: visibilityRulesPayload(rules),
        }),
      });
      if (kind === 'policy') await reloadVisibilityPolicies();
      else await reloadVisibilityGroups();
      invalidateVisibilityData();
      showSuccess(kind === 'policy' ? 'Политика сохранена' : 'Группа фильтров сохранена');
    } catch (error) { showError(error); }
  });
  actions.append(add, save);
  if (kind === 'group' && item.id) {
    const defaultButton = iconButton(
      'star',
      item.is_default ? 'primary-button' : 'secondary-button',
      item.is_default ? 'Снять фильтр по умолчанию' : 'Сделать фильтром по умолчанию',
    );
    defaultButton.addEventListener('click', async () => {
      try {
        const groupId = item.is_default ? null : item.id;
        await api(`${API.visibility}default`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ group_id: groupId }),
        });
        state.selectedVisibilityGroup = groupId === null ? 'all' : String(groupId);
        await reloadVisibilityGroups();
        invalidateVisibilityData();
        await showPage();
        showSuccess(groupId === null ? 'Фильтр по умолчанию снят' : 'Фильтр по умолчанию сохранён');
      } catch (error) { showError(error); }
    });
    actions.append(defaultButton);
  }
  if (item.id) {
    const remove = iconButton('trash', 'danger-button', kind === 'policy' ? 'Удалить политику' : 'Удалить группу');
    remove.addEventListener('click', async () => {
      try {
        const title = kind === 'policy' ? 'Удалить политику' : 'Удалить группу';
        if (!await confirmAction(title, `«${item.name}» будет удалена.`, title)) return;
        const base = kind === 'policy' ? `${API.visibilityAdmin}policy/` : API.visibility;
        await api(`${base}${item.id}`, { method: 'DELETE' });
        if (kind === 'policy') await reloadVisibilityPolicies();
        else await reloadVisibilityGroups();
        invalidateVisibilityData();
        showSuccess(kind === 'policy' ? 'Политика удалена' : 'Группа фильтров удалена');
      } catch (error) { showError(error); }
    });
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
  state.visibilityGroups = await api(API.visibility);
  const selectedExists = state.selectedVisibilityGroup === 'all' || state.visibilityGroups.some(
    (group) => String(group.id) === String(state.selectedVisibilityGroup)
  );
  if (!selectedExists) {
    state.selectedVisibilityGroup = String(state.visibilityGroups.find((group) => group.is_default)?.id || 'all');
  }
  renderVisibilitySwitcher();
}

async function reloadVisibilityGroups() {
  await loadVisibilityGroups();
  renderVisibilityGroups();
  state.loaded.visibility = true;
}

async function loadVisibilityPage() {
  await reloadVisibilityGroups();
}

function renderVisibilityPolicies() {
  const list = document.querySelector('#visibility-policy-list');
  list.replaceChildren();
  if (!state.visibilityPolicies.length) list.append(element('p', 'empty-state', 'Политики пока не созданы.'));
  state.visibilityPolicies.forEach((policy) => list.append(visibilityEditorCard(policy, 'policy')));
}

async function reloadVisibilityPolicies() {
  state.visibilityPolicies = await api(`${API.visibilityAdmin}policy`);
  renderVisibilityPolicies();
}

async function openAdminUserVisibility(preferredUsername) {
  state.visibilityAdminUser = preferredUsername;
  state.visibilityPolicies = await api(`${API.visibilityAdmin}policy`);
  document.querySelector('#visibility-user-dialog-name').textContent = preferredUsername;
  await renderAdminUserVisibility(preferredUsername);
  document.querySelector('#visibility-user-dialog').showModal();
}

async function renderAdminUserVisibility(preferredUsername) {
  const editor = document.querySelector('#visibility-admin-user-editor');
  editor.replaceChildren();
  if (!preferredUsername) {
    editor.append(element('p', 'empty-state', 'Добавьте пользователя, чтобы настроить видимость.'));
    return;
  }
  const config = await api(`${API.visibilityAdmin}user/${encodeURIComponent(preferredUsername)}`);
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
  save.addEventListener('click', async () => {
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
}

async function loadAdminVisibilityPage() {
  state.visibilityPolicies = await api(`${API.visibilityAdmin}policy`);
  renderVisibilityPolicies();
  state.loaded['visibility-admin'] = true;
}

function invalidateVisibilityData() {
  ['dashboard', 'projects', 'dependencies'].forEach((page) => { state.loaded[page] = false; });
  state.projects = [];
  state.dependencies = [];
  state.dependencyCache = {};
  state.selectedId = null;
  state.selectedDependency = null;
}
