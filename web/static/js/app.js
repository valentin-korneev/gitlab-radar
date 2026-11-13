import { api } from './api.js';
import { initializeAuth, logout, startLogin } from './auth.js';
import { addProjectBlacklistRule } from './blacklist.js';
import { API, PAGE_ROUTES } from './config.js';
import { renderTechnologyTarget } from './dashboard.js';
import { renderDependencies, renderDependencyDetail, resetDependencyPage } from './dependencies.js';
import { bindEditorForm } from './editors.js';
import { initializePageUpdates } from './page-updates.js';
import { saveParameters } from './parameters.js';
import { exportFilteredProjects, renderProjects, resetProjectFilters } from './projects.js';
import { addRequirementCondition, addRequirementConditionGroup, groupPayload, moveRequirement, reloadRequirements, requirementPayload, resetGroupForm, resetRequirementForm, saveRequirementGroupOrder, saveRequirementOrder } from './requirements.js';
import { showPage } from './router.js';
import { showError, showSuccess } from './toasts.js';
import { handleScanStatus, renderScanStatus, updateScanDuration } from './scan.js';
import { initializeIcons } from './shared.js';
import { catalogState, dashboardState, projectState, scanState, state } from './state.js';
import { addAuthorizedUser } from './users.js';
import { invalidateVisibilityData, loadVisibilityGroups, visibilityEditorCard } from './visibility.js';

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
    if (state.auth.user) await logout();
    else await startLogin();
  } catch (error) { showError(error); }
});
window.addEventListener('hashchange', () => { showPage().catch(showError); });
window.addEventListener('radar-project-filters', renderProjects);
document.querySelector('#project-search').addEventListener('input', (event) => {
  projectState.projectFilters.query = event.target.value;
  projectState.projectFilters.language = null;
  projectState.projectFilters.version = null;
  renderProjects();
});
document.querySelector('#export-projects').addEventListener('click', exportFilteredProjects);
document.querySelector('#dependency-search').addEventListener('input', (event) => {
  catalogState.dependencyQuery = event.target.value;
  renderDependencies();
});
document.querySelector('#show-transitive').addEventListener('change', (event) => {
  catalogState.showTransitive = event.target.checked;
  renderDependencies();
  const selected = catalogState.dependencies.find((dependency) => dependency.name === catalogState.selectedDependency);
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
document.querySelector('#target-show-single').addEventListener('change', (event) => {
  dashboardState.showSingleTechnologies = event.target.checked;
  if (dashboardState.technologyTarget) renderTechnologyTarget(dashboardState.technologyTarget, dashboardState.projectsCount);
});
const themeToggle = document.querySelector('#theme-toggle');
themeToggle.checked = document.documentElement.dataset.theme === 'dark';
themeToggle.addEventListener('change', () => {
  const theme = themeToggle.checked ? 'dark' : 'light';
  document.documentElement.dataset.theme = theme;
  try { localStorage.setItem('radar-theme', theme); } catch (error) { /* Тема сохранится до перезагрузки. */ }
});
document.querySelector('#scan-button').addEventListener('click', async () => {
  if (!state.auth.user?.is_admin || scanState.scanSubmitting || scanState.scanStatus?.state === 'stopping') return;
  const stopping = ['queued', 'running'].includes(scanState.scanStatus?.state);
  const url = stopping ? `${API.scan}${scanState.scanStatus.id}/stop` : API.scan;
  scanState.scanSubmitting = true;
  document.querySelector('#scan-button').disabled = true;
  try {
    const scan = await api(url, { method: 'POST' });
    await handleScanStatus(scan);
    if (!stopping) showSuccess(`Запуск №${scan.id} принят`);
  } catch (error) { showError(error); }
  finally {
    scanState.scanSubmitting = false;
    if (scanState.scanStatus) renderScanStatus(scanState.scanStatus);
  }
});
bindEditorForm('#parameters-form', async (event) => {
  event.preventDefault();
  try { await saveParameters(); } catch (error) { showError(error); }
});
bindEditorForm('#authorized-user-form', async (event) => {
  event.preventDefault();
  try { await addAuthorizedUser(); } catch (error) { showError(error); }
});
bindEditorForm('#blacklist-form', async (event) => {
  event.preventDefault();
  try { await addProjectBlacklistRule(); } catch (error) { showError(error); }
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
bindEditorForm('#requirement-group-form', async (event) => {
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
bindEditorForm('#move-requirement-form', async (event) => {
  event.preventDefault();
  try {
    await moveRequirement(
      Number(document.querySelector('#move-requirement-id').value),
      Number(document.querySelector('#move-requirement-group').value),
    );
    document.querySelector('#move-requirement-dialog').close();
  } catch (error) { showError(error); }
});
bindEditorForm('#requirement-form', async (event) => {
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
  initializeIcons();
  initializePageUpdates();
  try {
    await initializeAuth();
    await loadVisibilityGroups();
    await showPage();
  } catch (error) { showError(error); }
  window.setInterval(updateScanDuration, 1000);
}
startApplication();
