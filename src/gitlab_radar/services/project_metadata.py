import json
import logging
import tomllib
from dataclasses import dataclass
from typing import Any
lazy from collections.abc import Mapping

import yaml
from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name

from gitlab_radar.schemas.dependency import Dependency, DependencyGroup

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ProjectMetadata:
    python_version: str | None
    dependencies: list[Dependency]
    optional_dependencies: list[DependencyGroup]


def parse_pyproject_document(content: bytes | None) -> dict[str, Any]:
    if content is None:
        return {}
    try:
        return tomllib.loads(content.decode('utf-8'))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError):
        logger.warning('Не удалось разобрать pyproject.toml')
        return {}


def parse_project_metadata(files: Mapping[str, bytes]) -> ProjectMetadata:
    pyproject_content = files.get('pyproject.toml')
    pyproject = parse_pyproject_document(pyproject_content)
    dependencies = _project_dependencies(pyproject)
    optional_dependencies = _optional_dependencies(pyproject)
    python_versions = [_pyproject_python_version(pyproject)]

    pipfile_dependencies, pipfile_groups, pipfile_python = _pipfile_metadata(
        files.get('Pipfile'),
        files.get('Pipfile.lock'),
    )
    dependencies.extend(pipfile_dependencies)
    optional_dependencies.extend(pipfile_groups)
    python_versions.append(pipfile_python)

    conda_dependencies, conda_python = _conda_metadata(
        files.get('environment.yml') or files.get('environment.yaml'),
    )
    dependencies.extend(conda_dependencies)
    python_versions.append(conda_python)

    requirements_content = files.get('requirements.txt')
    if not pyproject_content and not pipfile_dependencies and not conda_dependencies and requirements_content:
        dependencies.extend(parse_requirements(requirements_content))

    return ProjectMetadata(
        python_version=_python_version_file(files.get('.python-version')) or next(
            (version for version in python_versions if version),
            None,
        ),
        dependencies=_unique_dependencies(dependencies),
        optional_dependencies=_merge_dependency_groups(optional_dependencies),
    )


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
        dependency = _parse_requirement(line)
        if dependency:
            dependencies.append(dependency)
    return _unique_dependencies(dependencies)


def _pipfile_metadata(
    pipfile_content: bytes | None,
    lock_content: bytes | None,
) -> tuple[list[Dependency], list[DependencyGroup], str | None]:
    if pipfile_content:
        pipfile = _parse_toml(pipfile_content, 'Pipfile')
        requires = _table(pipfile, 'requires')
        python_version = _string_value(requires.get('python_full_version')) or _string_value(
            requires.get('python_version'),
        )
        return (
            _mapped_dependencies(_table(pipfile, 'packages')),
            _dependency_groups({'dev': _mapped_dependencies(_table(pipfile, 'dev-packages'))}),
            python_version,
        )

    if not lock_content:
        return [], [], None
    try:
        lock = json.loads(lock_content.decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError):
        logger.warning('Не удалось разобрать Pipfile.lock')
        return [], [], None
    if not isinstance(lock, dict):
        return [], [], None
    requires = _table(_table(lock, '_meta'), 'requires')
    python_version = _string_value(requires.get('python_full_version')) or _string_value(
        requires.get('python_version'),
    )
    return (
        _mapped_dependencies(_table(lock, 'default')),
        _dependency_groups({'dev': _mapped_dependencies(_table(lock, 'develop'))}),
        python_version,
    )


def _conda_metadata(content: bytes | None) -> tuple[list[Dependency], str | None]:
    if not content:
        return [], None
    try:
        document = yaml.safe_load(content.decode('utf-8'))
    except (UnicodeDecodeError, yaml.YAMLError):
        logger.warning('Не удалось разобрать environment-файл Conda')
        return [], None
    if not isinstance(document, dict) or not isinstance(document.get('dependencies'), list):
        return [], None

    dependencies: list[Dependency] = []
    python_version: str | None = None
    for item in document['dependencies']:
        if isinstance(item, str):
            dependency = _conda_dependency(item)
            if dependency.name == 'python':
                python_version = dependency.version
            else:
                dependencies.append(dependency)
        elif isinstance(item, dict):
            pip_dependencies = item.get('pip')
            if isinstance(pip_dependencies, list):
                dependencies.extend(
                    dependency
                    for value in pip_dependencies
                    if isinstance(value, str)
                    if (dependency := _parse_requirement(value))
                )
    return _unique_dependencies(dependencies), python_version


def _conda_dependency(value: str) -> Dependency:
    specification = value.rpartition('::')[2].strip()
    for operator in ('>=', '<=', '!=', '==', '~=', '>', '<', '='):
        position = specification.find(operator)
        if position > 0:
            name = specification[:position].strip()
            version = specification[position:].strip()
            if operator == '=':
                version = f'=={version[1:].split("=", maxsplit=1)[0]}'
            return Dependency(name=canonicalize_name(name), version=version)
    return Dependency(name=canonicalize_name(specification))


def _mapped_dependencies(values: dict[str, Any]) -> list[Dependency]:
    return _unique_dependencies([_poetry_dependency(name, value) for name, value in values.items()])


