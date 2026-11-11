import json
import re
from collections.abc import Mapping
from pathlib import PurePosixPath

import yaml
from packaging.version import InvalidVersion, Version

from gitlab_radar.schemas.dependency import Dependency, DependencyGroup
from gitlab_radar.schemas.project import Project, ProjectSubproject
from gitlab_radar.schemas.technology import PackageManager
from gitlab_radar.services.analysis.base import FileSelection
from gitlab_radar.services.container_parser import parse_container_images
from gitlab_radar.services.package_manager import is_container_filename

PACKAGE_FILENAME = 'package.json'
NPM_LOCK_FILENAMES = frozenset({'package-lock.json', 'npm-shrinkwrap.json'})
YARN_LOCK_FILENAME = 'yarn.lock'
PNPM_LOCK_FILENAME = 'pnpm-lock.yaml'
NODE_VERSION_FILENAMES = frozenset({'.nvmrc', '.node-version'})
NODE_CONFIG_FILENAMES = frozenset({'.npmrc', 'tsconfig.json', 'tsconfig.base.json'})
NODE_FILENAMES = frozenset({
    PACKAGE_FILENAME,
    *NPM_LOCK_FILENAMES,
    YARN_LOCK_FILENAME,
    PNPM_LOCK_FILENAME,
    *NODE_VERSION_FILENAMES,
    *NODE_CONFIG_FILENAMES,
})
LOCK_FILENAMES = frozenset({*NPM_LOCK_FILENAMES, YARN_LOCK_FILENAME, PNPM_LOCK_FILENAME})
PACKAGE_MANAGER_BY_LOCK = {
    'package-lock.json': PackageManager.NPM,
    'npm-shrinkwrap.json': PackageManager.NPM,
    YARN_LOCK_FILENAME: PackageManager.YARN,
    PNPM_LOCK_FILENAME: PackageManager.PNPM,
}
PACKAGE_MANAGER_BY_NAME = {
    'npm': PackageManager.NPM,
    'yarn': PackageManager.YARN,
    'pnpm': PackageManager.PNPM,
}
NPM_REGISTRY_PATTERN = re.compile(r'^(?:@[^:]+:)?registry\s*=\s*(?P<url>\S+)\s*$', re.MULTILINE)
NODE_VERSION_PATTERN = re.compile(
    r'(?P<operator>>=|<=|!=|>|<|=|\^|~)?\s*v?(?P<version>\d+(?:\.\d+){0,2})(?:\.[xX*])?',
)
NODE_LOWER_BOUND_OPERATORS = {None, '=', '>=', '>', '^', '~'}
YARN_ENTRY_PATTERN = re.compile(
    r'^(?P<descriptors>[^\s#][^\n]*):\s*\n'
    r'(?:^[ \t]+.*\n)*?^[ \t]+version\s*:?[ \t]+["\']?(?P<version>[^"\'\s]+)',
    re.MULTILINE,
)


class _NodeAnalyzer:
    version = '1'
    package_manager_codes = ('npm', 'yarn', 'pnpm')
    key: str
    language_code: str

    def select_files(self, repository_paths: list[str]) -> list[FileSelection]:
        return [
            FileSelection(
                path=path,
                analyzer_key=self.key,
                language_code=self.language_code,
                role=_file_role(PurePosixPath(path).name),
            )
            for path in repository_paths
            if _is_node_analysis_file(PurePosixPath(path).name)
        ]

    def analyze(self, project: Project, files: dict[str, bytes]) -> list[ProjectSubproject]:
        del project
        manifests = sorted(path for path in files if PurePosixPath(path).name == PACKAGE_FILENAME)
        if not manifests:
            return []
        return [
            _build_subproject(
                _parent_directory(manifest) or '.',
                self.language_code,
                files[manifest],
                _module_files(_parent_directory(manifest), files),
            )
            for manifest in manifests
        ]


class JavaScriptAnalyzer(_NodeAnalyzer):
    key = 'javascript'
    language_code = 'javascript'


class TypeScriptAnalyzer(_NodeAnalyzer):
    key = 'typescript'
    language_code = 'typescript'


