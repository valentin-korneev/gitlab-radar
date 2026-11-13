import { api } from './api.js';
import { API } from './config.js';
import { bindEditorAction } from './editors.js';
import { readLatest } from './requests.js';
import { element, formatDate, formatDuration } from './shared.js';
import { showError } from './toasts.js';

const SERIES = [
  ['successful', 'Успешно', 'var(--green)'], ['partial', 'Частично', 'var(--warning)'],
  ['failed', 'Ошибки', 'var(--danger)'], ['skipped', 'Пропущено', 'var(--muted)'],
];
let initialized = false;
let chartFilters;
let chartSelection;
function svgElement(tag, attributes = {}, text = null) {
  const node = document.createElementNS('http://www.w3.org/2000/svg', tag);
  Object.entries(attributes).forEach(([name, value]) => node.setAttribute(name, value));
  if (text !== null) node.textContent = text;
  return node;
}
function chartFrame(label, maximum, format) {
  const svg = svgElement('svg', { viewBox: '0 0 720 220', role: 'img', 'aria-label': label, class: 'scan-chart' });
  [0, 0.5, 1].forEach((ratio) => {
    const y = 185 - ratio * 160;
    svg.append(svgElement('line', { x1: 66, x2: 710, y1: y, y2: y, class: 'scan-chart-grid' }),
      svgElement('text', { x: 58, y: y + 4, 'text-anchor': 'end' }, format(maximum * ratio)));
  });
  return svg;
}
function chartBar(point, x, y, width, height, color, text) {
  const bar = svgElement('rect', { x, y, width, height: Math.max(1, height), fill: color, rx: 2, tabindex: 0, role: 'button', 'aria-label': text });
  bar.append(svgElement('title', {}, text));
  const select = () => {
    document.querySelector('#scan-statistics-dialog').close(); chartSelection(point.id).catch(showError);
  };
  bar.addEventListener('click', select);
  bar.addEventListener('keydown', (event) => { if (['Enter', ' '].includes(event.key)) { event.preventDefault(); select(); } });
  return bar;
}
function renderCharts(points) {
  const container = document.querySelector('#scan-charts'); container.replaceChildren();
  if (!points.length) { container.append(element('p', 'empty-state', 'Запусков по выбранным фильтрам нет.')); return; }
  const durationMax = Math.max(1, ...points.map((point) => point.duration_seconds));
  const resultsMax = Math.max(1, ...points.map((point) => SERIES.reduce((sum, [key]) => sum + point[key], 0)));
  const durations = chartFrame('Длительность запусков. Выберите столбец для просмотра запуска.', durationMax, (value) => value >= 60 ? `${(value / 60).toLocaleString('ru-RU', { maximumFractionDigits: 1 })} мин` : `${value.toLocaleString('ru-RU', { maximumFractionDigits: 1 })} с`);
  const results = chartFrame('Результаты обработки проектов по запускам.', resultsMax, (value) => Math.round(value).toLocaleString('ru-RU'));
  const step = 636 / points.length;
  points.forEach((point, index) => {
    const x = 70 + index * step; const width = Math.max(3, step * 0.72);
    const height = point.duration_seconds / durationMax * 160;
    durations.append(chartBar(point, x, 185 - height, width, height, point.state === 'failed' ? 'var(--danger)' : 'var(--accent)',
      `Запуск №${point.id} · ${formatDate(point.created_at)} · ${formatDuration(point.duration_seconds)}`));
    let top = 185;
    SERIES.forEach(([key, title, color]) => {
      if (!point[key]) return;
      const part = point[key] / resultsMax * 160; top -= part;
      results.append(chartBar(point, x, top, width, part, color, `Запуск №${point.id} · ${title}: ${point[key]}`));
    });
    if (index % Math.ceil(points.length / 8) === 0 || index === points.length - 1) {
      [durations, results].forEach((svg) => svg.append(svgElement('text', { x: x + width / 2, y: 209, 'text-anchor': 'middle' }, `№${point.id}`)));
    }
  });
  const durationCard = element('section', 'scan-chart-card');
  durationCard.append(element('h3', '', 'Длительность'), durations);
  const resultsCard = element('section', 'scan-chart-card');
  const legend = element('div', 'scan-chart-legend');
  SERIES.forEach(([, title, color]) => {
    const label = element('span', '', title); label.style.setProperty('--series-color', color); legend.append(label);
  });
  resultsCard.append(element('h3', '', 'Результаты проектов'), legend, results);
  container.append(durationCard, resultsCard,
    element('p', 'scan-item-description', 'Последние 40 запусков по выбранным фильтрам. В успешные включено повторное использование анализа; перенесенные данные других проектов и проекты без пунктов запуска не учитываются. Нажмите на столбец для просмотра запуска.'));
}
async function loadCharts() {
  const query = chartFilters(); query.delete('before'); query.set('limit', 40);
  const points = await readLatest('scan-charts', (signal) => api(`${API.scan}statistics?${query}`, { signal }));
  if (!points || !document.querySelector('#scan-statistics-dialog').open) return;
  renderCharts(points);
}
function initializeCharts(filters, selectRun) {
  if (initialized) return;
  initialized = true; chartFilters = filters; chartSelection = selectRun;
  const dialog = document.querySelector('#scan-statistics-dialog');
  document.querySelector('#scan-statistics-open').addEventListener('click', () => {
    if (!dialog.open) dialog.showModal();
    document.querySelector('#scan-charts').replaceChildren(element('p', 'empty-state', 'Загрузка статистики…'));
    loadCharts().catch(showError);
  });
  document.querySelector('#scan-statistics-close').addEventListener('click', () => dialog.close());
  bindEditorAction(document.querySelector('#scan-statistics-refresh'), loadCharts);
}
export { initializeCharts };
