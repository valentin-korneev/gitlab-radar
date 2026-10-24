const API = {
  dashboard: '/api/dashboard/', dependencies: '/api/dependency/', projects: '/api/project/', scan: '/api/scan/',
};
const PAGE_TITLES = { dashboard: 'Обзор', projects: 'Проекты', dependencies: 'Зависимости', admin: 'Управление' };
const LEVEL_TITLES = { direct: 'Прямая', optional: 'Опциональная', transitive: 'Транзитивная' };
const PHASE_TITLES = {
  idle: 'Ожидание запуска', collecting: 'Сбор файлов из GitLab', analyzing: 'Локальный анализ файлов',
  publishing: 'Публикация результатов', completed: 'Результаты опубликованы',
};
const state = {
  projects: [], dependencies: [], dependencyCache: {}, dependencySource: 'python', selectedId: null, selectedSubprojectPath: null,
  selectedDependency: null, showTransitive: false, scanState: null, pollTimer: null,
  technologyTarget: null, projectsCount: 0, showSingleTechnologies: false,
  loaded: { dashboard: false, projects: false, dependencies: false }, loading: {},
};

async function api(path, options = {}) {
  const response = await fetch(path, { cache: 'no-store', ...options });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || `HTTP ${response.status}`);
  }
  return response.json();
}
function formatDate(value) {
  if (!value) return '—';
  return new Intl.DateTimeFormat('ru-RU', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value));
}
function formatDuration(seconds) {
  if (seconds < 60) return `${seconds.toLocaleString('ru-RU')} сек.`;
  return `${Math.floor(seconds / 60)} мин. ${Math.round(seconds % 60)} сек.`;
}
function projectPathParts(value) { return value.split('/').filter(Boolean); }
function registryName(value) {
  try { return new URL(value.includes('://') ? value : `https://${value}`).host.toLowerCase(); }
  catch (error) { return value.split('/')[0].toLowerCase(); }
}
function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
function subprojectView(project, subproject, detected = true) {
  const isRoot = subproject.path === '.';
  return {
    path: subproject.path,
    title: isRoot ? project.name : projectPathParts(subproject.path).at(-1),
    fullPath: isRoot ? project.path_with_namespace : `${project.path_with_namespace}/${subproject.path}`,
    packageManager: subproject.package_manager,
    pythonVersion: subproject.python_version || null,
    pythonConstraint: subproject.python_constraint || null,
    pythonVersionSource: subproject.python_version_source || null,
    dependencies: subproject.dependencies || [],
    optionalDependencies: subproject.optional_dependencies || [],
    transitiveDependencies: subproject.transitive_dependencies || [],
    hasDocker: Boolean(subproject.has_docker),
    containerImages: subproject.container_images || [],
    packageRegistries: subproject.package_registries || [],
    compliance: subproject.company_compliance_percentage || 0,
    ruleResults: subproject.company_rule_results || {},
    isRoot, detected,
  };
}
function projectView(project) {
  const subprojects = project.subprojects.map((subproject) => subprojectView(project, subproject));
  const root = subprojects.find((subproject) => subproject.isRoot) || null;
  const monorepository = subprojects.length > 1;
  const fallback = subprojects.length === 0
    ? subprojectView(project, {
      path: '.', package_manager: project.package_manager, dependencies: [], optional_dependencies: [],
      transitive_dependencies: [],
    }, false)
    : null;
  return {
    project,
    root: root || (monorepository ? null : subprojects[0]) || fallback,
    children: monorepository ? subprojects.filter((subproject) => !subproject.isRoot) : [],
    monorepository,
  };
}

