from dataclasses import dataclass

from gitlab_radar.schemas.project import Project, ProjectSubproject
from gitlab_radar.schemas.technology import PackageManager


@dataclass(frozen=True, slots=True)
class CompanyRule:
    code: str
    title: str
    description: str
    dependency: str | None = None


COMPANY_RULES = (
    CompanyRule('uv-required', 'uv обязателен', 'Проект использует uv как пакетный менеджер.'),
    CompanyRule('ruff-required', 'ruff обязателен', 'Проект использует ruff.', 'ruff'),
    CompanyRule('bandit-required', 'bandit обязателен', 'Проект использует bandit.', 'bandit'),
    CompanyRule('pylint-required', 'pylint обязателен', 'Проект использует pylint.', 'pylint'),
)


def subproject_rule_results(subproject: ProjectSubproject) -> dict[str, bool]:
    dependencies = {
        dependency.name
        for dependency in (
            *subproject.dependencies,
            *(dependency for group in subproject.optional_dependencies for dependency in group.dependencies),
        )
    }
    tools = set(subproject.configured_tools)
    return {
        rule.code: (
            subproject.package_manager is PackageManager.UV
            if rule.dependency is None
            else rule.dependency in dependencies or rule.dependency in tools
        )
        for rule in COMPANY_RULES
    }


def project_rule_results(project: Project) -> dict[str, bool]:
    subproject_results = [subproject_rule_results(subproject) for subproject in project.subprojects]
    return {
        rule.code: bool(subproject_results) and all(result[rule.code] for result in subproject_results)
        for rule in COMPANY_RULES
    }


def subproject_compliance_percentage(subproject: ProjectSubproject) -> float:
    results = subproject_rule_results(subproject)
    return round(sum(results.values()) / len(results) * 100, 1)


def project_compliance_percentage(project: Project) -> float:
    if not project.subprojects:
        return 0.0
    return round(
        sum(subproject_compliance_percentage(subproject) for subproject in project.subprojects)
        / len(project.subprojects),
        1,
    )


def apply_company_compliance(project: Project) -> None:
    for subproject in project.subprojects:
        subproject.company_rule_results = subproject_rule_results(subproject)
        subproject.company_compliance_percentage = subproject_compliance_percentage(subproject)
    project.company_rule_results = project_rule_results(project)
    project.company_compliance_percentage = project_compliance_percentage(project)
