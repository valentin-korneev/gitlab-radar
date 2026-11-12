import re
from collections import Counter
from urllib.parse import urlsplit

from packaging.version import InvalidVersion, Version

from gitlab_radar.database.models import ProgrammingFramework, ProgrammingLanguage
from gitlab_radar.database.repository import latest_published_scan
from gitlab_radar.schemas.dashboard import (
    CompanyRequirement,
    Dashboard,
    DataQualityStatistics,
    DependencyCountStatistics,
    DependencyLevelStatistics,
    DependencyStatistics,
    FrameworkStatistics,
    LanguageOption,
    LanguageStatistics,
    LanguageTechnologyStatistics,
    LastScanStatistics,
    TechnologyTarget,
    TechnologyUsage,
)
from gitlab_radar.schemas.dependency import DependencyLevel
from gitlab_radar.schemas.project import Project, ProjectSubproject
from gitlab_radar.schemas.technology import PackageManager
from gitlab_radar.services.company_rules import load_company_requirements
from gitlab_radar.services.dependency import build_dependency_catalog, subproject_dependency_entries
from gitlab_radar.services.frameworks import detected_framework_codes
from gitlab_radar.services.programming_languages import canonical_language_code, language_display_name
from gitlab_radar.services.project import load_projects
lazy from gitlab_radar.schemas.company_requirement import CompanyRequirement as CompanyRequirementRule

DEPENDENCY_LEVEL_TITLES = {
    DependencyLevel.DIRECT: 'Прямые',
    DependencyLevel.OPTIONAL: 'Опциональные',
    DependencyLevel.TRANSITIVE: 'Транзитивные',
}


def invalidate_dashboard_cache() -> None:
    pass


async def build_dashboard(
    preferred_username: str | None = None,
    visibility_group: str | None = None,
) -> Dashboard:
    scan = await latest_published_scan()
    projects = await load_projects(preferred_username, visibility_group)
    requirements = await load_company_requirements()
    language_rows = await ProgrammingLanguage.all().order_by('name')
    enabled_rows = [row for row in language_rows if row.enabled]
    enabled_languages = _language_options(enabled_rows)
    language_counts = _language_project_counts(projects)
    non_empty_projects = [project for project in projects if not project.is_empty]
    dependency_catalog = await build_dependency_catalog(projects)
    image_statistics, registry_statistics = _registry_statistics(projects)
    framework_statistics = await _framework_statistics(projects)

    dashboard = Dashboard(
        projects_count=len(non_empty_projects),
        empty_projects_count=sum(project.is_empty for project in projects),
        subprojects_count=sum(max(len(project.subprojects) - 1, 0) for project in projects),
        docker_projects_count=sum(project.has_docker for project in projects),
        gitlab_ci_projects_count=sum(project.has_gitlab_ci for project in projects),
        languages=_display_language_statistics(language_rows, language_counts, len(non_empty_projects)),
        enabled_languages=enabled_languages,
        language_technologies=_language_technology_statistics(projects, enabled_rows),
        dependency_counts=_dependency_count_statistics(projects, enabled_rows),
        top_dependencies=_top_dependencies(projects),
        frameworks=framework_statistics,
        company_requirements=[
            _company_requirement_statistics(requirement, projects)
            for requirement in requirements
        ],
        technology_target=TechnologyTarget(
            languages=_language_target_statistics(projects, enabled_rows),
            dependencies=[
                TechnologyUsage(
                    name=dependency.name,
                    projects_count=dependency.projects_count,
                    languages=dependency.languages,
                )
                for dependency in dependency_catalog
                if dependency.level is not DependencyLevel.TRANSITIVE
            ],
            images=image_statistics,
            registries=registry_statistics,
        ),
        registries=registry_statistics,
        data_quality=_data_quality_statistics(projects),
        last_scan=(
            LastScanStatistics(
                completed_at=scan.completed_at.isoformat() if scan.completed_at else None,
                duration_seconds=round((scan.completed_at - scan.started_at).total_seconds(), 1)
                if scan.completed_at
                else 0.0,
                errors_count=len(scan.errors),
                reused_projects=scan.reused_projects,
                skipped_projects=scan.skipped_projects,
                gitlab_requests=scan.gitlab_requests,
            )
            if scan
            else None
        ),
    )
    return dashboard.model_copy(deep=True)


