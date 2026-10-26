import logging
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name

from gitlab_radar.schemas.dependency import Dependency, DependencyGroup

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class DependencyDeclarations:
    dependencies: list[Dependency] = field(default_factory=list)
    optional_dependencies: list[DependencyGroup] = field(default_factory=list)
    python_constraint: str | None = None
    project_name: str | None = None
    configured_tools: set[str] = field(default_factory=set)


def parse_pyproject_document(content: bytes | None) -> dict[str, Any]:
    if content is None:
        return {}
    return parse_toml(content, 'pyproject.toml')


def parse_pyproject(document: dict[str, Any]) -> DependencyDeclarations:
    project = table(document, 'project')
    tool = table(document, 'tool')
    poetry = table(tool, 'poetry')
    dependencies = requirement_list(project.get('dependencies'))
    dependencies.extend(_poetry_direct_dependencies(poetry))
    groups = _pyproject_dependency_groups(document, project, tool)
    _extend_poetry_groups(groups, poetry)
    project_name = project.get('name') or poetry.get('name')
    return DependencyDeclarations(
        dependencies=unique_dependencies(dependencies),
        optional_dependencies=dependency_groups(groups),
        python_constraint=pyproject_python_constraint(document),
        project_name=canonicalize_name(project_name) if isinstance(project_name, str) and project_name else None,
        configured_tools=set(tool),
    )


def _pyproject_dependency_groups(
    document: dict[str, Any],
    project: dict[str, Any],
    tool: dict[str, Any],
) -> dict[str, list[Dependency]]:
    groups: dict[str, list[Dependency]] = {}
    for name, values in table(project, 'optional-dependencies').items():
        groups.setdefault(name, []).extend(requirement_list(values))
    for name, values in table(document, 'dependency-groups').items():
        groups.setdefault(name, []).extend(requirement_list(values))
    groups.setdefault('dev', []).extend(requirement_list(table(tool, 'uv').get('dev-dependencies')))
    return groups


def _poetry_direct_dependencies(poetry: dict[str, Any]) -> list[Dependency]:
    poetry_dependencies = table(poetry, 'dependencies')
    return [
        poetry_dependency(name, value)
        for name, value in poetry_dependencies.items()
        if name != 'python' and not is_optional_poetry_dependency(value)
    ]


def _extend_poetry_groups(groups: dict[str, list[Dependency]], poetry: dict[str, Any]) -> None:
    poetry_dependencies = table(poetry, 'dependencies')
    optional_poetry = {
        name: poetry_dependency(name, value)
        for name, value in poetry_dependencies.items()
        if name != 'python' and is_optional_poetry_dependency(value)
    }
    assigned_optional: set[str] = set()
    for group_name, names in table(poetry, 'extras').items():
        if not isinstance(names, list):
            continue
        for name in names:
            if isinstance(name, str) and name in optional_poetry:
                groups.setdefault(group_name, []).append(optional_poetry[name])
                assigned_optional.add(name)
    for name, dependency in optional_poetry.items():
        if name not in assigned_optional:
            groups.setdefault('optional', []).append(dependency)

    groups.setdefault('dev', []).extend(poetry_dependencies_from_table(table(poetry, 'dev-dependencies')))
    for name, group in table(poetry, 'group').items():
        groups.setdefault(name, []).extend(poetry_dependencies_from_table(table(group, 'dependencies')))


def parse_requirements(content: bytes) -> list[Dependency]:
    try:
        text = content.decode('utf-8')
    except UnicodeDecodeError:
        logger.warning('Не удалось разобрать requirements.txt')
        return []
    dependencies: list[Dependency] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(('#', '-r', '--requirement', '-c', '--constraint')):
            continue
        if line.startswith(('-e ', '--editable ')):
            egg = line.partition('#egg=')[2].strip()
            if egg:
                dependencies.append(Dependency(name=canonicalize_name(egg)))
            continue
        line = line.split(' #', maxsplit=1)[0].partition(';')[0].strip()
        dependency = parse_requirement(line)
        if dependency is not None:
            dependencies.append(dependency)
    return unique_dependencies(dependencies)


def parse_toml(content: bytes, filename: str) -> dict[str, Any]:
    try:
        return tomllib.loads(content.decode('utf-8'))
    except UnicodeDecodeError, tomllib.TOMLDecodeError:
        logger.warning('Не удалось разобрать %s', filename)
        return {}


def parse_requirement(value: str) -> Dependency | None:
    try:
        requirement = Requirement(value)
    except InvalidRequirement:
        return None
    version = str(requirement.specifier) or (f'@ {requirement.url}' if requirement.url else None)
    return Dependency(name=canonicalize_name(requirement.name), version=version)


def requirement_list(value: object) -> list[Dependency]:
    if not isinstance(value, list):
        return []
    dependencies: list[Dependency] = []
    for item in value:
        if not isinstance(item, str):
            continue
        dependency = parse_requirement(item)
        if dependency is not None:
            dependencies.append(dependency)
    return dependencies


def poetry_dependency(name: str, value: object) -> Dependency:
    version: str | None = None
    if isinstance(value, str):
        version = value if value != '*' else None
    elif isinstance(value, dict):
        configured_version = value.get('version')
        if isinstance(configured_version, str):
            version = configured_version if configured_version != '*' else None
        else:
            for source in ('path', 'git', 'url'):
                configured_source = value.get(source)
                if isinstance(configured_source, str):
                    version = f'{source}: {configured_source}'
                    break
    return Dependency(name=canonicalize_name(name), version=version)


def poetry_dependencies_from_table(values: dict[str, Any]) -> list[Dependency]:
    return [poetry_dependency(name, value) for name, value in values.items() if name != 'python']


def is_optional_poetry_dependency(value: object) -> bool:
    return isinstance(value, dict) and value.get('optional') is True


def pyproject_python_constraint(document: dict[str, Any]) -> str | None:
    requires_python = table(document, 'project').get('requires-python')
    if isinstance(requires_python, str):
        return requires_python.strip() or None
    poetry_python = table(table(table(document, 'tool'), 'poetry'), 'dependencies').get('python')
    if isinstance(poetry_python, str):
        return poetry_python.strip() or None
    if isinstance(poetry_python, dict):
        return string_value(poetry_python.get('version'))
    return None


def merge_dependency_groups(groups: list[DependencyGroup]) -> list[DependencyGroup]:
    dependencies_by_group: dict[str, list[Dependency]] = {}
    for group in groups:
        dependencies_by_group.setdefault(group.name, []).extend(group.dependencies)
    return dependency_groups(dependencies_by_group)


def dependency_groups(groups: Mapping[str, list[Dependency]]) -> list[DependencyGroup]:
    return [
        DependencyGroup(name=name, dependencies=unique_dependencies(dependencies))
        for name, dependencies in sorted(groups.items())
        if dependencies
    ]


def unique_dependencies(dependencies: list[Dependency]) -> list[Dependency]:
    unique = {(dependency.name, dependency.version): dependency for dependency in dependencies}
    return sorted(unique.values(), key=lambda dependency: (dependency.name, dependency.version or ''))


def table(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    result = value.get(name)
    return result if isinstance(result, dict) else {}


def string_value(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None
