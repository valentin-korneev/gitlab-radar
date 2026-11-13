const state = {
  dependencyCache: {},
  requirements: [], requirementGroups: [], requirementCatalog: null,
  parameters: [], programmingLanguages: [], programmingFrameworks: [], selectedProgrammingLanguageCode: null,
  authorizedUsers: [], visibilityGroups: [], selectedVisibilityGroup: null,
  visibilityPolicies: [], visibilityAdminUser: null, blacklistRules: [],
  auth: { config: null, user: null }, currentRoute: null, dataVersion: 0,
  loaded: {}, loading: {},
};
const projectState = {
  projects: [], selectedId: null, selectedSubprojectKey: null,
  projectFilters: { query: '', rules: new Set(), language: null, version: null },
};
const dashboardState = {
  technologyTarget: null, projectsCount: 0, showSingleTechnologies: false,
  technologyTargetLanguages: new Set(), technologyTargetLanguageOptions: [], technologyTargetLanguagesInitialized: false,
  languageOldestCurrentVersions: {}, dashboardRequirementLanguage: 'all', dashboardLanguageTechnologyCode: null,
};
const scanState = {
  scanState: null, scanStatus: null, scanSubmitting: false, scanSocket: null, scanReconnectTimer: null,
  scanStreamId: null, scanUpdatesCursor: 0, dashboardRefreshTimer: null,
};
const requirementState = { selectedRequirementGroupId: null };
const catalogPages = new Map();
let catalogState;
function activateCatalog(source) {
  if (!catalogPages.has(source)) catalogPages.set(source, {
    source, dependencies: [], selectedDependency: null, dependencyQuery: '',
    dependencyLanguages: new Set(), dependencyLanguagesInitialized: false,
    dependencyTreeExpanded: new Set(), showTransitive: false,
  });
  catalogState = catalogPages.get(source);
}
activateCatalog('python');

export { activateCatalog, catalogPages, catalogState, dashboardState, projectState, requirementState, scanState, state };
