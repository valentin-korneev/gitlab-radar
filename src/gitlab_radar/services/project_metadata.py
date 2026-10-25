import logging
from collections.abc import Mapping
from configparser import ConfigParser
from configparser import Error as ConfigParserError
from dataclasses import dataclass
from typing import Any

from gitlab_radar.schemas.dependency import Dependency, DependencyGroup
from gitlab_radar.services.dependency_parser import (
    merge_dependency_groups,
    parse_pyproject,
    parse_pyproject_document,
    parse_requirements,
    parse_toml,
    unique_dependencies,
)
from gitlab_radar.services.lock_parser import parse_lock_metadata, resolve_locked_versions
from gitlab_radar.services.package_manager import is_requirements_filename

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ProjectMetadata:  # pylint: disable=too-many-instance-attributes
    python_version: str | None
    python_constraint: str | None
    python_version_source: str | None
    dependencies: list[Dependency]
    optional_dependencies: list[DependencyGroup]
    transitive_dependencies: list[Dependency]
    configured_tools: list[str]
    package_registries: list[str]


def parse_project_metadata(
        files: Mapping[str, bytes],
        pyproject: dict[str, Any] | None = None,
) -> ProjectMetadata:
    pyproject_content = files.get('pyproject.toml')
    pyproject = parse_pyproject_document(pyproject_content) if pyproject is None else pyproject
    lock = parse_lock_metadata(dict(files))
    declarations = [
        parse_pyproject(pyproject),
    ]

    dependencies = unique_dependencies(
        [dependency for declaration in declarations for dependency in declaration.dependencies],
    )
    optional_dependencies = merge_dependency_groups(
        [group for declaration in declarations for group in declaration.optional_dependencies],
    )
    requirements_files = [
        content
        for filename, content in sorted(files.items())
        if is_requirements_filename(filename)
    ]
    if not dependencies:
        dependencies.extend(
            dependency
            for content in requirements_files
            for dependency in parse_requirements(content)
        )

    dependencies = resolve_locked_versions(unique_dependencies(dependencies), lock.dependencies)
    optional_dependencies = [
        DependencyGroup(
            name=group.name,
            dependencies=resolve_locked_versions(group.dependencies, lock.dependencies),
        )
        for group in optional_dependencies
    ]
    direct_names = {dependency.name for dependency in dependencies}
    optional_dependencies = _without_direct_dependencies(optional_dependencies, direct_names)
    optional_names = {
        dependency.name
        for group in optional_dependencies
        for dependency in group.dependencies
    }
    project_names = {declaration.project_name for declaration in declarations if declaration.project_name}
    excluded_names = direct_names | optional_names | project_names | {'python'}
    python_version = _python_version_file(files.get('.python-version'))
    python_constraint = next(
        (declaration.python_constraint for declaration in declarations if declaration.python_constraint),
        None,
    )
    package_registries = _package_registries(
        files,
        pyproject,
        lock.registries,
        has_dependencies=bool(dependencies or optional_dependencies or lock.dependencies),
    )

    return ProjectMetadata(
        python_version=python_version,
        python_constraint=python_constraint,
        python_version_source='.python-version' if python_version else None,
        dependencies=dependencies,
        optional_dependencies=optional_dependencies,
        transitive_dependencies=[
            dependency for dependency in lock.dependencies if dependency.name not in excluded_names
        ],
        configured_tools=sorted(
            {tool for declaration in declarations for tool in declaration.configured_tools},
        ),
        package_registries=package_registries,
    )


def _package_registries(
    files: Mapping[str, bytes],
    pyproject: Mapping[str, object],
    lock_registries: list[str],
    *,
    has_dependencies: bool,
) -> list[str]:
    registries = set(lock_registries) | _pyproject_registries(pyproject)

    uv_content = files.get('uv.toml')
    if uv_content:
        registries.update(_index_urls(parse_toml(uv_content, 'uv.toml')))

    pip_content = files.get('pip.conf')
    if pip_content:
        registries.update(_pip_registries(pip_content))

    if not registries and has_dependencies:
        registries.add('https://pypi.org/simple')
    return sorted(registry.strip().rstrip('/') for registry in registries if registry.strip())


def _pyproject_registries(pyproject: Mapping[str, object]) -> set[str]:
    registries: set[str] = set()
    tool = pyproject.get('tool')
    if isinstance(tool, Mapping):
        for name in ('uv', 'poetry', 'pip'):
            section = tool.get(name)
            if isinstance(section, Mapping):
                registries.update(_index_urls(section))
    return registries


def _pip_registries(content: bytes) -> set[str]:
    parser = ConfigParser(interpolation=None)
    try:
        parser.read_string(content.decode('utf-8'))
    except (ConfigParserError, UnicodeDecodeError):
        logger.warning('Не удалось разобрать pip.conf')
        return set()
    return {
        registry
        for section in parser.sections()
        for key in ('index-url', 'extra-index-url')
        if parser.has_option(section, key)
        for registry in parser.get(section, key).split()
    }


def _index_urls(section: Mapping[str, object]) -> set[str]:
    registries: set[str] = set()
    for key in ('index-url', 'extra-index-url', 'default-index'):
        value = section.get(key)
        if isinstance(value, str):
            registries.add(value)
        elif isinstance(value, list):
            registries.update(item for item in value if isinstance(item, str))
    sources = section.get('source') or section.get('index')
    if isinstance(sources, list):
        registries.update(
            str(source['url'])
            for source in sources
            if isinstance(source, Mapping) and isinstance(source.get('url'), str)
        )
    return registries


def _without_direct_dependencies(
        groups: list[DependencyGroup],
        direct_names: set[str],
) -> list[DependencyGroup]:
    result: list[DependencyGroup] = []
    for group in groups:
        dependencies = [dependency for dependency in group.dependencies if dependency.name not in direct_names]
        if dependencies:
            result.append(DependencyGroup(name=group.name, dependencies=dependencies))
    return result


def _python_version_file(content: bytes | None) -> str | None:
    if content is None:
        return None
    try:
        return next((line.strip() for line in content.decode('utf-8').splitlines() if line.strip()), None)
    except UnicodeDecodeError:
        logger.warning('Не удалось разобрать .python-version')
        return None