def _language_project_counts(projects: list[Project]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for project in projects:
        counts.update({canonical_language_code(language.code) for language in project.languages})
    return counts


def _display_language_statistics(
    languages: list[ProgrammingLanguage],
    counts: Counter[str],
    total_projects: int,
) -> list[LanguageStatistics]:
    grouped = _group_language_rows(languages)
    entries = [
        (
            code,
            rows,
            counts[code],
            any(row.enabled for row in rows),
            _language_group_version(rows),
        )
        for code, rows in grouped.items()
    ]

    def sort_key(item: tuple[str, list[ProgrammingLanguage], int, bool, str | None]) -> tuple[int, str]:
        return -item[2], language_display_name(item[0], item[1][0].name).lower()

    enabled = sorted((item for item in entries if item[3]), key=sort_key)[:10]
    disabled_limit = 10 - len(enabled)
    disabled = sorted((item for item in entries if not item[3]), key=sort_key)[
        :disabled_limit
    ]
    selected = sorted([*enabled, *disabled], key=sort_key)
    return [
        LanguageStatistics(
            code=code,
            name=language_display_name(code, rows[0].name),
            projects_count=project_count,
            percentage=_percentage(project_count, total_projects),
            enabled=enabled,
            oldest_current_version=oldest_current_version,
        )
        for code, rows, project_count, enabled, oldest_current_version in selected
    ]


def _language_options(languages: list[ProgrammingLanguage]) -> list[LanguageOption]:
    return [
        LanguageOption(
            code=code,
            name=language_display_name(code, rows[0].name),
            oldest_current_version=_language_group_version(rows),
        )
        for code, rows in _group_language_rows(languages).items()
    ]


def _group_language_rows(
    languages: list[ProgrammingLanguage],
) -> dict[str, list[ProgrammingLanguage]]:
    grouped: dict[str, list[ProgrammingLanguage]] = {}
    for language in languages:
        grouped.setdefault(canonical_language_code(language.code), []).append(language)
    return grouped


def _language_group_version(languages: list[ProgrammingLanguage]) -> str | None:
    ordered = sorted(languages, key=lambda language: language.code != 'javascript')
    return next((language.oldest_current_version for language in ordered if language.oldest_current_version), None)


def _language_technology_statistics(
    projects: list[Project],
    languages: list[ProgrammingLanguage],
) -> list[LanguageTechnologyStatistics]:
    result: list[LanguageTechnologyStatistics] = []
    for code, language_rows in _group_language_rows(languages).items():
        name = language_display_name(code, language_rows[0].name)
        language_projects = [
            project
            for project in projects
            if any(canonical_language_code(item.code) == code for item in project.languages)
        ]
        manager_projects: dict[str, set[int]] = {}
        version_projects: dict[str, set[int]] = {}
        for project in language_projects:
            subprojects = [
                subproject
                for subproject in project.subprojects
                if canonical_language_code(subproject.language) == code
            ]
            managers = {
                subproject.package_manager.value
                for subproject in subprojects
                if subproject.package_manager is not PackageManager.UNKNOWN
            }
            if not managers:
                managers.add(PackageManager.UNKNOWN.value)
            for manager in managers:
                manager_projects.setdefault(manager, set()).add(project.id)
            versions = {_runtime_version(subproject) for subproject in subprojects}
            for version in versions - {None}:
                version_projects.setdefault(str(version), set()).add(project.id)
        package_managers = _usage_from_projects(manager_projects)
        versions = _usage_from_projects(version_projects, version_sort=True)
        if package_managers or versions:
            result.append(
                LanguageTechnologyStatistics(
                    code=code,
                    name=name,
                    projects_count=len(language_projects),
                    package_managers=package_managers,
                    versions=versions,
                ),
            )
    return result


def _dependency_count_statistics(
    projects: list[Project],
    languages: list[ProgrammingLanguage],
) -> DependencyCountStatistics:
    by_language: dict[str, dict[DependencyLevel, set[str]]] = {}
    language_options = _language_options(languages)
    for language in language_options:
        names = {level: set() for level in DependencyLevel}
        for project in projects:
            for subproject in project.subprojects:
                if canonical_language_code(subproject.language) != language.code:
                    continue
                for dependency, level in subproject_dependency_entries(subproject):
                    names[level].add(dependency.name)
        names[DependencyLevel.OPTIONAL] -= names[DependencyLevel.DIRECT]
        names[DependencyLevel.TRANSITIVE] -= names[DependencyLevel.DIRECT] | names[DependencyLevel.OPTIONAL]
        by_language[language.code] = names
    return DependencyCountStatistics(
        languages=language_options,
        levels=[
            DependencyLevelStatistics(
                level=level.value,
                title=DEPENDENCY_LEVEL_TITLES[level],
                by_language={
                    language.code: len(by_language[language.code][level]) for language in languages
                },
                total=sum(len(by_language[language.code][level]) for language in languages),
            )
            for level in DependencyLevel
        ],
    )


def _company_requirement_statistics(
    requirement: CompanyRequirementRule,
    projects: list[Project],
) -> CompanyRequirement:
    eligible_projects = [
        project
        for project in projects
        if requirement.language is None
        or any(
            canonical_language_code(language.code) == canonical_language_code(requirement.language)
            for language in project.languages
        )
    ]
    matching_projects = sum(
        project.company_rule_results.get(requirement.code) is True for project in eligible_projects
    )
    return CompanyRequirement(
        code=requirement.code,
        title=requirement.title,
        description=requirement.description,
        matching_projects=matching_projects,
        total_projects=len(eligible_projects),
        compliance_percentage=_percentage(matching_projects, len(eligible_projects)),
    )


async def _framework_statistics(projects: list[Project]) -> list[FrameworkStatistics]:
    frameworks = (
        await ProgrammingFramework.filter(enabled=True, language__enabled=True)
        .prefetch_related('language')
        .order_by('name')
    )
    detected_by_project = {
        project.id: detected_framework_codes(project, frameworks) for project in projects
    }
    grouped: dict[tuple[str, str], tuple[set[int], set[str]]] = {}
    for framework in frameworks:
        project_ids = {
            project.id
            for project in projects
            if framework.code in detected_by_project[project.id]
        }
        if project_ids:
            code = canonical_language_code(framework.language.code)
            grouped.setdefault((code, framework.name), (set(), set()))[0].update(project_ids)
            grouped[(code, framework.name)][1].add(framework.code)
    result = [
        FrameworkStatistics(
            code=min(codes),
            name=name,
            language=language_display_name(code),
            projects_count=len(project_ids),
        )
        for (code, name), (project_ids, codes) in grouped.items()
    ]
    return sorted(result, key=lambda item: (-item.projects_count, item.name.lower()))


def _top_dependencies(projects: list[Project]) -> list[DependencyStatistics]:
    projects_by_dependency: dict[tuple[str, str], set[int]] = {}
    for project in projects:
        for subproject in project.subprojects:
            for dependency, level in subproject_dependency_entries(subproject):
                if level is DependencyLevel.TRANSITIVE:
                    continue
                projects_by_dependency.setdefault(
                    (dependency.name, canonical_language_code(subproject.language)),
                    set(),
                ).add(project.id)
    return [
        DependencyStatistics(
            name=name,
            language=language_display_name(language),
            projects_count=len(project_ids),
        )
        for (name, language), project_ids in sorted(
            projects_by_dependency.items(),
            key=lambda item: (-len(item[1]), item[0][0], item[0][1]),
        )[:10]
    ]


def _language_target_statistics(
    projects: list[Project],
    languages: list[ProgrammingLanguage],
) -> list[TechnologyUsage]:
    result: list[TechnologyUsage] = []
    for code, language_rows in _group_language_rows(languages).items():
        name = language_display_name(code, language_rows[0].name)
        language_projects = [
            project
            for project in projects
            if any(canonical_language_code(item.code) == code for item in project.languages)
        ]
        if not language_projects:
            continue
        result.append(
            TechnologyUsage(
                name=name,
                projects_count=len(language_projects),
                languages=[code],
            ),
        )
        oldest_current_version = _language_group_version(language_rows)
        if oldest_current_version:
            threshold = _safe_version(oldest_current_version)
            if threshold is not None:
                lts_projects = sum(
                    any(
                        canonical_language_code(subproject.language) == code
                        and (version := _safe_version(_runtime_version(subproject))) is not None
                        and version >= threshold
                        for subproject in project.subprojects
                    )
                    for project in language_projects
                )
                result.append(
                    TechnologyUsage(
                        name=f'{name} LTS',
                        projects_count=lts_projects,
                        languages=[code],
                    ),
                )
    return result


def _registry_statistics(
    projects: list[Project],
) -> tuple[list[TechnologyUsage], list[TechnologyUsage]]:
    image_projects: dict[str, tuple[set[int], set[str]]] = {}
    registry_projects: dict[str, tuple[set[int], set[str]]] = {}
    for project in projects:
        languages = {canonical_language_code(language.code) for language in project.languages}
        for image in project.container_images:
            _add_technology_project(
                image_projects,
                f'{image.registry}/{image.image}',
                project.id,
                languages,
            )
            _add_technology_project(
                registry_projects,
                _registry_name(image.registry),
                project.id,
                languages,
            )
        for registry in project.package_registries:
            _add_technology_project(
                registry_projects,
                _registry_name(registry),
                project.id,
                languages,
            )
    return _technology_usage(image_projects), _technology_usage(registry_projects)


def _add_technology_project(
    target: dict[str, tuple[set[int], set[str]]],
    name: str,
    project_id: int,
    languages: set[str],
) -> None:
    projects, item_languages = target.setdefault(name, (set(), set()))
    projects.add(project_id)
    item_languages.update(languages)


def _technology_usage(
    projects_by_name: dict[str, tuple[set[int], set[str]]],
) -> list[TechnologyUsage]:
    return [
        TechnologyUsage(
            name=name,
            projects_count=len(project_ids),
            languages=sorted(languages),
        )
        for name, (project_ids, languages) in sorted(
            projects_by_name.items(),
            key=lambda item: (-len(item[1][0]), item[0]),
        )
    ]


def _usage_from_projects(
    projects_by_name: dict[str, set[int]],
    *,
    version_sort: bool = False,
) -> list[TechnologyUsage]:
    items = projects_by_name.items()
    if version_sort:
        items = sorted(items, key=lambda item: _safe_version(item[0]) or Version('0'), reverse=True)
    else:
        items = sorted(items, key=lambda item: (-len(item[1]), item[0]))
    return [
        TechnologyUsage(name=name, projects_count=len(project_ids))
        for name, project_ids in items
    ]


def _runtime_version(subproject: ProjectSubproject) -> str | None:
    if subproject.runtime_version:
        return _normalize_version(subproject.runtime_version)
    if subproject.language == 'python':
        return _normalize_version(subproject.python_version or subproject.python_constraint)
    return None


def _normalize_version(value: str | None) -> str | None:
    if not value:
        return None
    match = re.search(r'(?<!\d)(\d+)(?:\.(\d+))?', value)
    return '.'.join(part for part in match.groups() if part is not None) if match else None


def _safe_version(value: str | None) -> Version | None:
    if not value:
        return None
    try:
        return Version(value)
    except InvalidVersion:
        return None


def _percentage(value: int, total: int) -> float:
    return round(value / total * 100, 1) if total else 0.0


def _data_quality_statistics(projects: list[Project]) -> DataQualityStatistics:
    subprojects = [subproject for project in projects for subproject in project.subprojects]
    return DataQualityStatistics(
        unknown_package_manager=sum(
            subproject.package_manager is PackageManager.UNKNOWN for subproject in subprojects
        ),
        unknown_language_version=sum(_runtime_version(subproject) is None for subproject in subprojects),
        projects_without_subprojects=sum(not project.subprojects for project in projects),
        analysis_errors=sum(bool(project.scan_error) for project in projects),
    )


def _registry_name(value: str) -> str:
    parsed = urlsplit(value if '://' in value else f'//{value}')
    return str(parsed.netloc or value.partition('/')[0]).lower()
