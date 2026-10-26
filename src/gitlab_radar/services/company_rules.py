from dataclasses import dataclass
from urllib.parse import urlsplit

from gitlab_radar.database.models import CompanyRequirement as CompanyRequirementModel
from gitlab_radar.schemas.company_requirement import (
    CompanyRequirement,
    RequirementCondition,
    RequirementConditionGroup,
    RequirementLogic,
    RequirementOperator,
    RequirementSource,
)
from gitlab_radar.schemas.project import Project, ProjectSubproject


@dataclass(frozen=True, slots=True)
class RuleContext:
    package_manager: set[str]
    dependencies: set[str]
    tools: set[str]
    components: set[str]
    hooks: set[str]
    package_registries: set[str]
    container_registries: set[str]


async def load_company_requirements(*, enabled: bool | None = True) -> list[CompanyRequirement]:
    query = CompanyRequirementModel.all()
    if enabled is not None:
        query = query.filter(enabled=enabled)
    rows = await query.order_by('sort_order', 'id')
    return [serialize_company_requirement(row) for row in rows]


def serialize_company_requirement(row: CompanyRequirementModel) -> CompanyRequirement:
    return CompanyRequirement.model_validate(
        {
            'id': row.id,
            'code': row.code,
            'title': row.title,
            'group_id': row.group_id,
            'description': row.description,
            'condition': row.condition,
            'enabled': row.enabled,
            'sort_order': row.sort_order,
        },
    )


def subproject_rule_results(
    subproject: ProjectSubproject,
    requirements: list[CompanyRequirement],
    project: Project | None = None,
) -> dict[str, bool]:
    dependencies = {
        dependency.name.lower()
        for dependency in (
            *subproject.dependencies,
            *(dependency for group in subproject.optional_dependencies for dependency in group.dependencies),
        )
    }
    context = RuleContext(
        package_manager={subproject.package_manager.value.lower()},
        dependencies=dependencies,
        tools={tool.lower() for tool in subproject.configured_tools},
        components={component.name.lower() for component in project.gitlab_ci_components} if project else set(),
        hooks={hook.url.lower() for hook in project.webhooks} if project else set(),
        package_registries={
            _registry_domain(value)
            for value in (set(project.package_registries) if project else set(subproject.package_registries))
        },
        container_registries={
            _registry_domain(value)
            for value in (
                _project_container_registries(project) if project else _subproject_container_registries(subproject)
            )
        },
    )
    return {requirement.code: _matches_requirement(requirement, context) for requirement in requirements}


def _matches_requirement(requirement: CompanyRequirement, context: RuleContext) -> bool:
    return _matches_group(requirement.condition, context)


def _matches_group(group: RequirementConditionGroup, context: RuleContext) -> bool:
    results = [
        _matches_group(node, context)
        if isinstance(node, RequirementConditionGroup)
        else _matches_condition(node, context)
        for node in group.items
    ]
    if group.logic is RequirementLogic.OR:
        return any(results)
    return all(results)


def _matches_condition(condition: RequirementCondition, context: RuleContext) -> bool:
    candidates = _source_values(condition.source, context)
    if not candidates:
        return condition.empty_result

    values = {value.strip().lower() for value in condition.values if value.strip()}
    if condition.operator is RequirementOperator.EQUALS:
        return bool(candidates & values)
    if condition.operator is RequirementOperator.NOT_EQUALS:
        return not bool(candidates & values)
    if condition.operator is RequirementOperator.CONTAINS:
        return any(value in candidate for candidate in candidates for value in values)
    contains = [any(value in candidate for value in values) for candidate in candidates]
    if condition.operator is RequirementOperator.NOT_CONTAINS:
        return not any(contains)
    return all(contains)


def _source_values(source: RequirementSource, context: RuleContext) -> set[str]:
    values = {
        RequirementSource.PACKAGE_MANAGER: context.package_manager,
        RequirementSource.DEPENDENCY: context.dependencies,
        RequirementSource.TOOL: context.tools,
        RequirementSource.DEPENDENCY_AND_TOOL: context.dependencies & context.tools,
        RequirementSource.CI_COMPONENT: context.components,
        RequirementSource.WEBHOOK: context.hooks,
        RequirementSource.PACKAGE_REGISTRY: context.package_registries,
        RequirementSource.CONTAINER_REGISTRY: context.container_registries,
    }
    return values[source]


def _project_container_registries(project: Project) -> set[str]:
    return {image.registry for image in project.container_images}


def _subproject_container_registries(subproject: ProjectSubproject) -> set[str]:
    return {image.registry for image in subproject.container_images}


def _registry_domain(registry: str) -> str:
    parsed = urlsplit(registry if '://' in registry else f'//{registry}')
    return (parsed.hostname or registry.partition('/')[0]).lower()


def _project_rule_results(
    subproject_results: list[dict[str, bool]],
    requirements: list[CompanyRequirement],
) -> dict[str, bool]:
    return {
        requirement.code: bool(subproject_results) and all(result[requirement.code] for result in subproject_results)
        for requirement in requirements
    }


def _compliance_percentage(results: dict[str, bool]) -> float:
    return round(sum(results.values()) / len(results) * 100, 1) if results else 100.0


def apply_company_compliance(project: Project, requirements: list[CompanyRequirement]) -> None:
    subproject_results: list[dict[str, bool]] = []
    for subproject in project.subprojects:
        results = subproject_rule_results(subproject, requirements, project)
        subproject.company_rule_results = results
        subproject.company_compliance_percentage = _compliance_percentage(results)
        subproject_results.append(results)
    project.company_rule_results = _project_rule_results(subproject_results, requirements)
    project.company_compliance_percentage = (
        round(
            sum(subproject.company_compliance_percentage for subproject in project.subprojects)
            / len(project.subprojects),
            1,
        )
        if project.subprojects
        else 0.0
    )
