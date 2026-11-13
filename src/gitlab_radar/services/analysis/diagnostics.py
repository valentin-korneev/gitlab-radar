import json
import tomllib
from collections.abc import Callable, Iterable
from configparser import ConfigParser
from configparser import Error as ConfigError
from pathlib import PurePosixPath
from typing import Protocol, Self

import yaml
from defusedxml import ElementTree
from defusedxml.common import DefusedXmlException
from packaging.requirements import Requirement

from gitlab_radar.schemas.project import AnalysisDiagnostic, DiagnosticStatus, Project, ProjectSubproject
from gitlab_radar.services.package_manager import is_requirements_filename


class UnsupportedFormatError(ValueError):
    pass


def parse_yaml(content: str) -> object:
    loader = yaml.SafeLoader(content)
    loader.yaml_constructors = {
        **loader.yaml_constructors,
        '!reference': lambda reader, node: reader.construct_sequence(node),
    }
    try:
        return loader.get_single_data()
    finally:
        loader.dispose()


class XmlElement(Protocol):
    tag: str
    text: str | None

    def iter(self) -> Iterable[Self]: ...
    def findall(self, path: str) -> list[Self]: ...
    def findtext(self, path: str) -> str | None: ...


def parse_xml(content: bytes) -> XmlElement:
    return ElementTree.fromstring(content, forbid_dtd=True, forbid_entities=True, forbid_external=True)


PARSE_ERRORS = (
    ValueError,
    TypeError,
    KeyError,
    IndexError,
    AttributeError,
    RecursionError,
    ConfigError,
    yaml.YAMLError,
    SyntaxError,
    DefusedXmlException,
)


def report(
    project: Project,
    path: str,
    message: str,
    *,
    language: str | None = None,
    status: DiagnosticStatus = DiagnosticStatus.INVALID,
) -> None:
    diagnostic = AnalysisDiagnostic(file_path=path, message=message, language=language, status=status)
    if diagnostic not in project.analysis_diagnostics:
        project.analysis_diagnostics.append(diagnostic)


def analyze_module(
    project: Project, language: str, path: str, build: Callable[[], ProjectSubproject]
) -> ProjectSubproject | None:
    try:
        return build()
    except PARSE_ERRORS as error:
        report(project, path, f'Не удалось разобрать модуль ({type(error).__name__})', language=language)
        return None


def validated_files(project: Project, files: dict[str, bytes]) -> dict[str, bytes]:
    result = {}
    for path, content in files.items():
        try:
            _validate(path, content)
        except UnsupportedFormatError as error:
            report(project, path, str(error), status=DiagnosticStatus.UNSUPPORTED)
        except PARSE_ERRORS as error:
            report(project, path, f'Некорректный файл ({type(error).__name__})')
        else:
            result[path] = content
            _limitations(project, path, content)
    return result


def _validate(path: str, content: bytes) -> None:
    name = PurePosixPath(path).name
    text = content.decode('utf-8-sig')
    if '\x00' in text or text == '[gitlab-radar:unsupported-encoding]':
        msg = 'Неподдерживаемая кодировка или нулевой символ'
        raise ValueError(msg)
    if name.endswith('.toml') or name == 'uv.lock':
        _validate_toml(name, text)
    elif name in {'package.json', 'package-lock.json', 'npm-shrinkwrap.json'}:
        _validate_json(name, text)
    elif name.endswith(('.yaml', '.yml')):
        _validate_yaml(name, text)
    elif name == 'pom.xml':
        if parse_xml(content).tag.rsplit('}', maxsplit=1)[-1] != 'project':
            msg = 'Ожидается Maven project'
            raise TypeError(msg)
    elif name == 'pip.conf':
        ConfigParser(interpolation=None).read_string(text)
    elif is_requirements_filename(name):
        _validate_requirements(text)


def _validate_toml(name: str, text: str) -> None:
    document = tomllib.loads(text)
    if name == 'pyproject.toml':
        _validate_pyproject(document)
    if name == 'uv.lock':
        if document.get('version') != 1:
            msg = 'Неподдерживаемая версия uv.lock'
            raise UnsupportedFormatError(msg)
        packages = document.get('package', [])
        if not isinstance(packages, list) or any(
            not isinstance(package, dict) or not isinstance(package.get('name'), str) for package in packages
        ):
            msg = 'Некорректный список пакетов uv.lock'
            raise TypeError(msg)
    if name == 'libs.versions.toml' and any(
        not isinstance(document.get(section, {}), dict) for section in ('versions', 'libraries')
    ):
        msg = 'Некорректный Gradle version catalog'
        raise TypeError(msg)


def _validate_requirements(text: str) -> None:
    for raw_line in text.replace('\\\n', '').splitlines():
        line = raw_line.strip()
        if not line or line.startswith(('#', '-')):
            continue
        Requirement(line.split(' #', maxsplit=1)[0])


def _validate_pyproject(document: dict) -> None:
    project = document.get('project', {})
    tool = document.get('tool', {})
    if not isinstance(project, dict) or not isinstance(tool, dict):
        msg = 'Некорректная секция project или tool'
        raise TypeError(msg)
    uv = tool.get('uv', {})
    if not isinstance(uv, dict):
        msg = 'Некорректная секция tool.uv'
        raise TypeError(msg)
    groups = [project.get('dependencies', []), uv.get('dev-dependencies', [])]
    for source in (project.get('optional-dependencies', {}), document.get('dependency-groups', {})):
        if not isinstance(source, dict):
            msg = 'Некорректная секция групп зависимостей'
            raise TypeError(msg)
        groups.extend(source.values())
    for group in groups:
        if not isinstance(group, list):
            msg = 'Ожидается список зависимостей'
            raise TypeError(msg)
        for requirement in group:
            if isinstance(requirement, dict) and set(requirement) == {'include-group'}:
                continue
            Requirement(requirement)


def _validate_json(name: str, text: str) -> None:
    document = json.loads(text)
    if not isinstance(document, dict):
        msg = 'Ожидается JSON object'
        raise TypeError(msg)
    if name == 'package.json':
        for field in ('dependencies', 'devDependencies', 'optionalDependencies', 'peerDependencies'):
            values = document.get(field, {})
            if not isinstance(values, dict) or any(not isinstance(value, str) for value in values.values()):
                msg = 'Некорректная секция зависимостей'
                raise TypeError(msg)


def _validate_yaml(name: str, text: str) -> None:
    document = parse_yaml(text)
    if document is not None and not isinstance(document, dict):
        msg = 'Ожидается YAML mapping'
        raise TypeError(msg)
    if name in {'compose.yaml', 'compose.yml', 'docker-compose.yaml', 'docker-compose.yml'} and (
        not isinstance(document, dict) or not isinstance(document.get('services'), dict)
    ):
        msg = 'Отсутствует секция services'
        raise TypeError(msg)


def _limitations(project: Project, path: str, content: bytes) -> None:
    name = PurePosixPath(path).name
    text = content.decode('utf-8-sig')
    if is_requirements_filename(name) and any(
        line.lstrip().startswith(('-r ', '-c ', '--requirement', '--constraint')) for line in text.splitlines()
    ):
        report(
            project,
            path,
            'Включаемые requirements/constraints не разрешаются автоматически',
            status=DiagnosticStatus.PARTIAL,
        )
    if name == 'pom.xml' and '<profiles' in text:
        report(project, path, 'Maven profiles не активируются при статическом анализе', status=DiagnosticStatus.PARTIAL)