def _build_subproject(
    path: str,
    language: str,
    manifest: bytes,
    files: dict[str, bytes],
) -> ProjectSubproject:
    document = _json_document(manifest)
    dependencies = _dependencies(document.get('dependencies'))
    optional_groups = [
        DependencyGroup(name=name, dependencies=items)
        for name, key in (
            ('development', 'devDependencies'),
            ('optional', 'optionalDependencies'),
            ('peer', 'peerDependencies'),
        )
        if (items := _dependencies(document.get(key)))
    ]
    direct_names = {dependency.name for dependency in dependencies} | {
        dependency.name for group in optional_groups for dependency in group.dependencies
    }
    transitive = [
        dependency
        for dependency in _locked_dependencies(files)
        if dependency.name not in direct_names
    ]
    return ProjectSubproject(
        path=path,
        language=language,
        package_manager=_detect_package_manager(document, files),
        runtime_version=_runtime_version(document, files),
        dependencies=dependencies,
        optional_dependencies=optional_groups,
        transitive_dependencies=_unique_dependencies(transitive),
        package_registries=_package_registries(document, files),
        container_images=parse_container_images(files),
        has_docker=any(is_container_filename(PurePosixPath(file_path).name) for file_path in files),
    )


def _dependencies(value: object) -> list[Dependency]:
    if not isinstance(value, dict):
        return []
    return sorted(
        (
            Dependency(name=str(name), version=version)
            for name, version in value.items()
            if isinstance(version, str)
        ),
        key=lambda item: item.name,
    )


def _detect_package_manager(document: dict[str, object], files: dict[str, bytes]) -> PackageManager:
    declared = document.get('packageManager')
    if isinstance(declared, str):
        manager = PACKAGE_MANAGER_BY_NAME.get(declared.partition('@')[0].casefold())
        if manager is not None:
            return manager
    detected = {
        manager
        for path in files
        if (manager := PACKAGE_MANAGER_BY_LOCK.get(PurePosixPath(path).name)) is not None
    }
    if len(detected) == 1:
        return detected.pop()
    if len(detected) > 1:
        return PackageManager.MIXED
    return PackageManager.UNKNOWN


def _runtime_version(document: dict[str, object], files: dict[str, bytes]) -> str | None:
    engines = document.get('engines')
    if (
        isinstance(engines, dict)
        and isinstance(node_constraint := engines.get('node'), str)
        and (version := _minimum_node_version(node_constraint))
    ):
        return version
    for filename in ('.nvmrc', '.node-version'):
        content = _file_by_name(files, filename)
        if content is not None and (version := _decode(content).strip()):
            return version.removeprefix('v')
    return None


def _minimum_node_version(value: str) -> str | None:
    branch_minimums: list[Version] = []
    for branch in value.split('||'):
        lower_bounds: list[Version] = []
        for match in NODE_VERSION_PATTERN.finditer(branch):
            if match.group('operator') not in NODE_LOWER_BOUND_OPERATORS:
                continue
            try:
                lower_bounds.append(Version(match.group('version')))
            except InvalidVersion:
                continue
        if lower_bounds:
            branch_minimums.append(max(lower_bounds))
    return str(min(branch_minimums)) if branch_minimums else None


def _package_registries(document: dict[str, object], files: dict[str, bytes]) -> list[str]:
    registries = {
        match.group('url').rstrip('/')
        for path, content in files.items()
        if PurePosixPath(path).name == '.npmrc'
        for match in NPM_REGISTRY_PATTERN.finditer(_decode(content))
    }
    publish_config = document.get('publishConfig')
    if isinstance(publish_config, dict) and isinstance(publish_config.get('registry'), str):
        registries.add(publish_config['registry'].rstrip('/'))
    return sorted(registry for registry in registries if registry)


def _locked_dependencies(files: dict[str, bytes]) -> list[Dependency]:
    dependencies: list[Dependency] = []
    for path, content in files.items():
        filename = PurePosixPath(path).name
        if filename in NPM_LOCK_FILENAMES:
            dependencies.extend(_npm_locked_dependencies(content))
        elif filename == YARN_LOCK_FILENAME:
            dependencies.extend(_yarn_locked_dependencies(content))
        elif filename == PNPM_LOCK_FILENAME:
            dependencies.extend(_pnpm_locked_dependencies(content))
    return _unique_dependencies(dependencies)


def _npm_locked_dependencies(content: bytes) -> list[Dependency]:
    document = _json_document(content)
    packages = document.get('packages')
    if isinstance(packages, dict):
        result: list[Dependency] = []
        for path, metadata in packages.items():
            name = _node_modules_package_name(str(path))
            if name and isinstance(metadata, dict):
                version = metadata.get('version')
                result.append(Dependency(name=name, version=version if isinstance(version, str) else None))
        return result
    dependencies = document.get('dependencies')
    return _npm_v1_dependencies(dependencies) if isinstance(dependencies, dict) else []


