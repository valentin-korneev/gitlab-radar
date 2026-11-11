function blacklistRuleRow(rule) {
  const row = element('div', 'blacklist-rule-row');
  const input = element('input');
  input.value = rule.pattern;
  input.maxLength = 500;
  input.required = true;
  input.readOnly = true;
  input.setAttribute('aria-label', 'Путь или шаблон проекта');
  const save = async () => {
    const pattern = input.value.trim();
    if (!pattern || pattern === rule.pattern) {
      input.value = rule.pattern;
      input.readOnly = true;
      return;
    }
    input.disabled = true;
    try {
      const updated = await api(`${API.projectBlacklist}${rule.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pattern }),
      });
      Object.assign(rule, updated);
      input.value = rule.pattern;
      input.readOnly = true;
      showSuccess('Правило сохранено');
    } catch (error) {
      input.value = rule.pattern;
      showError(error);
    } finally {
      input.disabled = false;
    }
  };
  input.addEventListener('change', save);
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
      renderProjectBlacklist();
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
  renderProjectBlacklist();
  showSuccess('Правило добавлено');
}

async function loadProjectBlacklist() {
  state.blacklistRules = await api(API.projectBlacklist);
  renderProjectBlacklist();
  state.loaded.blacklist = true;
}
