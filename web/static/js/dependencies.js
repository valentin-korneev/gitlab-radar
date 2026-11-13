import { api } from './api.js';
import { catalogAdapter } from './catalog-adapters.js';
import { API, LEVEL_TITLES, SOURCE_ROUTES } from './config.js';
import { appendDetail, renderProjects, syncProjectFilterControls } from './projects.js';
import { readLatest } from './requests.js';
import { ensurePageLoaded } from './navigation.js';
import { canonicalLanguageCode, element, languageDisplayName, maskWebhookText } from './shared.js';
import { activateCatalog, catalogState, projectState, state } from './state.js';

function renderDependencies() {
  if (catalogAdapter(catalogState.source).tree) {
    renderEndpointDependencies();
    return;
  }
  const query = catalogState.dependencyQuery.trim().toLowerCase();
  const dependencies = catalogState.dependencies
    .map((dependency) => ({ dependency, visible: visibleDependencyData(dependency) }))
    .filter(({ dependency, visible }) => {
      const searchable = catalogState.source === 'webhook'
        ? [dependency.name, ...dependency.versions.map((version) => version.version || '')]
        : [dependency.name];
      return searchable.some((value) => (
        catalogState.source === 'webhook' ? maskWebhookText(value) : value
      ).toLowerCase().includes(query)) && visible.projectsCount;
    });
  if (catalogState.selectedDependency && !dependencies.some(({ dependency }) => dependency.name === catalogState.selectedDependency)) {
    clearDependencySelection();
  }
  const list = document.querySelector('#dependency-list');
  list.replaceChildren();
  if (!dependencies.length) {
    list.append(element('p', 'empty-state', catalogState.dependencies.length ? 'Элементы не найдены.' : 'Список пуст.'));
    return;
  }
  dependencies.forEach(({ dependency, visible }) => {
    const row = element('button');
    row.type = 'button';
    row.className = `dependency-row${dependency.name === catalogState.selectedDependency ? ' active' : ''}`;
    const identity = element('span');
    const levels = visible.levels.map((level) => LEVEL_TITLES[level]).join(', ');
    const metadata = catalogState.source === 'python'
      ? `${visible.languages.map((language) => languageDisplayName(language)).join(', ') || 'язык не указан'} · ${levels} · вариантов версий: ${visible.versions.length}`
      : catalogState.source === 'webhook'
        ? `хуков: ${visible.versions.length}`
        : `вариантов версий: ${visible.versions.length}`;
    identity.append(element('strong', '', dependency.name), element('small', '', metadata));
    row.append(identity, element('b', '', visible.projectsCount));
    row.addEventListener('click', () => selectDependency(dependency, row));
    list.append(row);
  });
}
function renderEndpointDependencies() {
  const source = catalogState.source;
  const query = catalogState.dependencyQuery.trim().toLowerCase();
  const roots = new Map();
  const nodes = new Map();
  catalogState.dependencies.forEach((dependency) => {
    const adapter = catalogAdapter(source);
    dependency.versions.forEach((version) => {
      const matchesQuery = !query || adapter.searchTerms(dependency, version)
        .some((value) => value.toLowerCase().includes(query));
      const { domain, endpoint } = adapter.path(dependency, version);
      if (!domain) return;
      let node = roots.get(domain);
      if (!node) {
        node = createEndpointTreeNode(source, [domain]);
        roots.set(domain, node);
      }
      let path = [domain];
      endpoint.forEach((segment) => {
        path = [...path, segment];
        let child = node.children.get(segment);
        if (!child) {
          child = createEndpointTreeNode(source, path);
          child.parent = node;
          node.children.set(segment, child);
        }
        node = child;
      });
      addEndpointTreeEntry(node, adapter.entryVersion(version), version.projects, matchesQuery);
    });
  });
  roots.forEach((node) => {
    countEndpointTreeProjects(node);
    setEndpointTreeVisibility(node, query);
  });
  const orderedRoots = [...roots.values()].filter((node) => node.visible).sort(compareEndpointTreeNodes);
  const list = document.querySelector('#dependency-list');
  list.replaceChildren();
  if (!orderedRoots.length) {
    list.append(element('p', 'empty-state', catalogState.dependencies.length ? 'Элементы не найдены.' : 'Список пуст.'));
    if (catalogState.selectedDependency) clearDependencySelection();
    return;
  }
  const registerNodes = (node) => {
    node.fullPath = node.parent ? `${node.parent.fullPath}/${node.segment}` : node.segment;
    nodes.set(node.key, node);
    node.visibleChildren.forEach(registerNodes);
  };
  orderedRoots.forEach(registerNodes);
  let selectedNode = nodes.get(catalogState.selectedDependency);
  if (!selectedNode && catalogState.selectedDependency) {
    selectedNode = [...nodes.values()].find((node) => (
      node.fullPath === catalogState.selectedDependency
      || (!node.parent && node.segment === catalogState.selectedDependency)
    ));
    if (selectedNode) {
      catalogState.selectedDependency = selectedNode.key;
      for (let parent = selectedNode.parent; parent; parent = parent.parent) {
        catalogState.dependencyTreeExpanded.add(parent.key);
      }
    }
  }
  if (catalogState.selectedDependency && !selectedNode) clearDependencySelection();
  const selectedPath = new Set();
  for (let node = selectedNode; node; node = node.parent) selectedPath.add(node.key);
  orderedRoots.forEach((node) => renderEndpointTreeNode(node, list, source, selectedPath));
  if (selectedNode) renderDependencyDetail(endpointTreeDependency(selectedNode, source));
}
function createEndpointTreeNode(source, path) {
  return {
    key: JSON.stringify([source, ...path]),
    segment: path[path.length - 1],
    path,
    parent: null,
    children: new Map(),
    entries: new Map(),
  };
}
function addEndpointTreeEntry(node, version, projects, matchesQuery) {
  const key = version ?? '';
  if (!node.entries.has(key)) node.entries.set(key, { version, projects: new Map(), matchesQuery: false });
  const entry = node.entries.get(key);
  entry.matchesQuery ||= matchesQuery;
  projects.forEach((project) => {
    entry.projects.set(`${project.id}:${project.subproject_path}`, project);
  });
}
function countEndpointTreeProjects(node) {
  const projectIds = new Set();
  node.entries.forEach((entry) => entry.projects.forEach((project) => projectIds.add(project.id)));
  node.children.forEach((child) => countEndpointTreeProjects(child).forEach((id) => projectIds.add(id)));
  node.projectsCount = projectIds.size;
  return projectIds;
}
function setEndpointTreeVisibility(node, query) {
  node.visibleChildren = [...node.children.values()]
    .filter((child) => setEndpointTreeVisibility(child, query))
    .sort(compareEndpointTreeNodes);
  node.visible = !query || [...node.entries.values()].some((entry) => entry.matchesQuery) || node.visibleChildren.length > 0;
  return node.visible;
}
function compareEndpointTreeNodes(left, right) {
  const leftHasChildren = left.children.size > 0;
  const rightHasChildren = right.children.size > 0;
  if (leftHasChildren !== rightHasChildren) return leftHasChildren ? -1 : 1;
  return right.projectsCount - left.projectsCount || left.segment.localeCompare(right.segment);
}
function endpointTreeRecords(node, relativePath = []) {
  const records = [...node.entries.values()].map((entry) => ({
    path: relativePath,
    version: entry.version,
    projects: [...entry.projects.values()],
  }));
  node.children.forEach((child) => records.push(...endpointTreeRecords(child, [...relativePath, child.segment])));
  return records;
}
function endpointTreeProjectCount(node) {
  return node.projectsCount;
}
function endpointTreeDependency(node, source) {
  const records = endpointTreeRecords(node);
  const versions = records.map((record) => ({
    version: [record.path.join('/'), record.version].filter(Boolean).join(' · ') || null,
    projects: record.projects,
  }));
  return {
    name: node.fullPath,
    level: 'direct',
    levels: ['direct'],
    projects_count: endpointTreeProjectCount(node),
    languages: [],
    versions,
  };
}
function renderEndpointTreeNode(node, container, source, selectedPath) {
  const inSelectionPath = selectedPath.has(node.key);
  const wrapper = element('div', `dependency-tree-node${inSelectionPath ? ' in-selection-path' : ''}`);
  const row = element('div', 'dependency-tree-row');
  const hasChildren = node.visibleChildren.length > 0;
  if (hasChildren) {
    const toggle = element('button', 'dependency-tree-toggle', catalogState.dependencyTreeExpanded.has(node.key) ? '−' : '+');
    toggle.type = 'button';
    toggle.setAttribute('aria-label', `${catalogState.dependencyTreeExpanded.has(node.key) ? 'Свернуть' : 'Раскрыть'} ${maskWebhookText(node.segment)}`);
    toggle.setAttribute('aria-expanded', String(catalogState.dependencyTreeExpanded.has(node.key)));
    toggle.addEventListener('click', () => {
      if (catalogState.dependencyTreeExpanded.has(node.key)) catalogState.dependencyTreeExpanded.delete(node.key);
      else catalogState.dependencyTreeExpanded.add(node.key);
      renderDependencies();
    });
    row.append(toggle);
  } else row.append(element('span', 'dependency-tree-spacer'));
  const isSelected = catalogState.selectedDependency === node.key;
  const select = element('button', `dependency-tree-select${isSelected ? ' active' : ''}${inSelectionPath ? ' in-selection-path' : ''}`);
  select.type = 'button';
  select.setAttribute('aria-pressed', String(isSelected));
  select.append(element('span', '', node.segment));
  select.append(element('b', '', String(endpointTreeProjectCount(node))));
  select.addEventListener('click', () => {
    catalogState.selectedDependency = node.key;
    renderDependencies();
  });
  row.append(select);
  wrapper.append(row);
  if (hasChildren) {
    const children = element('div', 'dependency-tree-children');
    children.hidden = !catalogState.dependencyTreeExpanded.has(node.key);
    node.visibleChildren.forEach((child) => renderEndpointTreeNode(child, children, source, selectedPath));
    wrapper.append(children);
  }
  container.append(wrapper);
}
function clearDependencySelection() {
  catalogState.selectedDependency = null;
  document.querySelector('#dependency-detail').replaceChildren(
    element('p', 'empty-state', 'Выберите элемент, чтобы посмотреть версии и проекты.'),
  );
}
function resetDependencyPage() {
  catalogState.dependencyQuery = '';
  catalogState.showTransitive = false;
  catalogState.dependencyLanguages.clear();
  catalogState.dependencyLanguagesInitialized = false;
  document.querySelector('#dependency-search').value = '';
  document.querySelector('#show-transitive').checked = false;
  clearDependencySelection();
}
function visibleDependencyData(dependency) {
  const versions = dependency.versions
    .map((version) => ({
      ...version,
      projects: version.projects.filter((project) => (
        (catalogState.source !== 'python' || catalogState.showTransitive || project.level !== 'transitive')
        && (catalogState.source !== 'python'
          || catalogState.dependencyLanguages.has(canonicalLanguageCode(project.language)))
      )),
    }))
    .filter((version) => version.projects.length);
  const projects = versions.flatMap((version) => version.projects);
  const levels = [...new Set(projects.map((project) => project.level))];
  return {
    versions,
    levels: dependency.levels.filter((level) => levels.includes(level)),
    languages: [...new Set(
      projects.map((project) => canonicalLanguageCode(project.language)).filter(Boolean),
    )].sort(),
    projectsCount: new Set(projects.map((project) => project.id)).size,
  };
}
function renderDependencyDetail(dependency) {
  const detail = document.querySelector('#dependency-detail');
  detail.replaceChildren();
  const visible = visibleDependencyData(dependency);
  detail.append(element('h3', '', dependency.name));
  if (catalogState.source === 'python') appendDetail(detail, 'Типы использования', visible.levels.map((level) => LEVEL_TITLES[level]).join(', '));
  if (catalogState.source === 'python') {
    appendDetail(detail, 'Языки', visible.languages.map((language) => languageDisplayName(language)).join(', '));
  }
  appendDetail(detail, 'Используется в проектах', String(visible.projectsCount));
  const versions = element('div', 'dependency-versions');
  visible.versions.forEach((version) => {
    const group = element('section', 'dependency-version');
    const versionTitle = catalogAdapter(catalogState.source).versionTitle(version);
    group.append(element('h4', '', versionTitle));
    const projects = element('div', 'dependency-projects');
    version.projects.forEach((project) => {
      const link = element('a', 'dependency-project');
      link.href = project.web_url;
      link.target = '_blank';
      link.rel = 'noreferrer';
      link.append(
        element('strong', '', project.path_with_namespace),
        element('small', '', `${project.subproject_path === '.' ? 'Корень репозитория' : project.subproject_path}${catalogState.source === 'python' ? ` · ${languageDisplayName(project.language || '', project.language || 'язык не указан')} · ${LEVEL_TITLES[project.level]}` : ''}`),
      );
      projects.append(link);
    });
    group.append(projects);
    versions.append(group);
  });
  detail.append(versions);
}
function selectDependency(dependency, row) {
  catalogState.selectedDependency = dependency.name;
  document.querySelector('.dependency-row.active')?.classList.remove('active');
  row.classList.add('active');
  renderDependencyDetail(dependency);
}
let dependencyLoadId = 0;
async function loadDependencies() {
  const source = catalogState.source;
  const version = state.dataVersion;
  const loadId = ++dependencyLoadId;
  let cache = state.dependencyCache;
  while (!cache[source]) {
    let dependencies;
    try {
      dependencies = await readLatest('dependencies', (signal) => api(`${API.dependencies}?source=${source}`, { signal }));
      if (!dependencies) return;
    } catch (error) {
      if (loadId !== dependencyLoadId || source !== catalogState.source || version !== state.dataVersion) return;
      if (cache !== state.dependencyCache) {
        cache = state.dependencyCache;
        continue;
      }
      throw error;
    }
    if (loadId !== dependencyLoadId || source !== catalogState.source || version !== state.dataVersion) return;
    if (cache !== state.dependencyCache) {
      cache = state.dependencyCache;
      continue;
    }
    cache[source] = dependencies;
  }
  catalogState.dependencies = cache[source];
  const languages = [...new Set(
    catalogState.dependencies.flatMap((dependency) => dependency.languages || []).map(canonicalLanguageCode),
  )].sort();
  if (!catalogState.dependencyLanguagesInitialized) {
    catalogState.dependencyLanguages = new Set(languages);
    catalogState.dependencyLanguagesInitialized = true;
  } else {
    catalogState.dependencyLanguages = new Set(
      [...catalogState.dependencyLanguages]
        .map(canonicalLanguageCode)
        .filter((language) => languages.includes(language)),
    );
  }
  renderDependencyLanguageOptions(languages);
  state.loaded.dependencies = true;
  renderDependencies();
  const selected = catalogState.dependencies.find((dependency) => dependency.name === catalogState.selectedDependency);
  if (selected) renderDependencyDetail(selected);
}
function renderDependencyLanguageOptions(languages) {
  const options = document.querySelector('#dependency-language-options');
  options.replaceChildren(...languages.map((language) => {
    const label = element('label', 'requirement-language-option');
    const input = element('input');
    input.type = 'checkbox';
    input.checked = catalogState.dependencyLanguages.has(language);
    input.addEventListener('change', () => {
      if (input.checked) catalogState.dependencyLanguages.add(language);
      else catalogState.dependencyLanguages.delete(language);
      renderDependencies();
      const selected = catalogState.dependencies.find((dependency) => dependency.name === catalogState.selectedDependency);
      if (selected) renderDependencyDetail(selected);
    });
    label.append(input, element('span', '', languageDisplayName(language)));
    return label;
  }));
  if (!languages.length) options.append(element('small', 'muted', 'Нет языков'));
}
async function openDependency(name, source = 'python') {
  activateCatalog(source);
  document.querySelector('#transitive-filter').classList.toggle('control-placeholder', source !== 'python');
  catalogState.selectedDependency = name;
  const route = SOURCE_ROUTES[source];
  if (window.location.hash !== `#${route}`) {
    window.location.hash = route;
    return;
  }
  await loadDependencies();
}
async function openRuleViolations(code) {
  projectState.projectFilters.query = '';
  projectState.projectFilters.rules = new Set([code]);
  projectState.projectFilters.language = null;
  projectState.projectFilters.version = null;
  syncProjectFilterControls();
  window.location.hash = 'projects';
  await ensurePageLoaded('projects');
  renderProjects();
}
async function openLanguageVersion(language, version) {
  projectState.projectFilters.rules.clear();
  projectState.projectFilters.query = `${language.name} ${version}`;
  projectState.projectFilters.language = language.code;
  projectState.projectFilters.version = version;
  syncProjectFilterControls();
  if (window.location.hash !== '#projects') {
    window.location.hash = 'projects';
  }
  await ensurePageLoaded('projects');
  renderProjects();
}


export { loadDependencies, openDependency, openLanguageVersion, openRuleViolations, renderDependencies, renderDependencyDetail, resetDependencyPage };
