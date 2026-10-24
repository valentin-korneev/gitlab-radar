import logging
from dataclasses import dataclass
from typing import Any

import yaml
from packaging.utils import canonicalize_name

from gitlab_radar.schemas.dependency import Dependency
from gitlab_radar.services.dependency_parser import parse_json_document, parse_toml, table, unique_dependencies

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class LockMetadata:
    dependencies: list[Dependency]
    pipfile_document: dict[str, Any]


def parse_lock_metadata(files: dict[str, bytes]) -> LockMetadata:
    dependencies: list[Dependency] = []
    for filename in ('uv.lock', 'poetry.lock'):
        content = files.get(filename)
        if content:
            dependencies.extend(_package_list(parse_toml(content, filename).get('package')))

    pipfile_document = parse_json_document(files.get('Pipfile.lock'), 'Pipfile.lock')
    for group_name in ('default', 'develop'):
        for name, value in table(pipfile_document, group_name).items():
            version = value.get('version') if isinstance(value, dict) else value
            dependencies.append(
                Dependency(
                    name=canonicalize_name(name),
                    version=version if isinstance(version, str) and version else None,
                ),
            )
    for filename in ('conda-lock.yml', 'conda-lock.yaml'):
        content = files.get(filename)
        if content:
            dependencies.extend(_parse_conda_lock(content))
    return LockMetadata(unique_dependencies(dependencies), pipfile_document)


def resolve_locked_versions(
    dependencies: list[Dependency],
    locked_dependencies: list[Dependency],
) -> list[Dependency]:
    locked_versions: dict[str, set[str]] = {}
    for dependency in locked_dependencies:
        if dependency.version:
            locked_versions.setdefault(dependency.name, set()).add(dependency.version)
    resolved: list[Dependency] = []
    for dependency in dependencies:
        versions = locked_versions.get(dependency.name, set())
        if versions:
            resolved.extend(
                Dependency(name=dependency.name, version=version)
                for version in sorted(versions)
            )
        else:
            resolved.append(dependency)
    return unique_dependencies(resolved)


def _package_list(value: object) -> list[Dependency]:
    if not isinstance(value, list):
        return []
    dependencies: list[Dependency] = []
    for package in value:
        if not isinstance(package, dict):
            continue
        name = package.get('name')
        version = package.get('version')
        if isinstance(name, str):
            dependencies.append(
                Dependency(
                    name=canonicalize_name(name),
                    version=f'=={version}' if isinstance(version, str) and version else None,
                ),
            )
    return dependencies


def _parse_conda_lock(content: bytes) -> list[Dependency]:
    try:
        document = yaml.safe_load(content.decode('utf-8'))
    except (UnicodeDecodeError, yaml.YAMLError):
        logger.warning('Не удалось разобрать lock-файл Conda')
        return []
    if not isinstance(document, dict):
        return []
    return _package_list(document.get('package'))
