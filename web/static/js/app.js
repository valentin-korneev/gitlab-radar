document.querySelectorAll('.nav-item').forEach((item) => {
  item.addEventListener('click', () => {
    if (item.dataset.route === 'projects' && state.currentRoute === 'projects') {
      resetProjectFilters();
      return;
    }
    if (PAGE_ROUTES[state.currentRoute]?.source && item.dataset.route === state.currentRoute) {
      resetDependencyPage();
      renderDependencies();
      return;
    }
    window.location.hash = item.dataset.route;
  });
});
document.querySelector('#auth-button').addEventListener('click', async () => {
  try {
    if (!state.auth.config?.required) {
      await applyDevelopmentUser(document.querySelector('#development-user').value);
      return;
    }
    if (state.auth.user) await logout();
    else await startLogin();
  } catch (error) { showError(error); }
});
document.querySelector('#development-user').addEventListener('keydown', (event) => {
  if (event.key !== 'Enter') return;
  event.preventDefault();
  document.querySelector('#auth-button').click();
});
window.addEventListener('hashchange', () => { showPage().catch(showError); });
document.querySelector('#project-search').addEventListener('input', (event) => {
  state.projectFilters.query = event.target.value;
  renderProjects();
});
document.querySelector('#dependency-search').addEventListener('input', (event) => {
  state.dependencyQuery = event.target.value;
  renderDependencies();
});
document.querySelector('#show-transitive').addEventListener('change', (event) => {
  state.showTransitive = event.target.checked;
  renderDependencies();
  const selected = state.dependencies.find((dependency) => dependency.name === state.selectedDependency);
  if (selected) renderDependencyDetail(selected);
});
document.querySelector('#active-visibility-group').addEventListener('change', async (event) => {
  try {
    state.selectedVisibilityGroup = event.target.value;
    invalidateVisibilityData();
    await showPage();
  } catch (error) { showError(error); }
});
document.querySelector('#create-visibility-group').addEventListener('click', () => {
  const list = document.querySelector('#visibility-group-list');
  if (list.querySelector('.empty-state')) list.replaceChildren();
  list.prepend(visibilityEditorCard({ name: '', rules: [] }, 'group'));
  list.querySelector('input')?.focus();
});
document.querySelector('#create-visibility-policy').addEventListener('click', () => {
  const list = document.querySelector('#visibility-policy-list');
  if (list.querySelector('.empty-state')) list.replaceChildren();
  list.prepend(visibilityEditorCard({ name: '', rules: [] }, 'policy'));
  list.querySelector('input')?.focus();
});
document.querySelector('#close-visibility-user-dialog').addEventListener('click', () => {
  document.querySelector('#visibility-user-dialog').close();
});
STATE_CHANNEL?.addEventListener('message', (event) => {
  const path = event.data?.path || '';
  const invalidatedPages = new Set();
  if (path.startsWith(API.requirements) || path.startsWith(API.requirementGroups)) {
    state.requirements = [];
    state.requirementGroups = [];
    state.requirementCatalog = null;
    ['dashboard', 'projects', 'requirements'].forEach((page) => {
      state.loaded[page] = false;
      invalidatedPages.add(page);
    });
  }
  if (path.startsWith(API.parameters)) {
    state.parameters = [];
    state.requirementCatalog = null;
    ['dashboard', 'projects', 'requirements', 'parameters'].forEach((page) => {
      state.loaded[page] = false;
      invalidatedPages.add(page);
    });
  }
  if (path.startsWith(API.authorizedUsers)) {
    state.loaded.users = false;
    invalidatedPages.add('users');
  }
  if (path.startsWith(API.visibility)) {
    invalidateVisibilityData();
    state.loaded.visibility = false;
    state.loaded['visibility-admin'] = false;
    invalidatedPages.add('visibility');
    invalidatedPages.add('visibility-admin');
    invalidatedPages.add('dashboard');
    invalidatedPages.add('projects');
    invalidatedPages.add('dependencies');
    loadVisibilityGroups().catch(showError);
  }
  const activePage = PAGE_ROUTES[state.currentRoute]?.page;
  if (invalidatedPages.has(activePage)) showPage().catch(showError);
});
document.querySelector('#target-show-single').addEventListener('change', (event) => {
  state.showSingleTechnologies = event.target.checked;
  if (state.technologyTarget) renderTechnologyTarget(state.technologyTarget, state.projectsCount);
});
const themeToggle = document.querySelector('#theme-toggle');
themeToggle.checked = document.documentElement.dataset.theme === 'dark';
themeToggle.addEventListener('change', () => {
  const theme = themeToggle.checked ? 'dark' : 'light';
  document.documentElement.dataset.theme = theme;
  try { localStorage.setItem('radar-theme', theme); } catch (error) { /* Тема сохранится до перезагрузки. */ }
});
document.querySelector('#scan-button').addEventListener('click', async () => {
  try {
    const scan = await api(API.scan, { method: 'POST' });
    await handleScanStatus(scan);
    showSuccess('Сканирование запущено');
  } catch (error) { showError(error); }
});
document.querySelector('#parameters-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  try { await saveParameters(); } catch (error) { showError(error); }
});
document.querySelector('#authorized-user-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  try { await addAuthorizedUser(); } catch (error) { showError(error); }
});
document.querySelector('#add-condition').addEventListener('click', () => addRequirementCondition());
document.querySelector('#add-condition-group').addEventListener('click', () => addRequirementConditionGroup());
document.querySelector('#create-group').addEventListener('click', () => {
  resetGroupForm();
  document.querySelector('#group-dialog').showModal();
});
document.querySelector('#cancel-requirement-edit').addEventListener('click', () => {
  document.querySelector('#requirement-dialog').close();
  resetRequirementForm();
});
document.querySelector('#cancel-group-edit').addEventListener('click', () => {
  document.querySelector('#group-dialog').close();
  resetGroupForm();
});
document.querySelector('#cancel-requirement-move').addEventListener('click', () => {
  document.querySelector('#move-requirement-dialog').close();
});
const requirementGroups = document.querySelector('#requirement-groups');
let draggedGroup = null;
requirementGroups.addEventListener('dragstart', (event) => {
  if (!event.target.closest('.group-drag-handle')) return;
  draggedGroup = event.target.closest('[data-group-id]');
  draggedGroup.classList.add('group-dragging');
  event.dataTransfer.effectAllowed = 'move';
  event.dataTransfer.setData('text/plain', draggedGroup.dataset.groupId);
});
requirementGroups.addEventListener('dragover', (event) => {
  if (!draggedGroup) return;
  event.preventDefault();
  const target = event.target.closest('[data-group-id]');
  if (!target || target === draggedGroup) return;
  const bounds = target.getBoundingClientRect();
  const afterTarget = event.clientY > bounds.top + bounds.height / 2;
  requirementGroups.insertBefore(draggedGroup, afterTarget ? target.nextSibling : target);
});
requirementGroups.addEventListener('drop', async (event) => {
  if (!draggedGroup) return;
  event.preventDefault();
  try { await saveRequirementGroupOrder(); } catch (error) {
    showError(error);
    await reloadRequirements();
  }
});
requirementGroups.addEventListener('dragend', () => {
  draggedGroup?.classList.remove('group-dragging');
  draggedGroup = null;
});
let draggedRequirement = null;
const requirementGroupDetail = document.querySelector('#requirement-group-detail');
requirementGroupDetail.addEventListener('dragstart', (event) => {
  if (!event.target.closest('.requirement-drag-handle')) return;
  draggedRequirement = event.target.closest('[data-requirement-id]');
  draggedRequirement.classList.add('requirement-dragging');
  event.dataTransfer.effectAllowed = 'move';
  event.dataTransfer.setData('text/plain', draggedRequirement.dataset.requirementId);
});
requirementGroupDetail.addEventListener('dragover', (event) => {
  if (!draggedRequirement) return;
  event.preventDefault();
  const target = event.target.closest('[data-requirement-id]');
  if (!target || target === draggedRequirement) return;
  const sourceGroup = draggedRequirement.closest('[data-group-id]');
  if (target.closest('[data-group-id]') !== sourceGroup) return;
  const bounds = target.getBoundingClientRect();
  const afterTarget = event.clientY > bounds.top + bounds.height / 2;
  target.parentElement.insertBefore(draggedRequirement, afterTarget ? target.nextSibling : target);
});
requirementGroupDetail.addEventListener('drop', async (event) => {
  if (!draggedRequirement) return;
  event.preventDefault();
  const groupNode = draggedRequirement.closest('[data-group-id]');
  try { await saveRequirementOrder(groupNode); } catch (error) {
    showError(error);
    await reloadRequirements();
  }
});
requirementGroupDetail.addEventListener('dragend', () => {
  draggedRequirement?.classList.remove('requirement-dragging');
  draggedRequirement = null;
});
document.querySelector('#requirement-group-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const groupId = document.querySelector('#requirement-group-id').value;
  try {
    await api(groupId ? `${API.requirementGroups}${groupId}` : API.requirementGroups, {
      method: groupId ? 'PUT' : 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(groupPayload()),
    });
    await reloadRequirements();
    document.querySelector('#group-dialog').close();
    showSuccess(groupId ? 'Группа сохранена' : 'Группа создана');
  } catch (error) { showError(error); }
});
document.querySelector('#move-requirement-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  try {
    await moveRequirement(
      Number(document.querySelector('#move-requirement-id').value),
      Number(document.querySelector('#move-requirement-group').value),
    );
    document.querySelector('#move-requirement-dialog').close();
  } catch (error) { showError(error); }
});
document.querySelector('#requirement-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const requirementId = document.querySelector('#requirement-id').value;
  try {
    await api(requirementId ? `${API.requirements}${requirementId}` : API.requirements, {
      method: requirementId ? 'PUT' : 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(requirementPayload()),
    });
    await reloadRequirements();
    document.querySelector('#requirement-dialog').close();
    showSuccess(requirementId ? 'Требование сохранено' : 'Требование создано');
  } catch (error) { showError(error); }
});
async function startApplication() {
  try {
    await initializeAuth();
    await loadVisibilityGroups();
    await showPage();
  } catch (error) { showError(error); }
  window.setInterval(updateScanDuration, 1000);
}
startApplication();
