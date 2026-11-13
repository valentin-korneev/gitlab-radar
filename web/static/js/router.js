import { loadAdmin } from './admin.js';
import { startLogin } from './auth.js';
import { loadProjectBlacklist } from './blacklist.js';
import { ADMINISTRATOR_ROUTES, AUTHENTICATED_ROUTES, PAGE_ROUTES } from './config.js';
import { loadDashboard } from './dashboard.js';
import { loadDependencies } from './dependencies.js';
import { connectScanStatusSocket } from './navigation.js';
import { loadProgrammingLanguages } from './languages.js';
import { editablePages, pageEdit, renderPageNotice } from './page-updates.js';
import { loadParametersPage } from './parameters.js';
import { loadProjects } from './projects.js';
import { loadRequirementsPage } from './requirements.js';
import { showError } from './toasts.js';
import { element } from './shared.js';
import { activateCatalog, catalogState, state } from './state.js';
import { loadAuthorizedUsersPage } from './users.js';
import { loadAdminVisibilityPage, loadVisibilityPage } from './visibility.js';

async function showPage() {
  const requestedRoute = window.location.hash.slice(1);
  const routeName = PAGE_ROUTES[requestedRoute] ? requestedRoute : 'dashboard';
  const route = PAGE_ROUTES[routeName];
  const protectedRoute = AUTHENTICATED_ROUTES.has(routeName) || ADMINISTRATOR_ROUTES.has(routeName);
  if (protectedRoute && !state.auth.user) {
    await startLogin(routeName);
    return;
  }
  if (ADMINISTRATOR_ROUTES.has(routeName) && !state.auth.user?.is_admin) {
    window.location.hash = 'dashboard';
    return;
  }
  const previousRoute = state.currentRoute;
  state.currentRoute = routeName;
  renderPageNotice();
  document.querySelectorAll('.nav-item, .page').forEach((node) => node.classList.remove('active'));
  document.querySelector(`.nav-item[data-route="${routeName}"]`).classList.add('active');
  document.querySelector(`#${route.page}`).classList.add('active');
  try {
    if (route.source) {
      const sourceChanged = PAGE_ROUTES[previousRoute]?.source !== route.source;
      activateCatalog(route.source);
      document.querySelector('#dependency-search').value = catalogState.dependencyQuery;
      document.querySelector('#show-transitive').checked = catalogState.showTransitive;
      document.querySelector('#catalog-title').textContent = route.title;
      document.querySelector('#dependency-search').placeholder = route.search;
      document.querySelector('.dependency-controls').hidden = route.source !== 'python';
      if (sourceChanged) {
        document.querySelector('#dependency-detail').replaceChildren(
          element('p', 'empty-state', 'Выберите элемент, чтобы посмотреть версии и проекты.'),
        );
      }
      await loadDependencies();
    } else await ensurePageLoaded(route.page);
    if (routeName === 'admin') await connectScanStatusSocket();
  } catch (error) { showError(error); }
}
async function ensurePageLoaded(pageName) {
  if (state.loaded[pageName] || (editablePages.has(pageName) && pageEdit(pageName).dirty)) return;
  if (!state.loading[pageName]) {
    const loaders = {
      dashboard: loadDashboard, projects: loadProjects, dependencies: loadDependencies,
      requirements: loadRequirementsPage, parameters: loadParametersPage, users: loadAuthorizedUsersPage, admin: loadAdmin,
      languages: loadProgrammingLanguages,
      visibility: loadVisibilityPage, 'visibility-admin': loadAdminVisibilityPage,
      blacklist: loadProjectBlacklist,
    };
    state.loading[pageName] = loaders[pageName]().finally(() => { delete state.loading[pageName]; });
  }
  await state.loading[pageName];
}


export { ensurePageLoaded, showPage };