async function showPage() {
  const requestedPage = window.location.hash.slice(1);
  const pageName = PAGE_TITLES[requestedPage] ? requestedPage : 'dashboard';
  document.querySelectorAll('.nav-item, .page').forEach((node) => node.classList.remove('active'));
  document.querySelector(`.nav-item[data-page="${pageName}"]`).classList.add('active');
  document.querySelector(`#${pageName}`).classList.add('active');
  document.querySelector('#page-title').textContent = PAGE_TITLES[pageName];
  try { await ensurePageLoaded(pageName); } catch (error) { showError(error); }
}
async function ensurePageLoaded(pageName) {
  if (pageName === 'admin' || state.loaded[pageName]) return;
  if (!state.loading[pageName]) {
    const loaders = { dashboard: loadDashboard, projects: loadProjects, dependencies: loadDependencies };
    state.loading[pageName] = loaders[pageName]().finally(() => { delete state.loading[pageName]; });
  }
  await state.loading[pageName];
}

function projectMatchesFilters(project) {
  const query = document.querySelector('#project-search').value.trim().toLowerCase();
  const rules = [...document.querySelectorAll('.rule-switches input:checked')]
    .map((input) => input.dataset.rule);
  const searchable = `${project.name} ${project.path_with_namespace} ${project.subprojects.map((item) => item.path).join(' ')}`.toLowerCase();
  return (!query || searchable.includes(query))
    && rules.every((rule) => project.company_rule_results?.[rule] === false);
}
function renderProjects() {
  const projects = state.projects.filter(projectMatchesFilters);
  const list = document.querySelector('#project-list');
  list.replaceChildren();
  if (!projects.length) {
    list.append(element('p', 'empty-state', state.projects.length ? 'Проекты не найдены.' : 'Список проектов пуст. Запустите сканирование.'));
    return;
  }
  projects.forEach((project) => {
    const view = projectView(project);
    const selectedProject = project.id === state.selectedId;
    const tree = element('div', 'project-tree');
    const row = element('button');
    row.className = `project-row${selectedProject && state.selectedSubprojectPath === (view.root?.path || null) ? ' active' : ''}`;
    row.type = 'button';
    const identity = element('span');
    identity.append(element('strong', '', project.name), element('small', '', projectPathParts(project.path_with_namespace).join(' › ')));
    if (view.monorepository) {
      identity.append(element('small', 'subproject-summary', `Монорепозиторий · подпроектов: ${view.children.length + (view.root ? 1 : 0)}`));
    }
    row.append(identity, element('time', '', formatDate(project.last_activity_at)));
    row.addEventListener('click', () => selectProject(view, view.root, row));
    tree.append(row);
    if (view.children.length) {
      const children = element('div', 'project-children');
      view.children.forEach((subproject) => {
        const child = element('button');
        child.className = `project-child${selectedProject && state.selectedSubprojectPath === subproject.path ? ' active' : ''}`;
        child.type = 'button';
        child.append(element('span', '', projectPathParts(subproject.path).join(' › ')), packageManagerBadge(subproject.packageManager));
        child.addEventListener('click', () => selectProject(view, subproject, child));
        children.append(child);
      });
      tree.append(children);
    }
    list.append(tree);
  });
}
function appendDetail(container, label, value) {
  container.append(element('p', 'detail-label', label));
  const content = value instanceof Node ? value : element('p', 'detail-value', value || '—');
  container.append(content);
  return content;
}
function appendProjectPath(container, value) {
  const breadcrumb = element('div', 'project-path');
  projectPathParts(value).forEach((part) => breadcrumb.append(element('span', '', part)));
  appendDetail(container, 'Полный путь', breadcrumb);
}
function packageManagerBadge(value) {
  const badge = element('span', 'status-badge', value || '—');
  badge.classList.add(value === 'uv' ? 'manager-uv' : value === 'pip' ? 'manager-pip' : 'manager-other');
  return badge;
}
function dependencyBadge(dependency) {
  const badge = element('span', 'dependency-badge');
  badge.append(element('strong', '', dependency.name));
  if (dependency.version) badge.append(element('span', '', dependency.version));
  return badge;
}
function dependencyGroup(title, dependencies) {
  const group = element('section', 'dependency-group');
  group.append(element('h4', '', title));
  const items = element('div', 'dependency-badges');
  dependencies.forEach((dependency) => items.append(dependencyBadge(dependency)));
  group.append(items);
  return group;
}
function appendProjectDependencies(container, subproject) {
  const groups = [];
  if (subproject.dependencies.length) groups.push(dependencyGroup('Основные', subproject.dependencies));
  subproject.optionalDependencies.forEach((group) => {
    if (group.dependencies.length) groups.push(dependencyGroup(`Опциональные · ${group.name}`, group.dependencies));
  });
  const content = element('div', 'project-dependencies');
  if (groups.length) content.append(...groups);
  else content.append(element('p', 'empty-state', 'Основные и опциональные зависимости не найдены.'));
  if (subproject.transitiveDependencies.length) {
    const transitive = dependencyGroup('Транзитивные', subproject.transitiveDependencies);
    transitive.hidden = true;
    const button = element('button', 'transitive-toggle', `Показать транзитивные · ${subproject.transitiveDependencies.length}`);
    button.type = 'button';
    button.addEventListener('click', () => {
      transitive.hidden = !transitive.hidden;
      button.textContent = transitive.hidden
        ? `Показать транзитивные · ${subproject.transitiveDependencies.length}`
        : 'Скрыть транзитивные';
    });
    content.append(button, transitive);
  }
  const count = new Set([
    ...subproject.dependencies.map((dependency) => dependency.name),
    ...subproject.optionalDependencies.flatMap((group) => group.dependencies.map((dependency) => dependency.name)),
    ...subproject.transitiveDependencies.map((dependency) => dependency.name),
  ]).size;
  const disclosure = element('details', 'dependency-disclosure');
  disclosure.append(element('summary', '', `Зависимости · ${count}`), content);
  container.append(disclosure);
}
function appendGitLabComponents(container, project) {
  if (!project.gitlab_ci_components?.length) return;
  const components = element('div', 'dependency-badges');
  project.gitlab_ci_components.forEach((component) => components.append(dependencyBadge(component)));
  appendDetail(container, 'Компоненты GitLab CI', components);
}
function appendContainerImages(container, project) {
  if (!project.container_images?.length) return;
  const images = element('div', 'dependency-badges');
  project.container_images.forEach((image) => images.append(dependencyBadge({
    name: `${image.registry}/${image.image}`, version: image.version,
  })));
  appendDetail(container, 'Образы Docker', images);
  const compose = project.container_images
    .filter((image) => image.source === 'compose')
    .map((image) => `${image.registry}/${image.image}${image.version ? `:${image.version}` : ''}`);
  if (compose.length) appendDetail(container, 'Технологии Docker Compose', [...new Set(compose)].join(', '));
  const registries = new Set([
    ...(project.package_registries || []),
    ...project.container_images.map((image) => image.registry),
  ].map(registryName));
  if (registries.size) appendDetail(container, 'Registry', [...registries].join(', '));
}
function renderProjectDetail(view, subproject) {
  const { project } = view;
  const detail = document.querySelector('#project-detail');
  detail.replaceChildren();
  if (!subproject) {
    detail.append(element('h3', '', project.name), element('p', 'empty-state', 'Выберите подпроект. Корень репозитория не содержит отдельного проекта.'));
    appendProjectPath(detail, project.path_with_namespace);
    appendDetail(detail, 'Основная ветка', project.default_branch);
    appendDetail(detail, 'Docker', project.has_docker ? 'Используется' : 'Не используется');
    appendDetail(detail, 'GitLab CI', project.has_gitlab_ci ? 'Используется' : 'Не используется');
    appendGitLabComponents(detail, project);
    appendContainerImages(detail, project);
    return;
  }
  detail.append(element('h3', '', subproject.title));
  appendDetail(detail, 'ID', String(project.id));
  appendProjectPath(detail, subproject.fullPath);
  appendDetail(detail, 'Основная ветка', project.default_branch);
  appendDetail(detail, 'Пакетный менеджер', packageManagerBadge(subproject.packageManager));
  const pythonValue = subproject.pythonVersion
    ? `${subproject.pythonVersion}${subproject.pythonVersionSource ? ` · ${subproject.pythonVersionSource}` : ''}`
    : 'Не определена';
  appendDetail(detail, 'Версия Python', pythonValue);
  appendDetail(detail, 'Ограничение Python', subproject.pythonConstraint || 'Не указано');
  appendDetail(detail, 'Соответствие правилам компании', `${subproject.compliance}%`);
  appendDetail(detail, 'Docker', project.has_docker ? 'Используется' : 'Не используется');
  appendDetail(detail, 'GitLab CI', project.has_gitlab_ci ? 'Используется' : 'Не используется');
  appendProjectDependencies(detail, subproject);
  appendGitLabComponents(detail, project);
  appendContainerImages(detail, project);
  if (project.scan_error) appendDetail(detail, 'Ошибка анализа', project.scan_error);
  appendDetail(detail, 'Последняя активность', formatDate(project.last_activity_at));
  const link = element('a', 'detail-link', 'Открыть в GitLab →');
  link.href = project.web_url;
  link.target = '_blank';
  link.rel = 'noreferrer';
  detail.append(link);
}
function selectProject(view, subproject, row) {
  state.selectedId = view.project.id;
  state.selectedSubprojectPath = subproject?.path || null;
  document.querySelectorAll('.project-row.active, .project-child.active').forEach((node) => node.classList.remove('active'));
  row.classList.add('active');
  renderProjectDetail(view, subproject);
}

