import json
import posixpath
import re
import shlex
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath

import yaml

from gitlab_radar.schemas.dependency import Dependency
from gitlab_radar.schemas.project import DiagnosticStatus, Project
from gitlab_radar.services.analysis.diagnostics import PARSE_ERRORS, UnsupportedFormatError, report

LOCK_NAMES = ('npm-shrinkwrap.json', 'package-lock.json', 'pnpm-lock.yaml', 'yarn.lock')
DEPENDENCY_FIELDS = ('dependencies', 'devDependencies', 'optionalDependencies')


def _references(document: dict, *, development: bool = False) -> dict:
    fields = DEPENDENCY_FIELDS if development else ('dependencies', 'optionalDependencies')
    return {name: version for field in fields for name, version in document.get(field, {}).items()}


class NodeLockReader:
    def __init__(self, files: dict[str, bytes], project: Project, language: str) -> None:
        self.files = files
        self.project = project
        self.language = language
        self._documents: dict[str, dict] = {}

    def dependencies(self, manifest: str) -> list[Dependency]:
        directory = PurePosixPath(manifest).parent
        while True:
            invalid_paths = {
                item.file_path for item in self.project.analysis_diagnostics if item.status == DiagnosticStatus.INVALID
            }
            if any(str(directory / name) in invalid_paths for name in LOCK_NAMES):
                return []
            paths = [str(directory / name) for name in LOCK_NAMES if str(directory / name) in self.files]
            if paths:
                if len(paths) > 1:
                    report(
                        self.project,
                        manifest,
                        'Найдено несколько lock-файлов; используется приоритет npm, pnpm, Yarn',
                        language=self.language,
                        status=DiagnosticStatus.PARTIAL,
                    )
                return self._read(paths[0], manifest)
            if directory == directory.parent:
                return []
            directory = directory.parent

    def _read(self, path: str, manifest: str) -> list[Dependency]:
        try:
            if path not in self._documents:
                content = self.files[path].decode('utf-8-sig')
                self._documents[path] = (
                    json.loads(content)
                    if path.endswith('.json')
                    else _yarn_document(content)
                    if path.endswith('yarn.lock')
                    else yaml.safe_load(content)
                )
            document = self._documents[path]
            directory = posixpath.relpath(str(PurePosixPath(manifest).parent), str(PurePosixPath(path).parent))
            _require_mapping(document)
            if path.endswith('.json'):
                return _npm_graph(document, directory)
            if path.endswith('pnpm-lock.yaml'):
                return _pnpm_graph(document, directory)
            manifest_document = json.loads(self.files[manifest].decode('utf-8-sig'))
            return _yarn_graph(document, manifest_document, self.files)
        except UnsupportedFormatError as error:
            report(self.project, path, str(error), language=self.language, status=DiagnosticStatus.UNSUPPORTED)
        except PARSE_ERRORS as error:
            report(
                self.project,
                path,
                f'Не удалось прочитать граф зависимостей ({type(error).__name__})',
                language=self.language,
            )
        return []


def _require_mapping(document: object) -> None:
    if not isinstance(document, dict):
        msg = 'Ожидается объект lock-файла'
        raise TypeError(msg)


def _npm_graph(document: dict, directory: str) -> list[Dependency]:
    if document.get('lockfileVersion') not in {1, 2, 3}:
        msg = 'Неподдерживаемая версия npm lock-файла'
        raise UnsupportedFormatError(msg)
    packages = document.get('packages')
    if not isinstance(packages, dict):
        if directory != '.':
            msg = 'npm lock v1 не содержит привязки к workspace'
            raise UnsupportedFormatError(msg)
        return _npm_v1_graph(document.get('dependencies', {}))
    root = '' if directory == '.' else directory
    if root not in packages:
        msg = 'В lock-файле отсутствует workspace модуля'
        raise UnsupportedFormatError(msg)
    pending = [root]
    visited = set()
    result = []
    while pending:
        current = pending.pop()
        if current in visited:
            continue
        visited.add(current)
        metadata = packages[current]
        if metadata.get('link'):
            target = _npm_link(packages, metadata)
            pending.append(target)
            continue
        if current != root and '/node_modules/' in f'/{current}':
            name = current.rsplit('node_modules/', maxsplit=1)[1]
            result.append(Dependency(name=name, version=metadata.get('version')))
        pending.extend(_npm_children(packages, current, metadata, development=current == root))
    return result


