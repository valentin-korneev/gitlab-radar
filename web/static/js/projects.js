const PROJECT_DATA_STATUS_TITLES = {
  stale: 'Устаревшие данные — проект не обработан в текущем сканировании',
  missing: 'Проект не найден при последнем сканировании',
};

function subprojectView(project, subproject, detected = true) {
  const isRoot = subproject.path === '.';
  const language = subproject.language || 'python';
  return {
    key: `${language}:${subproject.path}`,
    path: subproject.path,
    title: isRoot ? project.name : projectPathParts(subproject.path).at(-1),
    fullPath: isRoot ? project.path_with_namespace : `${project.path_with_namespace}/${subproject.path}`,
    packageManager: subproject.package_manager,
    language,
    runtimeVersion: subproject.runtime_version || null,
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
  const fallback = subprojects.length === 0 && !project.is_empty && !(project.languages || []).length
    ? subprojectView(project, {
      path: '.', package_manager: project.package_manager, dependencies: [], optional_dependencies: [],
      transitive_dependencies: [],
    }, false)
    : null;
  const displayRoot = root || (monorepository ? null : subprojects[0]) || fallback;
  return {
    project,
    root: displayRoot,
    children: monorepository ? subprojects.filter((subproject) => subproject !== displayRoot) : [],
    monorepository,
  };
}

function compareProjectsByScanTime(left, right) {
  const leftStatus = left.data_status === 'current' ? 0 : 1;
  const rightStatus = right.data_status === 'current' ? 0 : 1;
  const leftTime = left.scanned_at ? new Date(left.scanned_at).getTime() : Number.POSITIVE_INFINITY;
  const rightTime = right.scanned_at ? new Date(right.scanned_at).getTime() : Number.POSITIVE_INFINITY;
  return leftStatus - rightStatus || leftTime - rightTime || left.id - right.id;
}


function projectMatchesFilters(project) {
  const query = state.projectFilters.query.trim().toLowerCase();
  const rules = [...state.projectFilters.rules];
  const languageNames = new Map(
    (project.languages || []).map((language) => [language.code, language.name]),
  );
  const languageVersions = project.subprojects
    .map((item) => {
      const version = normalizedRuntimeVersion(
        item.runtime_version || item.python_version || item.python_constraint,
      );
      if (!version) return '';
      const language = item.language || 'python';
      return `${languageNames.get(language) || language} ${version} ${language} ${version}`;
    })
    .filter(Boolean)
    .join(' ');
  const languages = (project.languages || []).map((language) => `${language.name} ${language.code}`).join(' ');
  const searchable = `${project.name} ${project.path_with_namespace} ${project.subprojects.map((item) => item.path).join(' ')} ${languageVersions} ${languages}`.toLowerCase();
  const versionMatches = !state.projectFilters.language || project.subprojects.some((subproject) => (
    subproject.language === state.projectFilters.language
    && normalizedRuntimeVersion(
      subproject.runtime_version || subproject.python_version || subproject.python_constraint,
    ) === state.projectFilters.version
  ));
  const queryMatches = state.projectFilters.language !== null || !query || searchable.includes(query);
  return queryMatches
    && versionMatches
    && rules.every((rule) => project.company_rule_results?.[rule] === false);
}

function normalizedRuntimeVersion(value) {
  const match = value?.match(/(^|\D)(\d+)(?:\.(\d+))?/);
  if (!match) return null;
  return match[3] ? `${match[2]}.${match[3]}` : match[2];
}
function syncProjectFilterControls() {
  document.querySelector('#project-search').value = state.projectFilters.query;
  document.querySelectorAll('.rule-switches input').forEach((input) => {
    input.checked = state.projectFilters.rules.has(input.dataset.rule);
  });
}
function resetProjectFilters() {
  state.projectFilters.query = '';
  state.projectFilters.rules.clear();
  state.projectFilters.language = null;
  state.projectFilters.version = null;
  syncProjectFilterControls();
  if (state.loaded.projects) renderProjects();
}
function projectRegistries(project) {
  const registries = new Set(project.package_registries || []);
  (project.container_images || []).forEach((image) => registries.add(image.registry));
  (project.gitlab_ci_components || []).forEach((component) => registries.add(registryName(component.name)));
  return [...registries].filter(Boolean).sort((left, right) => left.localeCompare(right));
}
function projectViolationTitles(results, requirements) {
  return Object.entries(results || {})
    .filter(([code, passed]) => passed === false && requirements.has(code))
    .map(([code]) => requirements.get(code));
}
function exportFilteredProjects() {
  const requirements = new Map(activeRequirements().map((requirement) => [requirement.code, requirement.title]));
  const projects = state.projects.filter(projectMatchesFilters);
  const rows = projects.map((project) => {
    const root = project.subprojects.find((subproject) => subproject.path === '.');
    const pythonRoot = project.subprojects.find(
      (subproject) => subproject.path === '.' && subproject.language === 'python',
    );
    const pythonVersion = normalizedPythonVersion(pythonRoot?.python_version, pythonRoot?.python_constraint);
    const python = [pythonVersion ? `Python ${pythonVersion}` : null, pythonRoot?.python_constraint]
      .filter(Boolean)
      .join(' · ');
    return [
      project.id,
      project.name,
      project.path_with_namespace,
      project.default_branch || '',
      python,
      root?.package_manager || project.package_manager || '',
      root?.company_compliance_percentage ?? project.company_compliance_percentage ?? 0,
      project.has_docker ? 'Да' : 'Нет',
      project.has_gitlab_ci ? 'Да' : 'Нет',
      projectRegistries(project).join('\n'),
      projectViolationTitles(project.company_rule_results, requirements).join('\n'),
      project.scan_error || '',
      PROJECT_DATA_STATUS_TITLES[project.data_status] || 'Актуальные данные',
      formatDate(project.last_activity_at),
      project.web_url,
    ];
  });
  const date = new Date().toISOString().slice(0, 10);
  downloadXlsx(
    `projects-with-violations-${date}.xlsx`,
    [
      { title: 'ID', width: 12 },
      { title: 'Проект', width: 28 },
      { title: 'Полный путь', width: 42 },
      { title: 'Основная ветка', width: 20 },
      { title: 'Версия Python', width: 30 },
      { title: 'Пакетный менеджер', width: 25 },
      { title: 'Соответствие правилам, %', width: 24 },
      { title: 'Docker', width: 12 },
      { title: 'GitLab CI', width: 12 },
      { title: 'Registry', width: 42 },
      { title: 'Типы нарушений', width: 55 },
      { title: 'Ошибка анализа', width: 45 },
      { title: 'Состояние данных', width: 42 },
      { title: 'Последняя активность', width: 22 },
      { title: 'GitLab URL', width: 48 },
    ],
    rows,
  );
}
function clearProjectSelection() {
  state.selectedId = null;
  state.selectedSubprojectKey = null;
  document.querySelector('#project-detail').replaceChildren(
    element('p', 'empty-state', 'Выберите проект, чтобы посмотреть детали.'),
  );
}
function renderProjects() {
  const projects = state.projects.filter(projectMatchesFilters);
  document.querySelector('#export-projects').disabled = projects.length === 0;
  if (state.selectedId !== null && !projects.some((project) => project.id === state.selectedId)) {
    clearProjectSelection();
  }
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
    row.className = `project-row${selectedProject && state.selectedSubprojectKey === (view.root?.key || null) ? ' active' : ''}`;
    row.type = 'button';
    const identity = element('span');
    identity.append(element('strong', '', project.name), element('small', '', projectPathParts(project.path_with_namespace).join(' › ')));
    const languages = sortedProjectLanguages(project);
    if (languages.length) {
      identity.append(element(
        'small',
        'project-language-summary',
        languages.map((language) => `${language.name} ${formatLanguagePercentage(language.percentage)}%`).join(' · '),
      ));
    }
    const versionSummary = projectVersionSummary(project);
    if (versionSummary) appendProjectCardSummary(identity, 'Версии', versionSummary);
    const managerSummary = projectPackageManagerSummary(project);
    if (managerSummary) appendProjectCardSummary(identity, 'Пакетные менеджеры', managerSummary);
    const frameworkSummary = projectFrameworkSummary(project);
    if (frameworkSummary) appendProjectCardSummary(identity, 'Фреймворки', frameworkSummary);
    if (project.is_empty) identity.append(element('small', 'empty-project-status', 'Пустой проект'));
    if (PROJECT_DATA_STATUS_TITLES[project.data_status]) {
      identity.append(element(
        'small',
        `project-data-status ${project.data_status}`,
        PROJECT_DATA_STATUS_TITLES[project.data_status],
      ));
    }
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
        child.className = `project-child${selectedProject && state.selectedSubprojectKey === subproject.key ? ' active' : ''}`;
        child.type = 'button';
        const childPath = subproject.isRoot
          ? `Корневой модуль · ${subproject.language}`
          : projectPathParts(subproject.path).join(' › ');
        child.append(element('span', '', childPath), packageManagerBadge(subproject.packageManager));
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
function sortedProjectLanguages(project) {
  return [...(project.languages || [])]
    .sort((left, right) => right.percentage - left.percentage || left.name.localeCompare(right.name));
}
function formatLanguagePercentage(value) {
  return Number(value).toLocaleString('ru-RU', { maximumFractionDigits: 1 });
}

function projectTechnologyGroups(project, valueProvider) {
  const languageNames = new Map(
    (project.languages || []).map((language) => [language.code, language.name]),
  );
  const valuesByLanguage = new Map();
  project.subprojects.forEach((subproject) => {
    const value = valueProvider(subproject);
    if (!value) return;
    const language = subproject.language || 'python';
    if (!valuesByLanguage.has(language)) valuesByLanguage.set(language, new Set());
    valuesByLanguage.get(language).add(value);
  });
  return [...valuesByLanguage.entries()]
    .map(([code, values]) => ({
      name: languageNames.get(code) || code,
      values: [...values].sort((left, right) => left.localeCompare(right, undefined, { numeric: true })),
    }))
    .sort((left, right) => left.name.localeCompare(right.name));
}

function projectVersionSummary(project) {
  return projectTechnologyGroups(
    project,
    (subproject) => normalizedRuntimeVersion(
      subproject.runtime_version || subproject.python_version || subproject.python_constraint,
    ),
  ).map((item) => `${item.name}: ${item.values.join(', ')}`).join(' · ');
}

function projectPackageManagerSummary(project) {
  return projectTechnologyGroups(
    project,
    (subproject) => (subproject.package_manager === 'unknown' ? null : subproject.package_manager),
  ).map((item) => `${item.name}: ${item.values.join(', ')}`).join(' · ');
}

function projectFrameworkSummary(project) {
  return [...(project.frameworks || [])]
    .sort((left, right) => left.language.localeCompare(right.language) || left.name.localeCompare(right.name))
    .map((framework) => `${framework.name} (${framework.language})`)
    .join(' · ');
}

function appendProjectCardSummary(container, label, value) {
  container.append(element('small', 'project-technology-summary', `${label}: ${value}`));
}
function appendProjectLanguages(container, project) {
  const languages = sortedProjectLanguages(project);
  if (!languages.length) return;
  const list = element('div', 'project-language-list');
  languages.forEach((language) => {
    const row = element('div', 'project-language-row');
    const track = element('span', 'project-language-track');
    const value = element('i');
    value.style.width = `${Math.min(Math.max(language.percentage, 0), 100)}%`;
    track.append(value);
    row.append(
      element('strong', '', language.name),
      track,
      element('b', '', `${formatLanguagePercentage(language.percentage)}%`),
    );
    list.append(row);
  });
  appendDetail(container, 'Языки программирования', list);
}
function appendProjectFrameworks(container, project) {
  if (!project.frameworks?.length) return;
  const badges = element('div', 'dependency-badges');
  project.frameworks.forEach((framework) => {
    const badge = element('span', 'dependency-badge project-framework-badge');
    badge.append(element('strong', '', framework.name), element('span', '', framework.language));
    badges.append(badge);
  });
  appendDetail(container, 'Фреймворки', badges);
}
function appendProjectVersions(container, project) {
  const summary = projectVersionSummary(project);
  if (summary) appendDetail(container, 'Версии языков', summary);
}
function appendProjectPackageManagers(container, project) {
  const summary = projectPackageManagerSummary(project);
  if (summary) appendDetail(container, 'Пакетные менеджеры', summary);
}
function appendEmptyProjectStatus(container, project) {
  if (!project.is_empty) return;
  appendDetail(container, 'Статус', element('span', 'empty-project-badge', 'Пустой'));
}
function appendProjectDataStatus(container, project) {
  const title = PROJECT_DATA_STATUS_TITLES[project.data_status];
  if (!title) return;
  appendDetail(container, 'Состояние данных', element(
    'span',
    `project-data-status-badge ${project.data_status}`,
    title,
  ));
}
function packageManagerBadge(value) {
  const badge = element('span', 'status-badge', value || '—');
  badge.classList.add(value === 'uv' ? 'manager-uv' : value === 'pip' ? 'manager-pip' : 'manager-other');
  return badge;
}
function dependencyBadge(dependency, onClick = null) {
  const badge = element(onClick ? 'button' : 'span', `dependency-badge${onClick ? ' dependency-badge-link' : ''}`);
  if (onClick) {
    badge.type = 'button';
    badge.addEventListener('click', onClick);
  }
  badge.append(element('strong', '', dependency.name));
  if (dependency.version) badge.append(element('span', '', dependency.version));
  return badge;
}
function dependencyGroup(title, dependencies) {
  const group = element('section', 'dependency-group');
  group.append(element('h4', '', title));
  const items = element('div', 'dependency-badges');
  dependencies.forEach((dependency) => items.append(dependencyBadge(dependency, () => openDependency(dependency.name, 'python'))));
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
  const componentsByRegistry = new Map();
  project.gitlab_ci_components.forEach((component) => {
    const registry = registryName(component.name);
    if (!componentsByRegistry.has(registry)) componentsByRegistry.set(registry, []);
    componentsByRegistry.get(registry).push(component);
  });
  const registryList = element('div', 'image-registry-list');
  [...componentsByRegistry.entries()]
    .sort(([left], [right]) => left.localeCompare(right))
    .forEach(([registry, components]) => {
      const group = element('section', 'image-registry-group');
      const badges = element('div', 'dependency-badges');
      components.forEach((component) => badges.append(dependencyBadge(
        { ...component, name: projectPathParts(component.name).slice(-3).join('/') || component.name },
        () => openDependency(component.name, 'ci'),
      )));
      group.append(element('h4', '', registry), badges);
      registryList.append(group);
    });
  appendDetail(container, 'Компоненты GitLab CI по registry', registryList);
}
function appendContainerImages(container, project) {
  if (!project.container_images?.length) return;
  const imagesByRegistry = new Map();
  project.container_images.forEach((image) => {
    if (!imagesByRegistry.has(image.registry)) imagesByRegistry.set(image.registry, []);
    imagesByRegistry.get(image.registry).push(image);
  });
  const registryList = element('div', 'image-registry-list');
  [...imagesByRegistry.entries()]
    .sort(([left], [right]) => left.localeCompare(right))
    .forEach(([registry, images]) => {
      const group = element('section', 'image-registry-group');
      const badges = element('div', 'dependency-badges');
      images.forEach((image) => badges.append(dependencyBadge(
        { name: image.image, version: image.version },
        () => openDependency(`${image.registry}/${image.image}`, 'docker'),
      )));
      group.append(element('h4', '', registry), badges);
      registryList.append(group);
  });
  appendDetail(container, 'Образы Docker по registry', registryList);
}
function appendProjectHooks(container, project) {
  if (!project.webhooks_accessible) return;
  if (!project.webhooks?.length) {
    appendDetail(container, 'Webhooks', 'Не настроены');
    return;
  }
  const hooks = element('div', 'webhook-list');
  project.webhooks.forEach((hook) => {
    const entry = element('button', 'webhook-entry');
    entry.type = 'button';
    entry.append(element('strong', '', hook.name || hook.url));
    if (hook.name) entry.append(element('small', '', hook.url));
    entry.append(element(
      'small',
      '',
      hook.events.map((event) => HOOK_EVENT_TITLES[event] || event).join(', ') || 'События не выбраны',
    ));
    entry.addEventListener('click', () => openDependency(hook.url, 'webhook'));
    hooks.append(entry);
  });
  appendDetail(container, 'Webhooks', hooks);
}
function normalizedPythonVersion(...values) {
  for (const value of values) {
    const match = value?.match(/(^|\D)(\d+)\.(\d+)/);
    if (match) return `${match[2]}.${match[3]}`;
  }
  return null;
}
function appendTechnologyStatuses(container, project) {
  const statuses = element('div', 'technology-statuses');
  [['Docker', project.has_docker], ['GitLab CI', project.has_gitlab_ci]].forEach(([title, enabled]) => {
    const status = element('span', `technology-status ${enabled ? 'enabled' : 'disabled'}`);
    status.append(element('b', '', enabled ? '✓' : '×'), element('span', '', title));
    statuses.append(status);
  });
  appendDetail(container, 'Технологии', statuses);
}
function appendRuleViolations(container, results) {
  const violations = activeRequirements()
    .filter((requirement) => results?.[requirement.code] === false)
    .map((requirement) => requirement.title);
  if (!violations.length) return;
  const badges = element('div', 'rule-violations');
  violations.forEach((title) => badges.append(element('span', '', title)));
  appendDetail(container, 'Не выполнены правила', badges);
}
function renderProjectDetail(view, subproject) {
  const { project } = view;
  const detail = document.querySelector('#project-detail');
  detail.replaceChildren();
  if (!subproject) {
    const message = project.is_empty
      ? 'Языки программирования не обнаружены.'
      : 'Для обнаруженных языков анализаторы не сформировали модули.';
    detail.append(element('h3', '', project.name), element('p', 'empty-state', message));
    appendProjectPath(detail, project.path_with_namespace);
    appendDetail(detail, 'Основная ветка', project.default_branch);
    appendEmptyProjectStatus(detail, project);
    appendProjectDataStatus(detail, project);
    appendProjectLanguages(detail, project);
    appendProjectVersions(detail, project);
    appendProjectPackageManagers(detail, project);
    appendProjectFrameworks(detail, project);
    const compliance = element('p', 'detail-value compliance-value', `${project.company_compliance_percentage || 0}%`);
    compliance.classList.add(`compliance-${complianceTone(project.company_compliance_percentage || 0, 'project_compliance_thresholds')}`);
    appendDetail(detail, 'Соответствие правилам компании', compliance);
    appendTechnologyStatuses(detail, project);
    appendRuleViolations(detail, project.company_rule_results);
    appendGitLabComponents(detail, project);
    appendContainerImages(detail, project);
    appendProjectHooks(detail, project);
    return;
  }
  detail.append(element('h3', '', subproject.title));
  appendDetail(detail, 'ID', String(project.id));
  appendProjectPath(detail, subproject.fullPath);
  appendDetail(detail, 'Основная ветка', project.default_branch);
  appendEmptyProjectStatus(detail, project);
  appendProjectDataStatus(detail, project);
  appendProjectLanguages(detail, project);
  appendProjectVersions(detail, project);
  appendProjectPackageManagers(detail, project);
  appendProjectFrameworks(detail, project);
  const compliance = element('p', 'detail-value compliance-value', `${subproject.compliance}%`);
  compliance.classList.add(`compliance-${complianceTone(subproject.compliance, 'project_compliance_thresholds')}`);
  appendDetail(detail, 'Соответствие правилам компании', compliance);
  appendTechnologyStatuses(detail, project);
  appendRuleViolations(detail, subproject.ruleResults);
  appendProjectDependencies(detail, subproject);
  appendGitLabComponents(detail, project);
  appendContainerImages(detail, project);
  appendProjectHooks(detail, project);
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
  state.selectedSubprojectKey = subproject?.key || null;
  document.querySelectorAll('.project-row.active, .project-child.active').forEach((node) => node.classList.remove('active'));
  row.classList.add('active');
  renderProjectDetail(view, subproject);
}


async function loadProjects() {
  const [projects] = await Promise.all([api(API.projects), ensureRequirements(), ensureParameters()]);
  state.projects = projects.sort(compareProjectsByScanTime);
  state.loaded.projects = true;
  renderProjects();
  const selected = state.projects.find((project) => project.id === state.selectedId);
  if (selected) {
    const view = projectView(selected);
    const entries = [view.root, ...view.children].filter(Boolean);
    const subproject = entries.find((item) => item.key === state.selectedSubprojectKey) || view.root;
    state.selectedSubprojectKey = subproject?.key || null;
    renderProjectDetail(view, subproject);
  }
  if (state.auth.user) await connectScanStatusSocket();
}

async function upsertScannedProject(projectId) {
  if (!state.loaded.projects || projectId === null || projectId === undefined) return;
  const project = await api(`${API.projects}${projectId}`);
  if (!project) return;
  const existingIndex = state.projects.findIndex((item) => item.id === project.id);
  if (existingIndex >= 0) state.projects.splice(existingIndex, 1, project);
  else state.projects.push(project);
  renderProjects();
  if (state.selectedId === project.id) {
    const view = projectView(project);
    const entries = [view.root, ...view.children].filter(Boolean);
    const subproject = entries.find((item) => item.key === state.selectedSubprojectKey) || view.root;
    state.selectedSubprojectKey = subproject?.key || null;
    renderProjectDetail(view, subproject);
  }
}

