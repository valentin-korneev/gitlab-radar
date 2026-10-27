function activeRequirements() { return state.requirements.filter((requirement) => requirement.enabled); }
async function ensureRequirements(includeCatalog = false) {
  const requests = [];
  if (!state.requirements.length) requests.push(api(API.requirements).then((items) => { state.requirements = items; }));
  if (!state.requirementGroups.length) requests.push(api(API.requirementGroups).then((items) => { state.requirementGroups = items; }));
  if (includeCatalog && !state.requirementCatalog) requests.push(api(API.requirementCatalog).then((catalog) => { state.requirementCatalog = catalog; }));
  await Promise.all(requests);
  renderRuleFilters();
}
function renderRuleFilters() {
  const container = document.querySelector('.rule-switches');
  const heading = container.querySelector('.control-label') || element('span', 'control-label', 'Нарушения правил');
  container.replaceChildren(heading);
  const active = activeRequirements();
  const activeCodes = new Set(active.map((requirement) => requirement.code));
  state.projectFilters.rules.forEach((code) => {
    if (!activeCodes.has(code)) state.projectFilters.rules.delete(code);
  });
  const grouped = state.requirementGroups
    .map((group) => active.filter((requirement) => requirement.group_id === group.id))
    .filter((requirements) => requirements.length);
  container.classList.toggle('six-columns', grouped.length > 4);
  grouped.flat().forEach((requirement) => {
    const label = element('label', 'switch');
    const input = element('input');
    input.type = 'checkbox';
    input.dataset.rule = requirement.code;
    input.checked = state.projectFilters.rules.has(requirement.code);
    input.addEventListener('change', () => {
      if (input.checked) state.projectFilters.rules.add(requirement.code);
      else state.projectFilters.rules.delete(requirement.code);
      renderProjects();
    });
    label.append(input, element('span'), document.createTextNode(requirement.title));
    container.append(label);
  });
}

