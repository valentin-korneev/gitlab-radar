from dataclasses import dataclass
from urllib.parse import urlsplit

from packaging.utils import canonicalize_name

from gitlab_radar.schemas.dependency import Dependency
from gitlab_radar.services.dependency_parser import parse_toml, unique_dependencies


@dataclass(frozen=True, slots=True)
class LockMetadata:
    dependencies: list[Dependency]
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

    return LockMetadata(unique_dependencies(dependencies), sorted(registries))


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
            resolved.extend(Dependency(name=dependency.name, version=version) for version in sorted(versions))
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
