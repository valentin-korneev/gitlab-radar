import logging
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import yaml
from packaging.utils import canonicalize_name

from gitlab_radar.schemas.dependency import Dependency
from gitlab_radar.services.dependency_parser import parse_json_document, parse_toml, table, unique_dependencies

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class LockMetadata:
    dependencies: list[Dependency]
    pipfile_document: dict[str, Any]
    registries: list[str]


def parse_lock_metadata(files: dict[str, bytes]) -> LockMetadata:
    dependencies: list[Dependency] = []
    registries: set[str] = set()
    for filename in ('uv.lock', 'poetry.lock'):
        content = files.get(filename)
        if content:
            document = parse_toml(content, filename)
            packages = document.get('package')
            dependencies.extend(_package_list(packages))
            registries.update(_package_registries(packages))

    pipfile_document = parse_json_document(files.get('Pipfile.lock'), 'Pipfile.lock')
    sources = table(pipfile_document, '_meta').get('sources')
    if isinstance(sources, list):
        registries.update(
            registry
            for source in sources
            if isinstance(source, dict)
            if (registry := _clean_registry(source.get('url')))
        )
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
            conda_dependencies, conda_registries = _parse_conda_lock(content)
            dependencies.extend(conda_dependencies)
            registries.update(conda_registries)
    return LockMetadata(unique_dependencies(dependencies), pipfile_document, sorted(registries))


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


def _parse_conda_lock(content: bytes) -> tuple[list[Dependency], set[str]]:
    try:
        document = yaml.safe_load(content.decode('utf-8'))
    except (UnicodeDecodeError, yaml.YAMLError):
        logger.warning('Не удалось разобрать lock-файл Conda')
        return [], set()
    if not isinstance(document, dict):
        return [], set()
    packages = document.get('package')
    registries = _package_registries(packages)
    metadata = table(document, 'metadata')
    channels = metadata.get('channels')
    if isinstance(channels, list):
        registries.update(
            registry
            for channel in channels
            if (registry := _clean_registry(channel))
        )
    return _package_list(packages), registries


def _package_registries(value: object) -> set[str]:
    if not isinstance(value, list):
        return set()
    result: set[str] = set()
    for package in value:
        if not isinstance(package, dict):
            continue
        source = package.get('source')
        if isinstance(source, dict):
            for key in ('registry', 'url'):
                registry = _clean_registry(source.get(key))
                if registry:
                    result.add(registry)
        registry = _clean_registry(package.get('url'))
        if registry:
            result.add(registry)
    return result


def _clean_registry(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip().rstrip('/')
    parsed = urlsplit(value)
    if not parsed.scheme or not parsed.hostname:
        return value
    netloc = parsed.netloc.rsplit('@', maxsplit=1)[-1]
    return netloc.lower()
