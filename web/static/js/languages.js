import { pageEdit } from './page-updates.js';
import { api } from './api.js';
import { API } from './config.js';
import { bindAsyncInput, bindEditorChange } from './editors.js';
import { readLatest } from './requests.js';
import { showError, showSuccess } from './toasts.js';
import { canonicalLanguageCode, element } from './shared.js';
import { dashboardState, state } from './state.js';

function invalidateLanguageDependentData() {
  state.requirementCatalog = null;
  state.dependencyCache = {};
  dashboardState.technologyTargetLanguages = new Set();
  dashboardState.technologyTargetLanguagesInitialized = false;
  ['dashboard', 'projects', 'dependencies', 'requirements'].forEach((page) => {
    state.loaded[page] = false;
  });
}

function languageRow(language) {
  const selected = language.code === state.selectedProgrammingLanguageCode;
  const row = element('article', `programming-language-row${selected ? ' selected' : ''}`);
  row.tabIndex = 0;
  row.setAttribute('role', 'option');
  row.setAttribute('aria-selected', String(selected));
  const selectLanguage = () => {
    if (state.selectedProgrammingLanguageCode === language.code) return;
    state.selectedProgrammingLanguageCode = language.code;
    renderProgrammingLanguages();
    renderProgrammingFrameworks();
  };
  row.addEventListener('click', (event) => {
    if (!event.target.closest('input, label, button')) selectLanguage();
  });
  row.addEventListener('keydown', (event) => {
    if (event.target !== row) return;
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      selectLanguage();
    }
  });
  const identity = element('div', 'programming-language-identity');
  identity.append(
    element('strong', '', language.name),
    element('code', '', language.code),
  );
  const analyzer = element('div', 'programming-language-analyzer');
  analyzer.append(
    element('span', '', language.analyzer_key ? `Анализатор: ${language.analyzer_key}` : 'Анализатор не подключен'),
    element('small', '', language.analyzer_version ? `Версия ${language.analyzer_version}` : 'Только определение и статистика'),
  );
  if (language.package_managers.length) {
    analyzer.append(element('small', '', `Пакетные менеджеры: ${language.package_managers.join(', ')}`));
  }
  const version = element('label', 'programming-language-version');
  version.append(element('span', '', 'Самая старая актуальная версия'));
  const versionInput = element('input');
  versionInput.value = language.oldest_current_version || '';
  versionInput.dataset.languageCode = language.code;
  versionInput.placeholder = 'Все версии актуальны';
  versionInput.maxLength = 50;
  bindAsyncInput(versionInput, {
    scope: row,
    read: () => language.oldest_current_version || null,
    normalize: (value) => value.trim() || null,
    save: (value) => api(`${API.programmingLanguages}${language.id}/oldest-current-version`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ oldest_current_version: value }),
    }),
    onSaved: (updated) => {
      Object.assign(language, updated);
      state.programmingLanguages
        .filter((item) => canonicalLanguageCode(item.code) === canonicalLanguageCode(language.code))
        .forEach((item) => { item.oldest_current_version = updated.oldest_current_version; });
      document.querySelectorAll('.programming-language-version input').forEach((input) => {
        if (canonicalLanguageCode(input.dataset.languageCode) === canonicalLanguageCode(language.code)) {
          input.value = updated.oldest_current_version || '';
        }
      });
      invalidateLanguageDependentData();
    },
    success: 'Версия сохранена',
  });
  version.append(versionInput);
  const toggle = element('label', 'switch programming-language-switch');
  const input = element('input');
  input.type = 'checkbox';
  input.dataset.languageCode = language.code;
  input.checked = language.enabled;
  bindEditorChange(input, row, async () => {
    input.disabled = true;
    try {
      const updated = await api(`${API.programmingLanguages}${language.id}/enabled`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: input.checked }),
      });
      Object.assign(language, updated);
      state.programmingFrameworks
        .filter((framework) => canonicalLanguageCode(framework.language_code) === canonicalLanguageCode(language.code))
        .forEach((framework) => { framework.language_enabled = language.enabled; });
      state.programmingLanguages
        .filter((item) => canonicalLanguageCode(item.code) === canonicalLanguageCode(language.code))
        .forEach((item) => { item.enabled = language.enabled; });
      document.querySelectorAll('.programming-language-switch input').forEach((toggle) => {
        if (canonicalLanguageCode(toggle.dataset.languageCode) === canonicalLanguageCode(language.code)) {
          toggle.checked = language.enabled;
        }
      });
      renderProgrammingFrameworks();
      invalidateLanguageDependentData();
      showSuccess(language.enabled ? 'Язык включен' : 'Язык выключен');
    } catch (error) {
      input.checked = language.enabled;
      showError(error);
    } finally {
      input.disabled = false;
    }
  });
  toggle.append(input, element('span'), element('b', '', 'Включен'));
  row.append(identity, analyzer, version, toggle);
  return row;
}
function renderProgrammingLanguages() {
  const list = document.querySelector('#programming-language-list');
  list.replaceChildren(...state.programmingLanguages.map(languageRow));
  if (!state.programmingLanguages.length) {
    list.append(element('p', 'empty-state', 'Языки появятся после сканирования проектов.'));
  }
}
function frameworkRow(framework) {
  const row = element('article', `programming-framework-row${framework.language_enabled ? '' : ' language-disabled'}`);
  const identity = element('div', 'programming-framework-identity');
  identity.append(element('strong', '', framework.name));
  const dependencies = element(
    'small',
    'programming-framework-dependencies',
    framework.dependency_names.join(', ') || 'Зависимости не заданы',
  );
  const toggle = element('label', 'switch programming-framework-switch');
  const input = element('input');
  input.type = 'checkbox';
  input.checked = framework.enabled;
  bindEditorChange(input, row, async () => {
    input.disabled = true;
    try {
      const updated = await api(`${API.programmingLanguages}frameworks/${framework.id}/enabled`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: input.checked }),
      });
      Object.assign(framework, updated);
      invalidateLanguageDependentData();
      showSuccess(framework.enabled ? 'Фреймворк включен' : 'Фреймворк выключен');
    } catch (error) {
      input.checked = framework.enabled;
      showError(error);
    } finally {
      input.disabled = false;
    }
  });
  toggle.append(input, element('span'), element('b', '', 'Включен'));
  row.append(identity, dependencies, toggle);
  return row;
}
function renderProgrammingFrameworks() {
  const list = document.querySelector('#programming-framework-list');
  const language = state.programmingLanguages.find(
    (item) => item.code === state.selectedProgrammingLanguageCode,
  );
  document.querySelector('#programming-framework-language').textContent = language?.name || 'Выберите язык';
  const frameworks = state.programmingFrameworks.filter(
    (framework) => framework.language_code === state.selectedProgrammingLanguageCode,
  );
  list.replaceChildren(...frameworks.map(frameworkRow));
  if (!frameworks.length) {
    list.append(element('p', 'empty-state', language
      ? 'Для выбранного языка фреймворки не настроены.'
      : 'Выберите язык в списке слева.'));
  }
}
async function loadProgrammingLanguages() {
  const result = await readLatest('languages', (signal) => Promise.all([
    api(API.programmingLanguages, { signal }), api(`${API.programmingLanguages}frameworks`, { signal }),
  ]));
  if (!result || pageEdit('languages').dirty) return;
  [state.programmingLanguages, state.programmingFrameworks] = result;
  if (!state.programmingLanguages.some((language) => language.code === state.selectedProgrammingLanguageCode)) {
    state.selectedProgrammingLanguageCode = state.programmingLanguages[0]?.code || null;
  }
  renderProgrammingLanguages();
  renderProgrammingFrameworks();
  state.loaded.languages = true;
}

export { loadProgrammingLanguages };
