function compactStatRow(label, value) {
  const row = element('div');
  row.append(element('span', '', label), element('b', '', String(value)));
  return row;
}
function languageVersionLink(language, item) {
  const row = element(language.code === 'python' ? 'button' : 'div', 'compact-stat-link');
  if (language.code === 'python') row.type = 'button';
  const oldestCurrent = state.languageOldestCurrentVersions[language.code];
  if (oldestCurrent) {
    const comparison = compareVersions(item.name, oldestCurrent);
    if (comparison < 0) row.classList.add('python-version-danger');
    else if (comparison === 0) row.classList.add('python-version-warning');
  }
  row.append(element('span', '', item.name), element('b', '', String(item.projects_count)));
  if (language.code === 'python') {
    row.addEventListener('click', () => openPythonVersion(item.name));
  }
  return row;
}
function parameterValue(key) {
  return state.parameters.find((parameter) => parameter.key === key)?.value || '';
}
function parameterRange(key) {
  return parameterValue(key).split(',').map(Number);
}
function complianceTone(value, parameterKey) {
  const [dangerThreshold, successThreshold] = parameterRange(parameterKey);
  if (value < dangerThreshold) return 'danger';
  if (value < successThreshold) return 'warning';
  return 'success';
}
function compareVersions(left, right) {
  const leftParts = left.split('.').map(Number);
  const rightParts = right.split('.').map(Number);
  return (leftParts[0] || 0) - (rightParts[0] || 0) || (leftParts[1] || 0) - (rightParts[1] || 0);
}
function stableFraction(value) {
  let hash = 2166136261;
  for (const character of value) {
    hash ^= character.codePointAt(0);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0) / 4294967295;
}
function technologyVisibleForLanguages(item) {
  if (!(item.languages || []).length) return true;
  return item.languages.some((language) => state.technologyTargetLanguages.has(language));
}
function renderTechnologyTarget(target, projectsCount) {
  const definitions = [
    ['Языки', target.languages], ['Зависимости', target.dependencies],
    ['Образы', target.images], ['Registry', target.registries],
  ];
  const markers = document.querySelector('#target-markers');
  const scaleMaximum = Math.max(Math.ceil(projectsCount * 1.1), 1);
  const markerNodes = definitions.flatMap(([category, sourceItems], categoryIndex) => {
    const items = sourceItems
      .filter((item) => categoryIndex >= 2 || technologyVisibleForLanguages(item))
      .filter((item) => state.showSingleTechnologies || item.projects_count > 1);
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
      const tooltip = `${category} · ${item.name} · Проектов: ${item.projects_count}`;
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
function renderTargetLanguageFilter(languages) {
  state.technologyTargetLanguageOptions = languages;
  const available = new Set(languages.map((language) => language.code));
  state.technologyTargetLanguages = new Set(
    [...state.technologyTargetLanguages].filter((language) => available.has(language)),
  );
  if (!state.technologyTargetLanguagesInitialized) {
    state.technologyTargetLanguages = new Set(available);
    state.technologyTargetLanguagesInitialized = true;
  }
  const container = document.querySelector('#target-language-filter');
  const definitions = [{ code: 'all', name: 'Все' }, ...languages];
  container.replaceChildren(...definitions.map((language) => {
    const label = element('label', 'requirement-language-option');
    const input = element('input');
    input.type = 'checkbox';
    input.checked = language.code === 'all'
      ? state.technologyTargetLanguages.size === available.size
      : state.technologyTargetLanguages.has(language.code);
    input.addEventListener('change', () => {
      if (language.code === 'all') {
        state.technologyTargetLanguages = input.checked ? new Set(available) : new Set();
      } else if (input.checked) state.technologyTargetLanguages.add(language.code);
      else state.technologyTargetLanguages.delete(language.code);
      renderTargetLanguageFilter(languages);
      renderTechnologyTarget(state.technologyTarget, state.projectsCount);
    });
    label.append(input, element('span', '', language.name));
    return label;
  }));
}
function renderDependencyCountMatrix(statistics) {
  const container = document.querySelector('#dependency-count-matrix');
  if (!statistics.languages.length) {
    container.replaceChildren(element('p', 'empty-state', 'Нет включенных языков со статистикой.'));
    return;
  }
  const table = element('table', 'dependency-matrix-table');
  const head = element('thead');
  const headRow = element('tr');
  headRow.append(element('th', '', 'Тип'));
  statistics.languages.forEach((language) => headRow.append(element('th', '', language.name)));
  headRow.append(element('th', 'dependency-matrix-total', 'Итого'));
  head.append(headRow);
  const body = element('tbody');
  statistics.levels.forEach((level) => {
    const row = element('tr');
    row.append(element('th', '', level.title));
    statistics.languages.forEach((language) => {
      row.append(element('td', '', String(level.by_language[language.code] || 0)));
    });
    row.append(element('td', 'dependency-matrix-total', String(level.total)));
    body.append(row);
  });
  table.append(head, body);
  container.replaceChildren(table);
}
function renderLanguageStatistics(languages) {
  const container = document.querySelector('#language-stats');
  container.replaceChildren();
  languages.forEach((item) => {
    const row = element('div', `language-statistics-row${item.enabled ? '' : ' disabled'}`);
    const heading = element('div', 'language-statistics-heading');
    heading.append(element('strong', '', item.name), element('span', '', `${item.percentage}%`));
    const track = element('div', 'language-statistics-track');
    const value = element('span');
    value.style.width = `${item.percentage}%`;
    track.append(value);
    row.append(heading, track, element('b', '', String(item.projects_count)));
    container.append(row);
  });
  if (!languages.length) container.append(element('p', 'empty-state', 'Языки еще не определены.'));
}
function renderLanguageTechnologyCards(statistics) {
  const container = document.querySelector('#language-technology-cards');
  const groups = [];
  statistics.forEach((language) => {
    const group = element('div', 'language-technology-group');
    const managersCard = element('article', 'dashboard-card');
    const managersHeading = element('div', 'card-heading');
    managersHeading.append(element('p', '', `${language.name} · пакетные менеджеры`));
    const managers = element('div', 'compact-list');
    managers.append(...language.package_managers.map(
      (item) => compactStatRow(item.name === 'unknown' ? 'Не определен' : item.name, item.projects_count),
    ));
    const versionsCard = element('article', 'dashboard-card');
    const versionsHeading = element('div', 'card-heading');
    versionsHeading.append(element('p', '', `${language.name} · версии`));
    const versions = element('div', 'compact-list');
    if (language.versions.length) {
      versions.append(...language.versions.map((item) => languageVersionLink(language, item)));
    } else {
      versions.append(compactStatRow('Не определено', language.projects_count));
    }
    managersCard.append(managersHeading, managers);
    versionsCard.append(versionsHeading, versions);
    group.append(managersCard, versionsCard);
    groups.push(group);
  });
  container.replaceChildren(...groups);
}
function renderFrameworks(frameworks) {
  const container = document.querySelector('#framework-bubbles');
  if (!frameworks.length) {
    container.replaceChildren(element('p', 'empty-state', 'Фреймворки не обнаружены.'));
    return;
  }
  const maximum = Math.max(...frameworks.map((item) => item.projects_count), 1);
  container.replaceChildren(...frameworks.map((item) => {
    const bubble = element('div', 'framework-bubble');
    const size = 74 + Math.sqrt(item.projects_count / maximum) * 82;
    bubble.style.setProperty('--bubble-size', `${size}px`);
    bubble.style.setProperty('--bubble-hue', String(Math.floor(stableFraction(item.code) * 360)));
    const tooltip = `${item.name} · ${item.language} · Проектов: ${item.projects_count}`;
    bubble.dataset.tooltip = tooltip;
    bubble.setAttribute('aria-label', tooltip);
    bubble.tabIndex = 0;
    bubble.append(element('b', '', String(item.projects_count)));
    return bubble;
  }));
}
function renderRegistryStatistics(items) {
  const container = document.querySelector('#registry-stats');
  container.replaceChildren(...items.slice(0, 15).map((item) => compactStatRow(item.name, item.projects_count)));
  if (!items.length) {
    container.append(element('p', 'empty-state', 'Registry не обнаружены.'));
  }
}
function renderDashboard(dashboard) {
  document.querySelector('#project-count').textContent = dashboard.projects_count;
  document.querySelector('#empty-project-count').textContent = dashboard.empty_projects_count;
  document.querySelector('#subproject-count').textContent = dashboard.subprojects_count;
  document.querySelector('#docker-project-count').textContent = dashboard.docker_projects_count;
  document.querySelector('#gitlab-ci-project-count').textContent = dashboard.gitlab_ci_projects_count;
  const total = dashboard.projects_count + dashboard.empty_projects_count || 1;
  document.querySelector('#docker-project-percentage').textContent = `${Math.round(dashboard.docker_projects_count / total * 100)}% проектов`;
  document.querySelector('#gitlab-ci-project-percentage').textContent = `${Math.round(dashboard.gitlab_ci_projects_count / total * 100)}% проектов`;
  state.languageOldestCurrentVersions = Object.fromEntries(
    dashboard.enabled_languages
      .filter((language) => language.oldest_current_version)
      .map((language) => [language.code, language.oldest_current_version]),
  );
  state.technologyTarget = dashboard.technology_target;
  state.projectsCount = dashboard.projects_count;
  renderTargetLanguageFilter(dashboard.enabled_languages);
  renderTechnologyTarget(dashboard.technology_target, dashboard.projects_count);
  renderDependencyCountMatrix(dashboard.dependency_counts);
  renderLanguageStatistics(dashboard.languages);
  renderLanguageTechnologyCards(dashboard.language_technologies);
  renderFrameworks(dashboard.frameworks);
  renderRegistryStatistics(dashboard.registries);
  const topDependencies = document.querySelector('#top-dependencies');
  topDependencies.replaceChildren();
  dashboard.top_dependencies.forEach((item, index) => {
    const row = element('button', 'dependency-top-row');
    row.type = 'button';
    const identity = element('span', 'dependency-top-identity');
    identity.append(element('strong', '', item.name), element('small', '', item.language));
    row.append(element('span', 'dependency-rank', String(index + 1).padStart(2, '0')), identity, element('b', '', item.projects_count));
    row.addEventListener('click', () => openDependency(item.name));
    topDependencies.append(row);
  });
  if (!dashboard.top_dependencies.length) {
    topDependencies.append(element('p', 'empty-state', 'Зависимости еще не найдены.'));
  }
  renderCompanyRequirements(dashboard.company_requirements);
  renderDataQuality(dashboard.data_quality);
  renderLastScan(dashboard.last_scan);
}
function renderCompanyRequirements(dashboardRequirements) {
  const requirements = document.querySelector('#company-requirements');
  requirements.replaceChildren();
  const configuredByCode = new Map(activeRequirements().map((item) => [item.code, item]));
  const languages = [...new Set(
    activeRequirements().map((item) => item.language).filter(Boolean),
  )].sort((left, right) => left.localeCompare(right));
  if (
    !['all', 'global'].includes(state.dashboardRequirementLanguage)
    && !languages.includes(state.dashboardRequirementLanguage)
  ) state.dashboardRequirementLanguage = 'all';
  const languageFilter = document.querySelector('#company-requirement-language-filter');
  languageFilter.replaceChildren(...[
    { value: 'all', title: 'Все' },
    { value: 'global', title: 'Глобальные' },
    ...languages.map((language) => ({ value: language, title: language })),
  ].map((option) => {
    const label = element('label', 'requirement-language-option');
    const input = element('input');
    input.type = 'radio';
    input.name = 'company-requirement-language';
    input.value = option.value;
    input.checked = state.dashboardRequirementLanguage === option.value;
    input.addEventListener('change', () => {
      if (!input.checked) return;
      state.dashboardRequirementLanguage = input.value;
      renderCompanyRequirements(dashboardRequirements);
    });
    label.append(input, element('span', '', option.title));
    return label;
  }));
  const groups = new Map(state.requirementGroups.map((group) => [group.name, []]));
  dashboardRequirements.forEach((item) => {
    const configured = configuredByCode.get(item.code);
    if (!configured) return;
    if (state.dashboardRequirementLanguage === 'global' && configured.language !== null) return;
    if (!['all', 'global'].includes(state.dashboardRequirementLanguage)
      && configured.language !== state.dashboardRequirementLanguage) return;
    const groupName = state.requirementGroups.find((group) => group.id === configured.group_id)?.name || 'Без группы';
    if (!groups.has(groupName)) groups.set(groupName, []);
    groups.get(groupName).push(item);
  });
  groups.forEach((itemsForGroup, groupName) => {
    if (!itemsForGroup.length) return;
    const group = element('section', 'requirement-group');
    const items = element('div', 'requirement-group-items');
    itemsForGroup.forEach((item) => {
      const tone = complianceTone(item.compliance_percentage, 'company_requirement_thresholds');
      const card = element('button', `requirement requirement-${tone}`);
      card.type = 'button';
      const progress = element('div', 'requirement-progress');
      const progressValue = element('span');
      progressValue.style.width = `${item.compliance_percentage}%`;
      progress.append(progressValue);
      card.append(
        element('strong', '', item.title),
        element('b', '', `${item.compliance_percentage}%`),
        progress,
        element('small', '', `${item.matching_projects} из ${item.total_projects}`),
      );
      card.title = item.description;
      card.addEventListener('click', () => openRuleViolations(item.code));
      items.append(card);
    });
    group.append(element('h4', '', groupName), items);
    requirements.append(group);
  });
}
function renderDataQuality(quality) {
  document.querySelector('#data-quality-stats').replaceChildren(
    compactStatRow('Пакетный менеджер не определен', quality.unknown_package_manager),
    compactStatRow('Версия языка не определена', quality.unknown_language_version),
    compactStatRow('Проекты без обнаруженных модулей', quality.projects_without_subprojects),
    compactStatRow('Ошибки анализа', quality.analysis_errors),
  );
}
function renderLastScan(scan) {
  const lastScan = document.querySelector('#last-scan-stats');
  lastScan.replaceChildren();
  if (scan) {
    lastScan.append(
      compactStatRow('Завершено', formatDate(scan.completed_at)),
      compactStatRow('Длительность', formatDuration(scan.duration_seconds)),
      compactStatRow('Повторно использовано', scan.reused_projects),
      compactStatRow('Пропущено', scan.skipped_projects),
      compactStatRow('Ошибки', scan.errors_count),
      compactStatRow('Обращения к GitLab', scan.gitlab_requests),
    );
  } else lastScan.append(element('p', 'empty-state', 'Сканирование еще не запускалось.'));
}
async function loadDashboard() {
  const [dashboard] = await Promise.all([api(API.dashboard), ensureRequirements(), ensureParameters()]);
  renderDashboard(dashboard);
  state.loaded.dashboard = true;
}
