import json
import re
from pathlib import PurePosixPath

from packaging.version import InvalidVersion, Version

from gitlab_radar.schemas.dependency import Dependency, DependencyGroup
from gitlab_radar.schemas.project import Project, ProjectSubproject
from gitlab_radar.schemas.technology import PackageManager
from gitlab_radar.services.analysis.base import FileSelection
from gitlab_radar.services.analysis.diagnostics import analyze_module
from gitlab_radar.services.analysis.node_lock import NodeLockReader
from gitlab_radar.services.container_parser import parse_container_images
from gitlab_radar.services.package_manager import is_container_filename

PACKAGE_FILENAME = 'package.json'
NPM_LOCK_FILENAMES = frozenset({'package-lock.json', 'npm-shrinkwrap.json'})
YARN_LOCK_FILENAME = 'yarn.lock'
PNPM_LOCK_FILENAME = 'pnpm-lock.yaml'
NODE_VERSION_FILENAMES = frozenset({'.nvmrc', '.node-version'})
NODE_CONFIG_FILENAMES = frozenset({'.npmrc', 'tsconfig.json', 'tsconfig.base.json'})
NODE_FILENAMES = frozenset(
    {
        PACKAGE_FILENAME,
        *NPM_LOCK_FILENAMES,
        YARN_LOCK_FILENAME,
        PNPM_LOCK_FILENAME,
        *NODE_VERSION_FILENAMES,
        *NODE_CONFIG_FILENAMES,
    }
)
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
    version = '2'
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
        reader = NodeLockReader(files, project, self.language_code)
        modules = []
        for manifest in sorted(path for path in files if PurePosixPath(path).name == PACKAGE_FILENAME):
            module = analyze_module(
                project,
                self.language_code,
                manifest,
                lambda manifest=manifest: _build_subproject(
                    _parent_directory(manifest) or '.',
                    self.language_code,
                    files[manifest],
                    _module_files(_parent_directory(manifest), files),
                    reader.dependencies(manifest),
                ),
            )
            if module is not None:
                modules.append(module)
        return modules


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
    locked_dependencies: list[Dependency],
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
    transitive = [dependency for dependency in locked_dependencies if dependency.name not in direct_names]
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
        (Dependency(name=str(name), version=version) for name, version in value.items() if isinstance(version, str)),
        key=lambda item: item.name,
    )


def _detect_package_manager(document: dict[str, object], files: dict[str, bytes]) -> PackageManager:
    declared = document.get('packageManager')
    if isinstance(declared, str):
        manager = PACKAGE_MANAGER_BY_NAME.get(declared.partition('@')[0].casefold())
        if manager is not None:
            return manager
    detected = {
        manager for path in files if (manager := PACKAGE_MANAGER_BY_LOCK.get(PurePosixPath(path).name)) is not None
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


def _unique_dependencies(items: list[Dependency]) -> list[Dependency]:
    result = {(item.name, item.version): item for item in items}
    return sorted(result.values(), key=lambda item: (item.name, item.version or ''))


def _module_files(directory: str, files: dict[str, bytes]) -> dict[str, bytes]:
    result = {path: content for path, content in files.items() if _parent_directory(path) == directory}
    inherited = {*LOCK_FILENAMES, *NODE_VERSION_FILENAMES, '.npmrc'}
    current = PurePosixPath(directory)
    while current != current.parent:
        current = current.parent
        for name in inherited:
            path = str(current / name)
            if path in files and not any(PurePosixPath(existing).name == name for existing in result):
                result[path] = files[path]
    return result


def _json_document(content: bytes) -> dict[str, object]:
    document = json.loads(_decode(content))
    if not isinstance(document, dict):
        msg = 'Ожидается JSON object'
        raise TypeError(msg)
    return document


def _file_by_name(files: dict[str, bytes], filename: str) -> bytes | None:
    return next((content for path, content in files.items() if PurePosixPath(path).name == filename), None)


def _decode(content: bytes) -> str:
    return content.decode('utf-8-sig')


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