def _npm_link(packages: dict, metadata: dict) -> str:
    target = posixpath.normpath(metadata['resolved'])
    if target not in packages:
        msg = 'Отсутствует связанный workspace'
        raise UnsupportedFormatError(msg)
    return target


def _npm_children(packages: dict, current: str, metadata: dict, *, development: bool) -> list[str]:
    result = []
    for name in _references(metadata, development=development):
        target = _npm_resolve(packages, current, name)
        if target is not None:
            result.append(target)
        elif name not in metadata.get('optionalDependencies', {}):
            msg = 'В lock-файле отсутствует обязательная зависимость'
            raise UnsupportedFormatError(msg)
    return result


def _npm_resolve(packages: dict, current: str, name: str) -> str | None:
    directory = current
    while True:
        candidate = posixpath.join(directory, 'node_modules', name)
        if candidate in packages:
            return candidate
        if not directory:
            return None
        directory = posixpath.dirname(directory)


def _npm_v1_graph(dependencies: Mapping) -> list[Dependency]:
    result = []
    for name, metadata in dependencies.items():
        result.append(Dependency(name=name, version=metadata.get('version')))
        result.extend(_npm_v1_graph(metadata.get('dependencies', {})))
    return result


@dataclass(frozen=True, slots=True)
class _PnpmEdge:
    target: str
    metadata: dict
    importer: bool
    dependency: Dependency | None


class _PnpmGraph:
    def __init__(self, document: dict) -> None:
        self.importers = document.get('importers', {'.': document})
        self.packages = document.get('packages', {})
        self.snapshots = document.get('snapshots', self.packages)

    def edge(self, current: str, name: str, raw_reference: str | dict) -> _PnpmEdge:
        reference = str(raw_reference['version'] if isinstance(raw_reference, dict) else raw_reference)
        if reference.startswith(('link:', 'workspace:')):
            target = posixpath.normpath(posixpath.join(current, reference.partition(':')[2]))
            if target not in self.importers:
                msg = 'Не найден связанный importer workspace'
                raise UnsupportedFormatError(msg)
            return _PnpmEdge(target, self.importers[target], True, None)
        target = _pnpm_resolve(self.snapshots, name, reference)
        if target is None:
            msg = 'Не найдена зависимость в pnpm graph'
            raise UnsupportedFormatError(msg)
        package_version = self.packages.get(target, {}).get('version') or _pnpm_version(target, name)
        return _PnpmEdge(target, self.snapshots[target] or {}, False, Dependency(name=name, version=package_version))


def _pnpm_graph(document: dict, directory: str) -> list[Dependency]:
    version = str(document.get('lockfileVersion', '')).split('.', maxsplit=1)[0]
    if version not in {'5', '6', '9'}:
        msg = 'Неподдерживаемая версия pnpm lock-файла'
        raise UnsupportedFormatError(msg)
    graph = _PnpmGraph(document)
    if directory not in graph.importers:
        msg = 'В pnpm lock-файле отсутствует importer модуля'
        raise UnsupportedFormatError(msg)
    pending = [(directory, graph.importers[directory], True)]
    visited = set()
    result = []
    while pending:
        current, metadata, importer = pending.pop()
        if current in visited:
            continue
        visited.add(current)
        for name, reference in _references(metadata, development=importer).items():
            try:
                edge = graph.edge(current, name, reference)
            except UnsupportedFormatError:
                if name in metadata.get('optionalDependencies', {}):
                    continue
                raise
            pending.append((edge.target, edge.metadata, edge.importer))
            if edge.dependency is not None:
                result.append(edge.dependency)
    return result