function compactStatRow(label, value) {
  const row = element('div');
  row.append(element('span', '', label), element('b', '', String(value)));
  return row;
}
function stableFraction(value) {
  let hash = 2166136261;
  for (const character of value) {
    hash ^= character.codePointAt(0);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0) / 4294967295;
}
function renderTechnologyTarget(target, projectsCount) {
  const definitions = [
    ['Python', target.python_versions], ['Зависимости', target.dependencies],
    ['Образы', target.images], ['Registry', target.registries],
  ];
  const markers = document.querySelector('#target-markers');
  const scaleMaximum = Math.max(Math.ceil(projectsCount * 1.1), 1);
  const markerNodes = definitions.flatMap(([category, sourceItems], categoryIndex) => {
    const items = sourceItems.filter((item) => state.showSingleTechnologies || item.projects_count > 1);
    const topItems = new Set(
      [...items]
        .sort((left, right) => right.projects_count - left.projects_count || left.name.localeCompare(right.name))
        .slice(0, 5),
    );
    return items.map((item) => {
      const marker = element('span', `target-marker target-category-${categoryIndex}`);
      const randomAngle = stableFraction(`${category}:${item.name}:angle`);
      const angle = (-85 + categoryIndex * 90 + randomAngle * 80) * Math.PI / 180;
      const radius = 4 + (1 - Math.min(item.projects_count / scaleMaximum, 1)) * 42;
      marker.style.left = `${50 + Math.cos(angle) * radius}%`;
      marker.style.top = `${50 + Math.sin(angle) * radius}%`;
      const tooltip = `${category} · ${item.name} · ${item.projects_count} проектов`;
      marker.dataset.tooltip = tooltip;
      marker.setAttribute('aria-label', tooltip);
      marker.tabIndex = 0;
      marker.append(element('i'));
      if (topItems.has(item)) {
        marker.classList.add('target-marker-labeled');
        marker.append(element('small', '', item.name));
      }
      return marker;
    });
  });
  markers.replaceChildren(...markerNodes);
}
function renderDashboard(dashboard) {
  document.querySelector('#project-count').textContent = dashboard.projects_count;
  document.querySelector('#subproject-count').textContent = dashboard.subprojects_count;
  document.querySelector('#dependency-count').textContent = dashboard.dependency_counts.total;
  document.querySelector('#direct-dependency-count').textContent = dashboard.dependency_counts.direct;
  document.querySelector('#optional-dependency-count').textContent = dashboard.dependency_counts.optional;
  document.querySelector('#transitive-dependency-count').textContent = dashboard.dependency_counts.transitive;
  document.querySelector('#docker-project-count').textContent = dashboard.docker_projects_count;
  document.querySelector('#gitlab-ci-project-count').textContent = dashboard.gitlab_ci_projects_count;
  const total = dashboard.projects_count || 1;
  document.querySelector('#docker-project-percentage').textContent = `${Math.round(dashboard.docker_projects_count / total * 100)}% проектов`;
  document.querySelector('#gitlab-ci-project-percentage').textContent = `${Math.round(dashboard.gitlab_ci_projects_count / total * 100)}% проектов`;
  state.technologyTarget = dashboard.technology_target;
  state.projectsCount = dashboard.projects_count;
  renderTechnologyTarget(dashboard.technology_target, dashboard.projects_count);
  const registries = document.querySelector('#registry-stats');
  registries.replaceChildren(...dashboard.registries.map((item) => compactStatRow(item.name, item.projects_count)));
  if (!dashboard.registries.length) registries.append(element('p', 'empty-state', 'Registry не обнаружены.'));

  const pythonVersions = document.querySelector('#python-version-stats');
  pythonVersions.replaceChildren(...dashboard.python_versions.map((item) => compactStatRow(`Python ${item.version}`, item.projects_count)));
  if (!dashboard.python_versions.length) pythonVersions.append(element('p', 'empty-state', 'Версии не определены.'));

  const statistics = document.querySelector('#package-manager-stats');
  statistics.replaceChildren();
  dashboard.package_managers.forEach((item) => {
    const row = element('div', 'statistics-row');
    const label = element('div', 'statistics-label');
    label.append(element('strong', '', item.title), element('span', '', `${item.percentage}%`));
    const track = element('div', 'statistics-track');
    const trackValue = element('span');
    trackValue.style.width = `${item.percentage}%`;
    track.append(trackValue);
    row.append(label, track, element('b', '', String(item.subprojects_count)));
    row.title = `${item.projects_count} репозиториев, ${item.subprojects_count} подпроектов`;
    statistics.append(row);
  });

  const topDependencies = document.querySelector('#top-dependencies');
  topDependencies.replaceChildren();
  dashboard.top_dependencies.forEach((item, index) => {
    const row = element('button', 'dependency-top-row');
    row.type = 'button';
    row.append(element('span', 'dependency-rank', String(index + 1).padStart(2, '0')), element('strong', '', item.name), element('b', '', item.projects_count));
    row.addEventListener('click', () => openDependency(item.name));
    topDependencies.append(row);
  });
  if (!dashboard.top_dependencies.length) topDependencies.append(element('p', 'empty-state', 'Зависимости ещё не найдены.'));

  const requirements = document.querySelector('#company-requirements');
  requirements.replaceChildren();
  dashboard.company_requirements.forEach((item) => {
    const card = element('button', 'requirement');
    card.type = 'button';
    const header = element('div');
    header.append(element('strong', '', item.title), element('b', '', `${item.compliance_percentage}%`));
    const progress = element('div', 'requirement-progress');
    const progressValue = element('span');
    progressValue.style.width = `${item.compliance_percentage}%`;
    progress.append(progressValue);
    card.append(header, element('p', '', item.description), progress, element('small', '', `${item.matching_projects} из ${item.total_projects} проектов`));
    card.addEventListener('click', () => openRuleViolations(item.code));
    requirements.append(card);
  });

  const quality = dashboard.data_quality;
  document.querySelector('#data-quality-stats').replaceChildren(
    compactStatRow('Менеджер не определён', quality.unknown_package_manager),
    compactStatRow('Версия Python не определена', quality.unknown_python_version),
    compactStatRow('Без подпроектов', quality.projects_without_subprojects),
    compactStatRow('Ошибки анализа', quality.analysis_errors),
  );
  const lastScan = document.querySelector('#last-scan-stats');
  lastScan.replaceChildren();
  if (dashboard.last_scan) {
    lastScan.append(
      compactStatRow('Завершено', formatDate(dashboard.last_scan.completed_at)),
      compactStatRow('Длительность', formatDuration(dashboard.last_scan.duration_seconds)),
      compactStatRow('Повторно использовано', dashboard.last_scan.reused_projects),
      compactStatRow('Пропущено', dashboard.last_scan.skipped_projects),
      compactStatRow('Ошибки', dashboard.last_scan.errors_count),
      compactStatRow('Обращения к GitLab', dashboard.last_scan.gitlab_requests),
    );
  } else lastScan.append(element('p', 'empty-state', 'Сканирование ещё не запускалось.'));
}
async function loadDashboard() { renderDashboard(await api(API.dashboard)); state.loaded.dashboard = true; }
async function loadProjects() {
  state.projects = await api(API.projects);
  state.loaded.projects = true;
  renderProjects();
  const selected = state.projects.find((project) => project.id === state.selectedId);
  if (selected) {
    const view = projectView(selected);
    const entries = [view.root, ...view.children].filter(Boolean);
    const subproject = entries.find((item) => item.path === state.selectedSubprojectPath) || view.root;
    state.selectedSubprojectPath = subproject?.path || null;
    renderProjectDetail(view, subproject);
  }
}

