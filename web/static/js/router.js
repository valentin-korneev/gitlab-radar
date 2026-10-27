async function showPage() {
  const requestedRoute = window.location.hash.slice(1);
  const routeName = PAGE_ROUTES[requestedRoute] ? requestedRoute : 'dashboard';
  const route = PAGE_ROUTES[routeName];
  if (state.currentRoute === 'projects' && routeName !== 'projects') resetProjectFilters();
  if (PAGE_ROUTES[state.currentRoute]?.source && routeName !== state.currentRoute) resetDependencyPage();
  const protectedRoute = AUTHENTICATED_ROUTES.has(routeName) || ADMINISTRATOR_ROUTES.has(routeName);
  if (state.auth.config?.required && protectedRoute && !await accessToken()) {
    await startLogin(routeName);
    return;
  }
  if (state.auth.config?.required && ADMINISTRATOR_ROUTES.has(routeName) && !state.auth.user?.is_admin) {
    window.location.hash = 'dashboard';
    return;
  }
  state.currentRoute = routeName;
  document.querySelectorAll('.nav-item, .page').forEach((node) => node.classList.remove('active'));
  document.querySelector(`.nav-item[data-route="${routeName}"]`).classList.add('active');
  document.querySelector(`#${route.page}`).classList.add('active');
  try {
    if (route.source) {
      const sourceChanged = state.dependencySource !== route.source;
      state.dependencySource = route.source;
      if (sourceChanged) state.selectedDependency = null;
      document.querySelector('#catalog-title').textContent = route.title;
      document.querySelector('#dependency-search').placeholder = route.search;
      document.querySelector('#transitive-filter').classList.toggle('control-placeholder', route.source !== 'python');
      if (sourceChanged) {
        document.querySelector('#dependency-detail').replaceChildren(
          element('p', 'empty-state', 'Выберите элемент, чтобы посмотреть версии и проекты.'),
        );
      }
      await loadDependencies();
    } else await ensurePageLoaded(route.page);
  } catch (error) { showError(error); }
}
async function ensurePageLoaded(pageName) {
  if (state.loaded[pageName]) return;
  if (!state.loading[pageName]) {
    const loaders = {
      dashboard: loadDashboard, projects: loadProjects, dependencies: loadDependencies,
      requirements: loadRequirementsPage, parameters: loadParametersPage, users: loadAuthorizedUsersPage, admin: loadAdmin,
    };
    state.loading[pageName] = loaders[pageName]().finally(() => { delete state.loading[pageName]; });
  }
  await state.loading[pageName];
}

