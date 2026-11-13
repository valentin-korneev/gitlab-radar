import hashlib
import json
import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PackageLocation:
    language: str
    module_path: str
    scope: str


@dataclass(frozen=True, slots=True)
class PackageRecord:
    key: str
    location: PackageLocation
    name: str
    versions: list[str | None]


def canonical_package_language(language: str) -> str:
    return 'javascript' if language == 'typescript' else language


def package_inventory(payload: dict) -> dict[str, PackageRecord]:
    grouped: dict[tuple[str, str, str, str], set[str | None]] = {}
    for module in payload.get('subprojects', []):
        language = canonical_package_language(module.get('language') or 'python')
        scopes = [('direct', module.get('dependencies', [])), ('transitive', module.get('transitive_dependencies', []))]
        scopes.extend(
            (f'optional:{group["name"]}', group['dependencies']) for group in module.get('optional_dependencies', [])
        )
        for scope, dependencies in scopes:
            for dependency in dependencies:
                name = dependency['name']
                if language == 'python':
                    name = re.sub(r'[-_.]+', '-', name).lower()
                identity = (language, module['path'], scope, name)
                grouped.setdefault(identity, set()).add(dependency.get('version'))
    result = {}
    for identity, versions in grouped.items():
        key = hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()
        result[key] = PackageRecord(
            key,
            PackageLocation(*identity[:3]),
            identity[3],
            sorted(versions, key=lambda value: (value is not None, value or '')),
        )
    return result