def _parse_toml(content: bytes, filename: str) -> dict[str, Any]:
    try:
        return tomllib.loads(content.decode('utf-8'))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError):
        logger.warning('Не удалось разобрать %s', filename)
        return {}


def _string_value(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _project_dependencies(pyproject: dict[str, Any]) -> list[Dependency]:
    dependencies = _requirement_list(_table(pyproject, 'project').get('dependencies'))
    poetry = _table(_table(pyproject, 'tool'), 'poetry')
    poetry_dependencies = _table(poetry, 'dependencies')
    for name, value in poetry_dependencies.items():
        if name != 'python' and not _is_optional_poetry_dependency(value):
            dependencies.append(_poetry_dependency(name, value))
    return dependencies


def _optional_dependencies(pyproject: dict[str, Any]) -> list[DependencyGroup]:
    groups: dict[str, list[Dependency]] = {}
    project = _table(pyproject, 'project')
    for name, values in _table(project, 'optional-dependencies').items():
        groups.setdefault(name, []).extend(_requirement_list(values))
    for name, values in _table(pyproject, 'dependency-groups').items():
        groups.setdefault(name, []).extend(_requirement_list(values))

    uv = _table(_table(pyproject, 'tool'), 'uv')
    groups.setdefault('dev', []).extend(_requirement_list(uv.get('dev-dependencies')))

    poetry = _table(_table(pyproject, 'tool'), 'poetry')
    poetry_dependencies = _table(poetry, 'dependencies')
    optional_poetry = {
        name: _poetry_dependency(name, value)
        for name, value in poetry_dependencies.items()
        if name != 'python' and _is_optional_poetry_dependency(value)
    }
    assigned_optional: set[str] = set()
    for group_name, names in _table(poetry, 'extras').items():
        if not isinstance(names, list):
            continue
        for name in names:
            if isinstance(name, str) and name in optional_poetry:
                groups.setdefault(group_name, []).append(optional_poetry[name])
                assigned_optional.add(name)
    for name, dependency in optional_poetry.items():
        if name not in assigned_optional:
            groups.setdefault('optional', []).append(dependency)

    legacy_dev = _table(poetry, 'dev-dependencies')
    groups.setdefault('dev', []).extend(_poetry_dependencies(legacy_dev))
    for name, group in _table(poetry, 'group').items():
        groups.setdefault(name, []).extend(_poetry_dependencies(_table(group, 'dependencies')))

    return _dependency_groups(groups)


def _pyproject_python_version(pyproject: dict[str, Any]) -> str | None:
    requires_python = _table(pyproject, 'project').get('requires-python')
    if isinstance(requires_python, str):
        return requires_python.strip() or None
    poetry_python = _table(_table(_table(pyproject, 'tool'), 'poetry'), 'dependencies').get('python')
    if isinstance(poetry_python, str):
        return poetry_python.strip() or None
    if isinstance(poetry_python, dict):
        version = poetry_python.get('version')
        return version.strip() if isinstance(version, str) and version.strip() else None
    return None


def _python_version_file(content: bytes | None) -> str | None:
    if content is None:
        return None
    try:
        return next((line.strip() for line in content.decode('utf-8').splitlines() if line.strip()), None)
    except UnicodeDecodeError:
        logger.warning('Не удалось разобрать .python-version')
        return None


def _requirement_list(value: object) -> list[Dependency]:
    if not isinstance(value, list):
        return []
    return [dependency for item in value if isinstance(item, str) if (dependency := _parse_requirement(item))]


def _parse_requirement(value: str) -> Dependency | None:
    try:
        requirement = Requirement(value)
    except InvalidRequirement:
        return None
    version = str(requirement.specifier) or (f'@ {requirement.url}' if requirement.url else None)
    return Dependency(name=canonicalize_name(requirement.name), version=version)


def _poetry_dependencies(values: dict[str, Any]) -> list[Dependency]:
    return [_poetry_dependency(name, value) for name, value in values.items() if name != 'python']


def _poetry_dependency(name: str, value: object) -> Dependency:
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


def _is_optional_poetry_dependency(value: object) -> bool:
    return isinstance(value, dict) and value.get('optional') is True


def _merge_dependency_groups(groups: list[DependencyGroup]) -> list[DependencyGroup]:
    dependencies_by_group: dict[str, list[Dependency]] = {}
    for group in groups:
        dependencies_by_group.setdefault(group.name, []).extend(group.dependencies)
    return _dependency_groups(dependencies_by_group)


def _dependency_groups(groups: Mapping[str, list[Dependency]]) -> list[DependencyGroup]:
    return [
        DependencyGroup(name=name, dependencies=_unique_dependencies(dependencies))
        for name, dependencies in sorted(groups.items())
        if dependencies
    ]


def _unique_dependencies(dependencies: list[Dependency]) -> list[Dependency]:
    unique = {(dependency.name, dependency.version): dependency for dependency in dependencies}
    return sorted(unique.values(), key=lambda dependency: (dependency.name, dependency.version or ''))


def _table(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    table = value.get(name)
    return table if isinstance(table, dict) else {}