def _npm_v1_dependencies(value: Mapping[object, object]) -> list[Dependency]:
    result: list[Dependency] = []
    for name, metadata in value.items():
        if not isinstance(metadata, dict):
            continue
        version = metadata.get('version')
        result.append(Dependency(name=str(name), version=version if isinstance(version, str) else None))
        nested = metadata.get('dependencies')
        if isinstance(nested, dict):
            result.extend(_npm_v1_dependencies(nested))
    return result


def _yarn_locked_dependencies(content: bytes) -> list[Dependency]:
    result: list[Dependency] = []
    for match in YARN_ENTRY_PATTERN.finditer(_decode(content)):
        descriptor = match.group('descriptors').split(',', maxsplit=1)[0].strip().strip('"\'')
        if name := _yarn_package_name(descriptor):
            result.append(Dependency(name=name, version=match.group('version')))
    return result


def _pnpm_locked_dependencies(content: bytes) -> list[Dependency]:
    try:
        document = yaml.safe_load(_decode(content))
    except yaml.YAMLError:
        return []
    if not isinstance(document, dict):
        return []
    packages = document.get('packages')
    if not isinstance(packages, dict):
        return []
    result: list[Dependency] = []
    for key, metadata in packages.items():
        parsed = _pnpm_package(str(key))
        if parsed is None:
            continue
        name, key_version = parsed
        version = metadata.get('version') if isinstance(metadata, dict) else None
        result.append(Dependency(name=name, version=version if isinstance(version, str) else key_version))
    return result


def _node_modules_package_name(path: str) -> str | None:
    marker = 'node_modules/'
    if marker not in path:
        return None
    tail = path.rsplit(marker, maxsplit=1)[1]
    parts = tail.split('/')
    return '/'.join(parts[:2]) if tail.startswith('@') and len(parts) > 1 else parts[0]


def _yarn_package_name(descriptor: str) -> str | None:
    value = descriptor.removeprefix('npm:')
    if value.startswith('@'):
        separator = value.find('@', 1)
        return value[:separator] if separator > 0 else None
    return value.partition('@')[0] or None


def _pnpm_package(value: str) -> tuple[str, str | None] | None:
    normalized = value.lstrip('/').split('(', maxsplit=1)[0]
    if normalized.startswith('@') and normalized.find('@', 1) < 0:
        name, separator, version = normalized.rpartition('/')
        return (name, version) if separator and version else None
    if '@' not in normalized and '/' in normalized:
        name, separator, version = normalized.partition('/')
        return (name, version) if separator and version else None
    separator = normalized.rfind('@')
    if separator <= 0:
        return None
    name = normalized[:separator]
    version = normalized[separator + 1 :]
    return (name, version or None)


def _unique_dependencies(items: list[Dependency]) -> list[Dependency]:
    result = {(item.name, item.version): item for item in items}
    return sorted(result.values(), key=lambda item: (item.name, item.version or ''))


def _module_files(directory: str, files: dict[str, bytes]) -> dict[str, bytes]:
    return {
        path: content
        for path, content in files.items()
        if _parent_directory(path) == directory
        or (
            _parent_directory(path) == ''
            and (PurePosixPath(path).name in LOCK_FILENAMES | NODE_VERSION_FILENAMES | {'.npmrc'})
        )
    }


def _json_document(content: bytes) -> dict[str, object]:
    try:
        document = json.loads(_decode(content))
    except json.JSONDecodeError:
        return {}
    return document if isinstance(document, dict) else {}


def _file_by_name(files: dict[str, bytes], filename: str) -> bytes | None:
    return next((content for path, content in files.items() if PurePosixPath(path).name == filename), None)


def _decode(content: bytes) -> str:
    return content.decode('utf-8', errors='replace')


def _is_node_analysis_file(filename: str) -> bool:
    return filename in NODE_FILENAMES or is_container_filename(filename)


def _file_role(filename: str) -> str:
    if filename in LOCK_FILENAMES:
        return 'lock'
    if filename == PACKAGE_FILENAME:
        return 'manifest'
    return 'config'


def _parent_directory(path: str) -> str:
    parent = str(PurePosixPath(path).parent)
    return '' if parent == '.' else parent
