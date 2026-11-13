import { element } from './shared.js';

function scanOptionsFields(container) {
  const projects = element('label', 'visibility-field scan-option-field', 'ID проектов (пусто — все доступные)');
  const ids = element('input');
  ids.name = 'project_ids';
  ids.placeholder = 'Например: 123, 456';
  projects.append(ids);
  const force = element('label', 'switch scan-option-toggle');
  const checkbox = element('input');
  checkbox.type = 'checkbox';
  checkbox.name = 'force_analysis';
  force.append(checkbox, element('span'), document.createTextNode('Повторить анализ даже без изменений'));
  container.append(projects, force);
}
function readScanOptions(container) {
  const text = container.querySelector('[name=project_ids]').value.trim();
  const projectIds = text ? text.split(/[\s,;]+/).map(Number) : null;
  if (projectIds && (projectIds.length > 1000 || projectIds.some((id) => !Number.isSafeInteger(id) || id <= 0))) {
    throw new Error('Укажите до 1000 положительных ID проектов через запятую');
  }
  return { project_ids: projectIds, force_analysis: container.querySelector('[name=force_analysis]').checked };
}
function fillScanOptions(container, options = {}) {
  container.querySelector('[name=project_ids]').value = (options.project_ids || []).join(', ');
  container.querySelector('[name=force_analysis]').checked = Boolean(options.force_analysis);
}
function scanOptionsText(options = {}) {
  return `${options.project_ids ? `Проекты: ${options.project_ids.join(', ')}` : 'Все доступные проекты'} · ${options.force_analysis ? 'повторный анализ без кеша' : 'повторное использование готового анализа'}`;
}
export { scanOptionsFields, readScanOptions, fillScanOptions, scanOptionsText };