function renderDependencies() {
  const query = document.querySelector('#dependency-search').value.trim().toLowerCase();
  const dependencies = state.dependencies
    .filter((dependency) => dependency.name.includes(query)
      && (state.showTransitive || dependency.levels.some((level) => level !== 'transitive')));
  const list = document.querySelector('#dependency-list');
  list.replaceChildren();
  if (!dependencies.length) {
    list.append(element('p', 'empty-state', state.dependencies.length ? 'Зависимости не найдены.' : 'Список зависимостей пуст.'));
    return;
  }
  dependencies.forEach((dependency) => {
    const row = element('button');
    row.type = 'button';
    row.className = `dependency-row${dependency.name === state.selectedDependency ? ' active' : ''}`;
    const identity = element('span');
    const levels = dependency.levels.map((level) => LEVEL_TITLES[level]).join(', ');
    const metadata = state.dependencySource === 'python'
      ? `${levels} · вариантов версий: ${dependency.versions.length}`
      : `вариантов версий: ${dependency.versions.length}`;
    identity.append(element('strong', '', dependency.name), element('small', '', metadata));
    row.append(identity, element('b', '', dependency.projects_count));
    row.addEventListener('click', () => selectDependency(dependency, row));
    list.append(row);
  });
}
function renderDependencyDetail(dependency) {
  const detail = document.querySelector('#dependency-detail');
  detail.replaceChildren();
  detail.append(element('h3', '', dependency.name));
  if (state.dependencySource === 'python') appendDetail(detail, 'Типы использования', dependency.levels.map((level) => LEVEL_TITLES[level]).join(', '));
  appendDetail(detail, 'Используется в проектах', String(dependency.projects_count));
  const versions = element('div', 'dependency-versions');
  dependency.versions.forEach((version) => {
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
async function openDependency(name) {
  state.dependencySource = 'python';
  document.querySelectorAll('.source-tab').forEach((item) => item.classList.toggle('active', item.dataset.source === 'python'));
  document.querySelector('#transitive-filter').classList.remove('control-placeholder');
  state.selectedDependency = name;
  window.location.hash = 'dependencies';
  await loadDependencies();
  const dependency = state.dependencies.find((item) => item.name === name);
  if (dependency) renderDependencyDetail(dependency);
}
async function openRuleViolations(code) {
  document.querySelectorAll('.rule-switches input').forEach((input) => {
    input.checked = input.dataset.rule === code;
  });
  window.location.hash = 'projects';
  await ensurePageLoaded('projects');
  renderProjects();
}

function renderScanStatus(scan) {
  document.querySelector('#scan-state').textContent = scan.state_title;
  document.querySelector('#scan-button').disabled = scan.state === 'running';
  document.querySelector('#scan-dot').className = scan.state;
  let description = 'Сканирование ещё не запускалось.';
  if (scan.state === 'running') description = `${PHASE_TITLES[scan.phase]} · запущено ${formatDate(scan.started_at)}`;
  if (scan.state === 'completed') description = `Завершено ${formatDate(scan.completed_at)} · проектов: ${scan.projects_count}`;
  if (scan.state === 'failed') description = `Завершено ${formatDate(scan.completed_at)} · ${scan.error || 'неизвестная ошибка'}`;
  document.querySelector('#scan-description').textContent = description;
  document.querySelector('#scan-progress-value').style.width = `${scan.progress_percentage}%`;
  document.querySelector('#scan-progress-label').textContent = `${scan.completed_steps} из ${scan.total_steps} этапов · собрано ${scan.collected_projects}, проанализировано ${scan.analyzed_projects}, повторно ${scan.reused_projects}`;
  document.querySelector('#scan-duration').textContent = formatDuration(scan.duration_seconds);
  document.querySelector('#scan-requests').textContent = `Обращений к GitLab: ${scan.gitlab_requests}`;
  document.querySelector('#scan-current-project').textContent = scan.current_project ? `Сейчас: ${scan.current_project}` : '';
  const errors = document.querySelector('#scan-errors');
  const errorList = document.querySelector('#scan-errors-list');
  const allErrors = [...scan.errors];
  if (scan.error && !allErrors.includes(scan.error)) allErrors.push(scan.error);
  errors.hidden = allErrors.length === 0;
  document.querySelector('#scan-errors-count').textContent = allErrors.length;
  errorList.replaceChildren(...allErrors.map((error) => element('p', '', error)));
}
async function refreshScanStatus() {
  let retry = false;
  try {
    const previousState = state.scanState;
    const scan = await api(API.scan);
    state.scanState = scan.state;
    renderScanStatus(scan);
    if (previousState === 'running' && scan.state === 'completed') {
      state.dependencyCache = {};
      const reloads = [loadDashboard()];
      if (state.loaded.projects) reloads.push(loadProjects());
      if (state.loaded.dependencies) reloads.push(loadDependencies());
      await Promise.all(reloads);
    }
  } catch (error) {
    retry = true;
    showError(error);
  } finally {
    window.clearTimeout(state.pollTimer);
    state.pollTimer = state.scanState === 'running' || retry
      ? window.setTimeout(refreshScanStatus, retry ? 10000 : 3000)
      : null;
  }
}
function showError(error) {
  const toast = document.querySelector('#global-error');
  toast.textContent = error.message;
  toast.hidden = false;
  window.setTimeout(() => { toast.hidden = true; }, 5000);
}

document.querySelectorAll('.nav-item').forEach((item) => {
  item.addEventListener('click', () => { window.location.hash = item.dataset.page; });
});
window.addEventListener('hashchange', showPage);
document.querySelector('#project-search').addEventListener('input', renderProjects);
document.querySelectorAll('.rule-switches input').forEach((input) => {
  input.addEventListener('change', renderProjects);
});
document.querySelector('#dependency-search').addEventListener('input', renderDependencies);
document.querySelectorAll('.source-tab').forEach((button) => {
  button.addEventListener('click', async () => {
    state.dependencySource = button.dataset.source;
    state.selectedDependency = null;
    document.querySelectorAll('.source-tab').forEach((item) => item.classList.toggle('active', item === button));
    document.querySelector('#transitive-filter').classList.toggle('control-placeholder', state.dependencySource !== 'python');
    document.querySelector('#dependency-detail').replaceChildren(element('p', 'empty-state', 'Выберите зависимость, чтобы посмотреть версии и проекты.'));
    await loadDependencies();
  });
});
document.querySelector('#show-transitive').addEventListener('change', (event) => {
  state.showTransitive = event.target.checked;
  renderDependencies();
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
  try { await api(API.scan, { method: 'POST' }); } catch (error) { showError(error); }
  await refreshScanStatus();
});
showPage();
refreshScanStatus();