function optionSelect(options, value, className) {
  const select = element('select', className);
  options.forEach((option) => {
    const node = element('option', '', option.title);
    node.value = option.value;
    node.selected = option.value === value;
    select.append(node);
  });
  return select;
}
function conditionLogicSelect(value = 'and') {
  return optionSelect(
    [
      { value: 'and', title: 'И — должны выполняться все' },
      { value: 'or', title: 'ИЛИ — достаточно одного' },
    ],
    value,
    'condition-group-logic',
  );
}
function addRequirementCondition(condition = {}, container = document.querySelector('#requirement-conditions')) {
  const row = element('div', 'requirement-condition');
  const source = optionSelect(state.requirementCatalog.sources, condition.source, 'condition-source');
  const operator = optionSelect(state.requirementCatalog.operators, condition.operator, 'condition-operator');
  const values = element('input', 'condition-values');
  values.required = true;
  values.placeholder = 'Значения через запятую';
  values.value = (condition.values || []).join(', ');
  source.addEventListener('change', () => {
    const defaults = state.requirementCatalog.sources.find((item) => item.value === source.value);
    if (!defaults) return;
    if (defaults.default_operator) operator.value = defaults.default_operator;
    if (!values.value.trim() && defaults.default_values.length) values.value = defaults.default_values.join(', ');
  });
  const emptyLabel = element('label', 'condition-empty');
  const empty = element('input');
  empty.type = 'checkbox';
  empty.className = 'condition-empty-result';
  empty.checked = Boolean(condition.empty_result);
  emptyLabel.append(empty, document.createTextNode(' Если данных нет — требование выполнено'));
  const remove = element('button', 'condition-remove');
  remove.type = 'button';
  remove.title = 'Удалить условие';
  remove.setAttribute('aria-label', 'Удалить условие');
  remove.append(iconElement('close'));
  remove.addEventListener('click', () => {
    if (container.children.length > 1) row.remove();
  });
  row.append(source, operator, values, emptyLabel, remove);
  container.append(row);
}
function addRequirementConditionGroup(group = {}, container = document.querySelector('#requirement-conditions')) {
  const node = element('section', 'condition-group');
  const heading = element('div', 'condition-group-heading');
  const logic = conditionLogicSelect(group.logic || 'and');
  logic.setAttribute('aria-label', 'Логика группы условий');
  const logicField = element('label', 'condition-group-logic-field');
  logicField.append(document.createTextNode('Как объединять условия'), logic);
  const actions = element('div', 'condition-group-actions');
  const addCondition = iconButton('plus', 'secondary-button', 'Добавить условие в группу');
  const addGroup = iconButton('group', 'secondary-button', 'Добавить вложенную группу');
  const remove = iconButton('trash', 'danger-button', 'Удалить группу условий');
  const items = element('div', 'condition-group-items');
  addCondition.addEventListener('click', () => addRequirementCondition({}, items));
  addGroup.addEventListener('click', () => addRequirementConditionGroup({}, items));
  remove.addEventListener('click', () => {
    if (container.children.length > 1) node.remove();
  });
  actions.append(addCondition, addGroup, remove);
  heading.append(element('strong', '', 'Группа условий'), actions);
  node.append(heading, logicField, items);
  (group.items || [{}]).forEach((condition) => addRequirementConditionNode(condition, items));
  container.append(node);
}
function addRequirementConditionNode(node, container = document.querySelector('#requirement-conditions')) {
  if (node && Array.isArray(node.items)) addRequirementConditionGroup(node, container);
  else addRequirementCondition(node || {}, container);
}
function conditionNodePayload(node) {
  if (node.classList.contains('condition-group')) {
    const items = node.querySelector(':scope > .condition-group-items');
    return {
      logic: node.querySelector(':scope > .condition-group-logic-field .condition-group-logic').value,
      items: [...items.children].map(conditionNodePayload),
    };
  }
  return {
    source: node.querySelector('.condition-source').value,
    operator: node.querySelector('.condition-operator').value,
    values: node.querySelector('.condition-values').value.split(',').map((value) => value.trim()).filter(Boolean),
    empty_result: node.querySelector('.condition-empty-result').checked,
  };
}
function countConditionNodes(nodes) {
  return nodes.reduce((count, node) => count + (
    Array.isArray(node.items) ? countConditionNodes(node.items) : 1
  ), 0);
}
function requirementPayload() {
  const requirementId = Number(document.querySelector('#requirement-id').value);
  const current = state.requirements.find((requirement) => requirement.id === requirementId);
  return {
    code: document.querySelector('#requirement-code').value.trim(),
    title: document.querySelector('#requirement-title').value.trim(),
    group_id: current?.group_id || state.selectedRequirementGroupId,
    description: document.querySelector('#requirement-description').value.trim(),
    enabled: current?.enabled ?? true,
    sort_order: current?.sort_order || (
      state.requirements.filter((requirement) => requirement.group_id === state.selectedRequirementGroupId).length + 1
    ) * 10,
    condition: {
      logic: document.querySelector('#requirement-condition-logic').value,
      items: [...document.querySelector('#requirement-conditions').children].map(conditionNodePayload),
    },
  };
}
function resetRequirementForm() {
  document.querySelector('#requirement-form').reset();
  document.querySelector('#requirement-id').value = '';
  document.querySelector('#requirement-conditions').replaceChildren();
  addRequirementCondition();
  document.querySelector('#requirement-dialog-title').textContent = 'Новое требование';
}
function editRequirement(requirement) {
  document.querySelector('#requirement-id').value = requirement.id;
  document.querySelector('#requirement-title').value = requirement.title;
  document.querySelector('#requirement-code').value = requirement.code;
  document.querySelector('#requirement-description').value = requirement.description;
  document.querySelector('#requirement-condition-logic').value = requirement.condition.logic;
  document.querySelector('#requirement-conditions').replaceChildren();
  requirement.condition.items.forEach((condition) => addRequirementConditionNode(condition));
  document.querySelector('#requirement-dialog-title').textContent = 'Редактирование требования';
  document.querySelector('#requirement-dialog').showModal();
  document.querySelector('#requirement-title').focus();
}
async function removeRequirement(requirement) {
  const confirmed = await confirmAction(
    'Удалить требование?',
    `Требование «${requirement.title}» будет удалено без возможности восстановления.`,
    'Удалить требование',
  );
  if (!confirmed) return;
  await api(`${API.requirements}${requirement.id}`, { method: 'DELETE' });
  await reloadRequirements();
  showSuccess('Требование удалено');
}
function groupPayload() {
  const groupId = Number(document.querySelector('#requirement-group-id').value);
  const current = state.requirementGroups.find((group) => group.id === groupId);
  return {
    name: document.querySelector('#requirement-group-name').value.trim(),
    description: document.querySelector('#requirement-group-description').value.trim(),
    sort_order: current?.sort_order || (state.requirementGroups.length + 1) * 10,
  };
}
function resetGroupForm() {
  document.querySelector('#requirement-group-form').reset();
  document.querySelector('#requirement-group-id').value = '';
  document.querySelector('#group-dialog-title').textContent = 'Новая группа';
}
function editRequirementGroup(group) {
  document.querySelector('#requirement-group-id').value = group.id;
  document.querySelector('#requirement-group-name').value = group.name;
  document.querySelector('#requirement-group-description').value = group.description;
  document.querySelector('#group-dialog-title').textContent = 'Редактирование группы';
  document.querySelector('#group-dialog').showModal();
  document.querySelector('#requirement-group-name').focus();
}
async function removeRequirementGroup(group) {
  const confirmed = await confirmAction(
    'Удалить группу?',
    `Группа «${group.name}» будет удалена без возможности восстановления.`,
    'Удалить группу',
  );
  if (!confirmed) return;
  await api(`${API.requirementGroups}${group.id}`, { method: 'DELETE' });
  if (state.selectedRequirementGroupId === group.id) state.selectedRequirementGroupId = null;
  await reloadRequirements();
  showSuccess('Группа удалена');
}
function renderRequirementGroups() {
  const container = document.querySelector('#requirement-groups');
  if (!container) return;
  document.querySelector('#requirements-count').textContent = state.requirementGroups.length;
  container.replaceChildren();
  state.requirementGroups.forEach((group) => {
    const node = element(
      'button',
      `requirement-group-list-item${group.id === state.selectedRequirementGroupId ? ' active' : ''}`,
    );
    node.type = 'button';
    node.dataset.groupId = group.id;
    node.title = `Открыть группу «${group.name}»`;
    const handle = element('span', 'group-drag-handle', '⋮⋮');
    handle.draggable = true;
    handle.title = 'Перетащить группу';
    handle.addEventListener('click', (event) => event.stopPropagation());
    const summary = element('div');
    const groupRequirements = state.requirements.filter((requirement) => requirement.group_id === group.id);
    summary.append(
      element('strong', '', group.name),
      element('small', '', `${groupRequirements.length} из 6`),
    );
    node.append(handle, summary, element('span', 'group-open-mark', '›'));
    node.addEventListener('click', () => {
      state.selectedRequirementGroupId = group.id;
      renderRequirementGroups();
    });
    container.append(node);
  });
  if (!state.requirementGroups.length) container.append(element('p', 'empty-state', 'Сначала создайте группу.'));
  renderRequirementGroupDetail();
}
function renderRequirementGroupDetail() {
  const detail = document.querySelector('#requirement-group-detail');
  const group = state.requirementGroups.find((item) => item.id === state.selectedRequirementGroupId);
  detail.replaceChildren();
  delete detail.dataset.groupId;
  if (!group) {
    detail.append(element('p', 'empty-state', 'Выберите группу, чтобы посмотреть требования.'));
    return;
  }
  detail.dataset.groupId = group.id;
  const heading = element('div', 'requirement-detail-heading');
  const identity = element('div');
  identity.append(element('h3', '', group.name));
  if (group.description) identity.append(element('p', 'muted', group.description));
  const groupRequirements = state.requirements.filter((requirement) => requirement.group_id === group.id);
  const actions = element('div', 'admin-requirement-actions');
  const edit = iconButton('edit', 'secondary-button', 'Изменить группу');
  edit.addEventListener('click', () => editRequirementGroup(group));
  const add = iconButton('plus', 'primary-button', 'Добавить требование');
  add.disabled = groupRequirements.length >= 6;
  add.addEventListener('click', () => {
    resetRequirementForm();
    document.querySelector('#requirement-dialog').showModal();
  });
  const remove = iconButton('trash', 'danger-button', 'Удалить группу');
  remove.addEventListener('click', () => removeRequirementGroup(group).catch(showError));
  actions.append(edit, add, remove);
  heading.append(identity, actions);
  const requirements = element('div', 'requirement-detail-items');
  groupRequirements.forEach((requirement) => requirements.append(requirementTreeItem(requirement)));
  if (!groupRequirements.length) requirements.append(element('p', 'empty-state', 'В группе пока нет требований.'));
  detail.append(heading, requirements);
}
function requirementTreeItem(requirement) {
  const item = element('div', `requirement-tree-item${requirement.enabled ? '' : ' disabled'}`);
  item.dataset.requirementId = requirement.id;
  const handle = element('span', 'requirement-drag-handle', '⋮⋮');
  handle.draggable = true;
  handle.title = 'Перетащить требование';
  const summary = element('div', 'requirement-tree-summary');
  summary.append(
    element('strong', '', requirement.title),
    element('small', '', `${requirement.code} · условий: ${countConditionNodes(requirement.condition.items)}`),
  );
  const enabled = element('label', 'switch requirement-enabled-switch');
  const input = element('input');
  input.type = 'checkbox';
  input.checked = requirement.enabled;
  input.addEventListener('change', async () => {
    try { await setRequirementEnabled(requirement, input.checked); } catch (error) {
      input.checked = requirement.enabled;
      showError(error);
    }
  });
  enabled.append(input, element('span'));
  enabled.title = requirement.enabled ? 'Требование включено' : 'Требование выключено';
  const actions = element('div', 'admin-requirement-actions');
  const edit = iconButton('edit', 'secondary-button', 'Изменить требование');
  edit.addEventListener('click', () => editRequirement(requirement));
  const move = iconButton('move', 'secondary-button', 'Сменить группу');
  move.disabled = !state.requirementGroups.some((group) => (
    group.id !== requirement.group_id
    && state.requirements.filter((item) => item.group_id === group.id).length < 6
  ));
  move.addEventListener('click', () => openRequirementMove(requirement));
  const remove = iconButton('trash', 'danger-button', 'Удалить требование');
  remove.addEventListener('click', () => removeRequirement(requirement).catch(showError));
  actions.append(edit, move, remove);
  item.append(handle, summary, enabled, actions);
  return item;
}
async function setRequirementEnabled(requirement, enabled) {
  const updated = await api(`${API.requirements}${requirement.id}/enabled`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled }),
  });
  state.requirements = state.requirements.map((item) => item.id === updated.id ? updated : item);
  state.loaded.dashboard = false;
  state.loaded.projects = false;
  renderRuleFilters();
  renderRequirementGroups();
  showSuccess(enabled ? 'Требование включено' : 'Требование выключено');
}
function openRequirementMove(requirement) {
  document.querySelector('#move-requirement-id').value = requirement.id;
  document.querySelector('#move-requirement-title').textContent = requirement.title;
  const select = document.querySelector('#move-requirement-group');
  select.replaceChildren();
  state.requirementGroups
    .filter((group) => (
      group.id !== requirement.group_id
      && state.requirements.filter((item) => item.group_id === group.id).length < 6
    ))
    .forEach((group) => {
      const option = element('option', '', group.name);
      option.value = group.id;
      select.append(option);
    });
  document.querySelector('#move-requirement-dialog').showModal();
}
async function moveRequirement(requirementId, groupId) {
  await api(`${API.requirements}${requirementId}/group`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ group_id: groupId }),
  });
  state.requirements = await api(API.requirements);
  state.loaded.dashboard = false;
  state.loaded.projects = false;
  renderRuleFilters();
  renderRequirementGroups();
  showSuccess('Требование перенесено');
}
async function saveRequirementGroupOrder() {
  const groupIds = [...document.querySelectorAll('#requirement-groups [data-group-id]')]
    .map((item) => Number(item.dataset.groupId));
  state.requirementGroups = await api(`${API.requirementGroups}order`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ group_ids: groupIds }),
  });
  state.loaded.dashboard = false;
  renderRequirementGroups();
  showSuccess('Порядок групп сохранён');
}
async function saveRequirementOrder(groupNode) {
  const requirementIds = [...groupNode.querySelectorAll('[data-requirement-id]')]
    .map((item) => Number(item.dataset.requirementId));
  state.requirements = await api(`${API.requirements}order`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ group_id: Number(groupNode.dataset.groupId), requirement_ids: requirementIds }),
  });
  state.loaded.dashboard = false;
  renderRequirementGroups();
  showSuccess('Порядок требований сохранён');
}
async function reloadRequirements() {
  [state.requirements, state.requirementGroups] = await Promise.all([
    api(API.requirements), api(API.requirementGroups),
  ]);
  if (!state.requirementGroups.some((group) => group.id === state.selectedRequirementGroupId)) {
    state.selectedRequirementGroupId = null;
  }
  state.loaded.dashboard = false;
  state.loaded.projects = false;
  state.loaded.requirements = false;
  renderRuleFilters();
  renderRequirementGroups();
  resetRequirementForm();
  resetGroupForm();
}

async function loadRequirementsPage() {
  await ensureRequirements(true);
  renderRequirementGroups();
  if (!document.querySelector('.requirement-condition')) addRequirementCondition();
  state.loaded.requirements = true;
}
