function renderDependencies() {
  const query = state.dependencyQuery.trim().toLowerCase();
  const dependencies = state.dependencies
    .map((dependency) => ({ dependency, visible: visibleDependencyData(dependency) }))
    .filter(({ dependency, visible }) => dependency.name.includes(query) && visible.projectsCount);
  if (state.selectedDependency && !dependencies.some(({ dependency }) => dependency.name === state.selectedDependency)) {
    clearDependencySelection();
  }
  const list = document.querySelector('#dependency-list');
  list.replaceChildren();
  if (!dependencies.length) {
    list.append(element('p', 'empty-state', state.dependencies.length ? 'Элементы не найдены.' : 'Список пуст.'));
    return;
  }
  dependencies.forEach(({ dependency, visible }) => {
    const row = element('button');
    row.type = 'button';
    row.className = `dependency-row${dependency.name === state.selectedDependency ? ' active' : ''}`;
    const identity = element('span');
    const levels = visible.levels.map((level) => LEVEL_TITLES[level]).join(', ');
    const metadata = state.dependencySource === 'python'
      ? `${levels} · вариантов версий: ${visible.versions.length}`
      : `вариантов версий: ${visible.versions.length}`;
    identity.append(element('strong', '', dependency.name), element('small', '', metadata));
    row.append(identity, element('b', '', visible.projectsCount));
    row.addEventListener('click', () => selectDependency(dependency, row));
    list.append(row);
  });
}
function clearDependencySelection() {
  state.selectedDependency = null;
  document.querySelector('#dependency-detail').replaceChildren(
    element('p', 'empty-state', 'Выберите элемент, чтобы посмотреть версии и проекты.'),
  );
}
function resetDependencyPage() {
  state.dependencyQuery = '';
  state.showTransitive = false;
  document.querySelector('#dependency-search').value = '';
  document.querySelector('#show-transitive').checked = false;
  clearDependencySelection();
}
function visibleDependencyData(dependency) {
  const versions = dependency.versions
    .map((version) => ({
      ...version,
      projects: version.projects.filter((project) => (
        state.dependencySource !== 'python' || state.showTransitive || project.level !== 'transitive'
      )),
    }))
    .filter((version) => version.projects.length);
  const projects = versions.flatMap((version) => version.projects);
  const levels = [...new Set(projects.map((project) => project.level))];
  return {
    versions,
    levels: dependency.levels.filter((level) => levels.includes(level)),
    projectsCount: new Set(projects.map((project) => project.id)).size,
  };
}
function renderDependencyDetail(dependency) {
  const detail = document.querySelector('#dependency-detail');
  detail.replaceChildren();
  const visible = visibleDependencyData(dependency);
  detail.append(element('h3', '', dependency.name));
  if (state.dependencySource === 'python') appendDetail(detail, 'Типы использования', visible.levels.map((level) => LEVEL_TITLES[level]).join(', '));
  appendDetail(detail, 'Используется в проектах', String(visible.projectsCount));
  const versions = element('div', 'dependency-versions');
  visible.versions.forEach((version) => {
    const group = element('section', 'dependency-version');
    group.append(element('h4', '', version.version || 'Версия не указана'));
    const projects = element('div', 'dependency-projects');
    version.projects.forEach((project) => {
      const link = element('a', 'dependency-project');
      link.href = project.web_url;
      link.target = '_blank';
      link.rel = 'noreferrer';
      link.append(
        element('strong', '', project.path_with_namespace),
        element('small', '', `${project.subproject_path === '.' ? 'Корень репозитория' : project.subproject_path}${state.dependencySource === 'python' ? ` · ${LEVEL_TITLES[project.level]}` : ''}`),
      );
      projects.append(link);
    });
    group.append(projects);
    versions.append(group);
  });
  detail.append(versions);
}
function selectDependency(dependency, row) {
  state.selectedDependency = dependency.name;
  document.querySelector('.dependency-row.active')?.classList.remove('active');
  row.classList.add('active');
  renderDependencyDetail(dependency);
}
async function loadDependencies() {
  if (!state.dependencyCache[state.dependencySource]) {
    state.dependencyCache[state.dependencySource] = await api(`${API.dependencies}?source=${state.dependencySource}`);
  }
  state.dependencies = state.dependencyCache[state.dependencySource];
  state.loaded.dependencies = true;
  renderDependencies();
  const selected = state.dependencies.find((dependency) => dependency.name === state.selectedDependency);
  if (selected) renderDependencyDetail(selected);
}
async function openDependency(name, source = 'python') {
  state.dependencySource = source;
  document.querySelector('#transitive-filter').classList.toggle('control-placeholder', source !== 'python');
  state.selectedDependency = name;
  const route = SOURCE_ROUTES[source];
  if (window.location.hash !== `#${route}`) {
    window.location.hash = route;
    return;
  }
  await loadDependencies();
}
async function openRuleViolations(code) {
  state.projectFilters.query = '';
  state.projectFilters.rules = new Set([code]);
  syncProjectFilterControls();
  window.location.hash = 'projects';
  await ensurePageLoaded('projects');
  renderProjects();
}
async function openPythonVersion(version) {
  state.projectFilters.rules.clear();
  state.projectFilters.query = `Python ${version}`;
  syncProjectFilterControls();
  window.location.hash = 'projects';
  await ensurePageLoaded('projects');
  renderProjects();
}

