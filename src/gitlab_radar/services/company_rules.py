from dataclasses import dataclass
from urllib.parse import urlsplit

from gitlab_radar.schemas.project import GitLabComponent, Project, ProjectHook, ProjectSubproject
from gitlab_radar.schemas.technology import PackageManager


@dataclass(frozen=True, slots=True)
class CompanyRule:
    code: str
    title: str
    description: str
    dependency: str | None = None
    component_pattern: str | None = None
    hook_pattern: str | None = None
    registry_policy: bool = False


@dataclass(frozen=True, slots=True)
class RuleContext:
    dependencies: set[str]
    tools: set[str]
    components: set[str]
    hooks: set[str]
    package_registries: set[str]
    container_registries: set[str]


COMPANY_RULES = (
    CompanyRule('uv-required', 'uv обязателен', 'Проект использует uv как пакетный менеджер.'),
    CompanyRule('ruff-required', 'ruff обязателен', 'Проект использует ruff.', 'ruff'),
    CompanyRule('bandit-required', 'bandit обязателен', 'Проект использует bandit.', 'bandit'),
    CompanyRule('pylint-required', 'pylint обязателен', 'Проект использует pylint.', 'pylint'),
    CompanyRule(
        'python-linters-component-required',
        'Компонент python-linters обязателен',
        'GitLab CI подключает компонент, имя которого содержит python-linters.',
        component_pattern='python-linters',
    ),
    CompanyRule(
        'sonar-component-required',
        'Компонент sonar обязателен',
        'GitLab CI подключает компонент, имя которого содержит sonar.',
        component_pattern='sonar',
    ),
    CompanyRule(
        'approved-registry-required',
        'Разрешённые registry',
        'Python-зависимости используют Artifactory, образы — Artifactory или GitLab Registry.',
        registry_policy=True,
    ),
    CompanyRule(
        'aist-reviewer-hook-required',
        'Webhook aist.reviewer обязателен',
        'В проекте настроен webhook, URL которого содержит aist.reviewer.',
        hook_pattern='aist.reviewer',
    ),
)

def subproject_rule_results(
        subproject: ProjectSubproject,
        components: list[GitLabComponent] | None = None,
        package_registries: set[str] | None = None,
        container_registries: set[str] | None = None,
        hooks: list[ProjectHook] | None = None,
) -> dict[str, bool]:
    context = RuleContext(
        dependencies={
            dependency.name
            for dependency in (
                *subproject.dependencies,
                *(dependency for group in subproject.optional_dependencies for dependency in group.dependencies),
            )
        },
        tools=set(subproject.configured_tools),
        components={component.name.lower() for component in components or []},
        hooks={hook.url.lower() for hook in hooks or []}
        | {'aist.reviewer' for hook in hooks or [] if hook.is_aist_reviewer},
        package_registries=(
            package_registries
            if package_registries is not None
            else set(subproject.package_registries)
        ),
        container_registries=(
            container_registries
            if container_registries is not None
            else {image.registry for image in subproject.container_images}
        ),
    )
    return {
        rule.code: _matches_rule(rule, subproject, context)
        for rule in COMPANY_RULES
    }


def _matches_rule(
        rule: CompanyRule,
        subproject: ProjectSubproject,
        context: RuleContext,
) -> bool:
    if rule.component_pattern:
        return any(rule.component_pattern in name for name in context.components)
    if rule.hook_pattern:
        return any(rule.hook_pattern in url for url in context.hooks)
    if rule.dependency:
        return rule.dependency in context.dependencies or rule.dependency in context.tools
    if rule.registry_policy:
        package_registries_match = bool(context.package_registries) and all(
            'artifactory' in _registry_domain(registry)
            for registry in context.package_registries
        )
        container_registries_match = bool(context.container_registries) and all(
            any(allowed in _registry_domain(registry) for allowed in ('artifactory', 'gitlab-registry'))
            for registry in context.container_registries
        )
        return (
            (not context.dependencies or package_registries_match)
            and (not context.container_registries or container_registries_match)
            and bool(context.package_registries or context.container_registries)
        )
    return subproject.package_manager is PackageManager.UV


def _project_container_registries(project: Project) -> set[str]:
    return {image.registry for image in project.container_images}


def _registry_domain(registry: str) -> str:
    parsed = urlsplit(registry if '://' in registry else f'//{registry}')
    return (parsed.hostname or registry.partition('/')[0]).lower()


def project_rule_results(project: Project) -> dict[str, bool]:
    subproject_results = [
        subproject_rule_results(
            subproject,
            project.gitlab_ci_components,
            set(project.package_registries),
            _project_container_registries(project),
            project.webhooks,
        )
        for subproject in project.subprojects
    ]
    return _project_rule_results(subproject_results)


def _project_rule_results(subproject_results: list[dict[str, bool]]) -> dict[str, bool]:
    return {
        rule.code: bool(subproject_results) and all(result[rule.code] for result in subproject_results)
        for rule in COMPANY_RULES
    }


def subproject_compliance_percentage(
        subproject: ProjectSubproject,
        components: list[GitLabComponent] | None = None,
        package_registries: set[str] | None = None,
        container_registries: set[str] | None = None,
        hooks: list[ProjectHook] | None = None,
) -> float:
    results = subproject_rule_results(
        subproject,
        components,
        package_registries,
        container_registries,
        hooks,
    )
    return _compliance_percentage(results)


def _compliance_percentage(results: dict[str, bool]) -> float:
    return round(sum(results.values()) / len(results) * 100, 1)


def project_compliance_percentage(project: Project) -> float:
    if not project.subprojects:
        return 0.0
    return round(
        sum(
            subproject_compliance_percentage(
                subproject,
                project.gitlab_ci_components,
                set(project.package_registries),
                _project_container_registries(project),
                project.webhooks,
            )
            for subproject in project.subprojects
        )
        / len(project.subprojects),
        1,
    )


def apply_company_compliance(project: Project) -> None:
    package_registries = set(project.package_registries)
    container_registries = _project_container_registries(project)
    subproject_results: list[dict[str, bool]] = []
    for subproject in project.subprojects:
        results = subproject_rule_results(
            subproject,
            project.gitlab_ci_components,
            package_registries,
            container_registries,
            project.webhooks,
        )
        subproject.company_rule_results = results
        subproject.company_compliance_percentage = _compliance_percentage(results)
        subproject_results.append(results)
    project.company_rule_results = _project_rule_results(subproject_results)
    project.company_compliance_percentage = (
        round(
            sum(subproject.company_compliance_percentage for subproject in project.subprojects)
            / len(project.subprojects),
            1,
        )
        if project.subprojects
        else 0.0
    )
