from dataclasses import dataclass

from gitlab_radar.schemas.project import Project
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


def project_rule_results(project: Project) -> dict[str, bool]:
    dependencies = {
        dependency.name
        for subproject in project.subprojects
        for dependency in (
            *subproject.dependencies,
            *(dependency for group in subproject.optional_dependencies for dependency in group.dependencies),
        )
    }
    return {
        rule.code: (
            project.package_manager is PackageManager.UV
            if rule.dependency is None
            else rule.dependency in dependencies
        )
        for rule in COMPANY_RULES
    }


def project_compliance_percentage(project: Project) -> float:
    results = project_rule_results(project)
    return round(sum(results.values()) / len(results) * 100, 1)