def _pnpm_resolve(snapshots: dict, name: str, reference: str) -> str | None:
    return next(
        (
            key
            for key in (f'{name}@{reference}', f'/{name}@{reference}', f'/{name}/{reference}', reference)
            if key in snapshots
        ),
        None,
    )


def _pnpm_version(key: str, name: str) -> str:
    value = key.lstrip('/')
    for prefix in (f'{name}@', f'{name}/'):
        if value.startswith(prefix):
            return value[len(prefix) :].split('(', maxsplit=1)[0].split('_', maxsplit=1)[0]
    return value


def _yarn_document(
    content: str,
) -> dict:
    if '__metadata:' in content:
        document = yaml.safe_load(content)
        if not isinstance(document, dict) or str(document['__metadata'].get('version')) not in {
            '4',
            '5',
            '6',
            '7',
            '8',
        }:
            msg = 'Неподдерживаемая версия Yarn lock-файла'
            raise UnsupportedFormatError(msg)
        return document
    if '# yarn lockfile v1' not in content:
        msg = 'Неизвестный формат Yarn lock-файла'
        raise UnsupportedFormatError(msg)
    return _yarn_classic_document(content)


def _yarn_classic_document(content: str) -> dict:
    result = {}
    entry = None
    section = None
    for line in content.splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        if not line.startswith(' '):
            if not line.endswith(':'):
                msg = 'Некорректная запись Yarn v1'
                raise ValueError(msg)
            entry = {}
            result[line[:-1]] = entry
            section = None
        elif entry is not None:
            section = _yarn_classic_line(line, entry, section)
    return result


def _yarn_classic_line(line: str, entry: dict, section: str | None) -> str | None:
    values = shlex.split(line.strip())
    if line.startswith('    '):
        if section:
            name, reference = values
            entry[section][name] = reference
        return section
    if len(values) == 1 and values[0].endswith(':'):
        section = values[0][:-1]
        entry[section] = {}
        return section
    name, value = values
    entry[name] = value
    return None


def _yarn_descriptors(document: dict) -> dict:
    descriptors = {}
    for key, metadata in document.items():
        if key == '__metadata':
            continue
        for descriptor in re.split(r',\s*', key):
            descriptors[descriptor.strip('"\'')] = metadata
    return descriptors


def _yarn_workspaces(files: dict[str, bytes]) -> dict:
    workspaces = {}
    for path, content in files.items():
        if PurePosixPath(path).name == 'package.json':
            module = json.loads(content.decode('utf-8-sig'))
            if isinstance(module.get('name'), str):
                workspaces[module['name']] = module
    return workspaces


def _yarn_graph(document: dict, manifest: dict, files: dict[str, bytes]) -> list[Dependency]:
    descriptors = _yarn_descriptors(document)
    workspaces = _yarn_workspaces(files)
    pending = list(_references(manifest, development=True).items())
    visited = set()
    result = []
    while pending:
        name, reference = pending.pop()
        identity = (name, reference)
        if identity in visited:
            continue
        visited.add(identity)
        metadata = descriptors.get(f'{name}@{reference}') or descriptors.get(f'{name}@npm:{reference}')
        if (
            metadata is None
            and name in workspaces
            and (reference.startswith('workspace:') or reference in {'*', workspaces[name].get('version')})
        ):
            pending.extend(_references(workspaces[name], development=True).items())
            continue
        if metadata is None:
            msg = 'Не найдена зависимость в Yarn graph'
            raise UnsupportedFormatError(msg)
        if not isinstance(metadata.get('version'), str):
            msg = 'Отсутствует версия пакета в Yarn lock-файле'
            raise TypeError(msg)
        result.append(Dependency(name=name, version=metadata.get('version')))
        pending.extend(_references(metadata).items())
    return result
