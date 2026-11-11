import re
import tomllib
from collections import defaultdict
from pathlib import PurePosixPath

from gitlab_radar.schemas.dependency import Dependency, DependencyGroup
from gitlab_radar.schemas.project import Project, ProjectSubproject
from gitlab_radar.schemas.technology import PackageManager
from gitlab_radar.services.analysis.base import FileSelection
from gitlab_radar.services.container_parser import parse_container_images
from gitlab_radar.services.package_manager import is_container_filename

MAVEN_FILENAME = 'pom.xml'
GRADLE_BUILD_FILENAMES = frozenset({'build.gradle', 'build.gradle.kts'})
GRADLE_CONFIG_FILENAMES = frozenset({
    'settings.gradle',
    'settings.gradle.kts',
    'gradle.properties',
    'gradle.lockfile',
    'libs.versions.toml',
})
JAVA_FILENAMES = frozenset({MAVEN_FILENAME, *GRADLE_BUILD_FILENAMES, *GRADLE_CONFIG_FILENAMES})
MAVEN_DEPENDENCY_MANAGEMENT_PATTERN = re.compile(
    r'<dependencyManagement\b[^>]*>.*?</dependencyManagement>',
    re.DOTALL,
)
MAVEN_BUILD_PATTERN = re.compile(r'<build\b[^>]*>.*?</build>', re.DOTALL)
MAVEN_DEPENDENCY_PATTERN = re.compile(r'<dependency\b[^>]*>(.*?)</dependency>', re.DOTALL)
MAVEN_PROPERTIES_PATTERN = re.compile(r'<properties\b[^>]*>(.*?)</properties>', re.DOTALL)
MAVEN_PROPERTY_PATTERN = re.compile(r'<([A-Za-z0-9_.-]+)\b[^>]*>\s*([^<]+?)\s*</\1>')
MAVEN_REPOSITORY_PATTERN = re.compile(r'<repository\b[^>]*>(.*?)</repository>', re.DOTALL)
GRADLE_DIRECT_CONFIGURATIONS = frozenset({
    'api',
    'implementation',
    'compileOnly',
    'runtimeOnly',
    'annotationProcessor',
    'kapt',
})
GRADLE_OPTIONAL_CONFIGURATIONS = frozenset({
    'testImplementation',
    'testCompileOnly',
    'testRuntimeOnly',
    'testAnnotationProcessor',
})
GRADLE_CONFIGURATIONS = GRADLE_DIRECT_CONFIGURATIONS | GRADLE_OPTIONAL_CONFIGURATIONS
GRADLE_COORDINATE_PATTERN = re.compile(
    r'^\s*(?P<configuration>[A-Za-z][A-Za-z0-9]*)\s*'
    r'(?:\(\s*)?(?:platform\s*\(\s*)?["\'](?P<coordinate>[^"\']+)["\']',
    re.MULTILINE,
)
GRADLE_MAP_PATTERN = re.compile(
    r'^\s*(?P<configuration>[A-Za-z][A-Za-z0-9]*)\s*'
    r'(?:\(\s*)?group\s*[:=]\s*["\'](?P<group>[^"\']+)["\']\s*,\s*'
    r'name\s*[:=]\s*["\'](?P<name>[^"\']+)["\']'
    r'(?:\s*,\s*version\s*[:=]\s*["\'](?P<version>[^"\']+)["\'])?',
    re.MULTILINE,
)
GRADLE_ALIAS_PATTERN = re.compile(
    r'^\s*(?P<configuration>[A-Za-z][A-Za-z0-9]*)\s*'
    r'(?:\(\s*)?libs\.(?P<alias>[A-Za-z0-9_.-]+)',
    re.MULTILINE,
)
GRADLE_LOCK_PATTERN = re.compile(
    r'^(?P<group>[^:#=\s]+):(?P<name>[^:#=\s]+):(?P<version>[^=\s]+)(?:=.*)?$',
    re.MULTILINE,
)
GRADLE_REPOSITORY_PATTERN = re.compile(
    r'(?:url\s*=\s*(?:uri\s*\()?|url\s+)["\'](?P<url>https?://[^"\']+)',
)
GRADLE_VERSION_PATTERNS = (
    re.compile(r'JavaLanguageVersion\.of\s*\(\s*(\d+)\s*\)'),
    re.compile(r'JavaVersion\.VERSION_(\d+)(?:_\d+)?'),
    re.compile(r'(?:sourceCompatibility|targetCompatibility)\s*=\s*["\']?(\d+(?:\.\d+)*)'),
    re.compile(r'^(?:javaVersion|java_version)\s*=\s*(\d+(?:\.\d+)*)\s*$', re.MULTILINE),
)


class JavaAnalyzer:
    key = 'java'
    language_code = 'java'
    version = '1'
    package_manager_codes = ('maven', 'gradle')

    def select_files(self, repository_paths: list[str]) -> list[FileSelection]:
        return [
            FileSelection(
                path=path,
                analyzer_key=self.key,
                language_code=self.language_code,
                role=_file_role(PurePosixPath(path).name),
            )
            for path in repository_paths
            if _is_java_analysis_file(PurePosixPath(path).name)
        ]

    def analyze(self, project: Project, files: dict[str, bytes]) -> list[ProjectSubproject]:
        del project
        manifests = _module_manifests(files)
        version_catalog = _gradle_version_catalog(files)
        return [
            _build_maven_subproject(path, files[manifest], _module_files(path, files))
            if PurePosixPath(manifest).name == MAVEN_FILENAME
            else _build_gradle_subproject(path, files[manifest], _module_files(path, files), version_catalog)
            for path, manifest in manifests
        ]


def _module_manifests(files: dict[str, bytes]) -> list[tuple[str, str]]:
    by_directory: dict[str, list[str]] = defaultdict(list)
    for path in files:
        if PurePosixPath(path).name in {MAVEN_FILENAME, *GRADLE_BUILD_FILENAMES}:
            by_directory[_parent_directory(path)].append(path)
    manifests: list[tuple[str, str]] = []
    for directory, paths in sorted(by_directory.items()):
        paths.sort(key=lambda path: (PurePosixPath(path).name != MAVEN_FILENAME, path))
        manifests.append((directory or '.', paths[0]))
    return manifests


def _module_files(directory: str, files: dict[str, bytes]) -> dict[str, bytes]:
    target_directory = '' if directory == '.' else directory
    return {
        path: content
        for path, content in files.items()
        if _parent_directory(path) == target_directory
        or PurePosixPath(path).name == 'libs.versions.toml'
        or (
            _parent_directory(path) == ''
            and PurePosixPath(path).name in GRADLE_CONFIG_FILENAMES | GRADLE_BUILD_FILENAMES
        )
    }


def _build_maven_subproject(
    path: str,
    manifest: bytes,
    files: dict[str, bytes],
) -> ProjectSubproject:
    text = _decode(manifest)
    properties = _maven_properties(text)
    dependencies: list[Dependency] = []
    optional: dict[str, list[Dependency]] = defaultdict(list)
    project_dependencies = MAVEN_BUILD_PATTERN.sub(
        '',
        MAVEN_DEPENDENCY_MANAGEMENT_PATTERN.sub('', text),
    )
    for node in MAVEN_DEPENDENCY_PATTERN.findall(project_dependencies):
        group = _resolved_maven_tag(node, 'groupId', properties)
        artifact = _resolved_maven_tag(node, 'artifactId', properties)
        if not group or not artifact:
            continue
        dependency = Dependency(
            name=f'{group}:{artifact}',
            version=_resolved_maven_tag(node, 'version', properties),
        )
        scope = _resolved_maven_tag(node, 'scope', properties) or 'compile'
        is_optional = _resolved_maven_tag(node, 'optional', properties) == 'true'
        if scope in {'test', 'provided'} or is_optional:
            optional['optional' if is_optional else scope].append(dependency)
        else:
            dependencies.append(dependency)
    runtime_version = _maven_java_version(text, properties)
    return ProjectSubproject(
        path=path,
        language='java',
        package_manager=PackageManager.MAVEN,
        runtime_version=runtime_version,
        dependencies=_unique_dependencies(dependencies),
        optional_dependencies=[
            DependencyGroup(name=name, dependencies=_unique_dependencies(items))
            for name, items in sorted(optional.items())
        ],
        package_registries=_maven_repositories(text, properties),
        container_images=parse_container_images(files),
        has_docker=any(is_container_filename(PurePosixPath(file_path).name) for file_path in files),
    )


def _maven_properties(text: str) -> dict[str, str]:
    match = MAVEN_PROPERTIES_PATTERN.search(text)
    properties = dict(MAVEN_PROPERTY_PATTERN.findall(match.group(1))) if match else {}
    project_header = re.sub(
        r'<parent\b[^>]*>.*?</parent>',
        '',
        text.partition('<dependencies')[0],
        flags=re.DOTALL,
    )
    for name in ('groupId', 'artifactId', 'version'):
        if value := _maven_tag(project_header, name):
            properties[f'project.{name}'] = value
            properties[f'pom.{name}'] = value
    return properties


def _maven_java_version(text: str, properties: dict[str, str]) -> str | None:
    for name in ('maven.compiler.release', 'maven.compiler.source', 'java.version', 'jdk.version'):
        if value := _resolve(properties.get(name), properties):
            return value
    for name in ('release', 'source', 'target'):
        value = _resolve(_maven_tag(text, name), properties)
        if value and re.fullmatch(r'\d+(?:\.\d+)*', value):
            return value
    return None


def _maven_repositories(text: str, properties: dict[str, str]) -> list[str]:
    return sorted({
        url
        for node in MAVEN_REPOSITORY_PATTERN.findall(text)
        if (url := _resolved_maven_tag(node, 'url', properties))
    })


def _build_gradle_subproject(
    path: str,
    manifest: bytes,
    files: dict[str, bytes],
    version_catalog: dict[str, Dependency],
) -> ProjectSubproject:
    text = _decode(manifest)
    dependencies: list[Dependency] = []
    optional: list[Dependency] = []
    for match in GRADLE_COORDINATE_PATTERN.finditer(text):
        dependency = _coordinate_dependency(match.group('coordinate'))
        _append_gradle_dependency(match.group('configuration'), dependency, dependencies, optional)
    for match in GRADLE_MAP_PATTERN.finditer(text):
        dependency = Dependency(
            name=f"{match.group('group')}:{match.group('name')}",
            version=match.group('version'),
        )
        _append_gradle_dependency(match.group('configuration'), dependency, dependencies, optional)
    for match in GRADLE_ALIAS_PATTERN.finditer(text):
        dependency = version_catalog.get(_normalize_gradle_alias(match.group('alias')))
        _append_gradle_dependency(match.group('configuration'), dependency, dependencies, optional)
    direct_names = {dependency.name for dependency in dependencies + optional}
    transitive = [
        dependency
        for dependency in _gradle_locked_dependencies(files)
        if dependency.name not in direct_names
    ]
    all_text = '\n'.join(_decode(content) for content in files.values())
    runtime_version = next(
        (match.group(1) for pattern in GRADLE_VERSION_PATTERNS if (match := pattern.search(all_text))),
        None,
    )
    return ProjectSubproject(
        path=path,
        language='java',
        package_manager=PackageManager.GRADLE,
        runtime_version=runtime_version,
        dependencies=_unique_dependencies(dependencies),
        optional_dependencies=(
            [DependencyGroup(name='test', dependencies=_unique_dependencies(optional))]
            if optional
            else []
        ),
        transitive_dependencies=_unique_dependencies(transitive),
        package_registries=sorted(set(GRADLE_REPOSITORY_PATTERN.findall(all_text))),
        container_images=parse_container_images(files),
        has_docker=any(is_container_filename(PurePosixPath(file_path).name) for file_path in files),
    )


def _append_gradle_dependency(
    configuration: str,
    dependency: Dependency | None,
    direct: list[Dependency],
    optional: list[Dependency],
) -> None:
    if dependency is None or configuration not in GRADLE_CONFIGURATIONS:
        return
    (optional if configuration in GRADLE_OPTIONAL_CONFIGURATIONS else direct).append(dependency)


def _coordinate_dependency(value: str) -> Dependency | None:
    try:
        group, name, *versions = value.split(':')
    except ValueError:
        return None
    if not group or not name:
        return None
    return Dependency(name=f'{group}:{name}', version=versions[0] if versions else None)


def _gradle_locked_dependencies(files: dict[str, bytes]) -> list[Dependency]:
    result: list[Dependency] = []
    for path, content in files.items():
        if PurePosixPath(path).name != 'gradle.lockfile':
            continue
        result.extend(
            Dependency(
                name=f"{match.group('group')}:{match.group('name')}",
                version=match.group('version'),
            )
            for match in GRADLE_LOCK_PATTERN.finditer(_decode(content))
        )
    return result


def _gradle_version_catalog(files: dict[str, bytes]) -> dict[str, Dependency]:
    catalog_content = next(
        (content for path, content in files.items() if PurePosixPath(path).name == 'libs.versions.toml'),
        None,
    )
    if catalog_content is None:
        return {}
    document = tomllib.loads(_decode(catalog_content))
    versions = document.get('versions', {})
    libraries = document.get('libraries', {})
    if not isinstance(versions, dict) or not isinstance(libraries, dict):
        return {}
    result: dict[str, Dependency] = {}
    for alias, definition in libraries.items():
        dependency = _catalog_dependency(definition, versions)
        if dependency is not None:
            result[_normalize_gradle_alias(str(alias))] = dependency
    return result


def _catalog_dependency(definition: object, versions: dict[str, object]) -> Dependency | None:
    if isinstance(definition, str):
        return _coordinate_dependency(definition)
    if not isinstance(definition, dict):
        return None
    module = definition.get('module')
    if not isinstance(module, str):
        group, name = definition.get('group'), definition.get('name')
        module = f'{group}:{name}' if isinstance(group, str) and isinstance(name, str) else None
    if module is None:
        return None
    version = definition.get('version')
    if isinstance(version, dict):
        reference = version.get('ref')
        version = versions.get(reference) if isinstance(reference, str) else None
    elif not isinstance(version, str):
        reference = definition.get('version.ref')
        version = versions.get(reference) if isinstance(reference, str) else None
    return _coordinate_dependency(f'{module}:{version}' if isinstance(version, str) else module)


def _unique_dependencies(items: list[Dependency]) -> list[Dependency]:
    result: dict[tuple[str, str | None], Dependency] = {}
    for item in items:
        result[(item.name, item.version)] = item
    return sorted(result.values(), key=lambda item: (item.name, item.version or ''))


def _resolve(value: str | None, properties: dict[str, str]) -> str | None:
    if not value:
        return None
    result = value.strip()
    for _ in range(5):
        updated = re.sub(
            r'\$\{([^}]+)\}',
            lambda match: properties.get(match.group(1), match.group(0)),
            result,
        )
        if updated == result:
            break
        result = updated
    return result if '${' not in result else None


def _resolved_maven_tag(text: str, name: str, properties: dict[str, str]) -> str | None:
    return _resolve(_maven_tag(text, name), properties)


def _maven_tag(text: str, name: str) -> str | None:
    match = re.search(rf'<{name}\b[^>]*>\s*([^<]+?)\s*</{name}>', text)
    return match.group(1).strip() if match else None


def _normalize_gradle_alias(value: str) -> str:
    return re.sub(r'[-_.]+', '.', value).casefold()


def _decode(content: bytes) -> str:
    return content.decode('utf-8')


def _is_java_analysis_file(filename: str) -> bool:
    return filename in JAVA_FILENAMES or is_container_filename(filename)


def _file_role(filename: str) -> str:
    if filename == 'gradle.lockfile':
        return 'lock'
    if filename in {MAVEN_FILENAME, *GRADLE_BUILD_FILENAMES}:
        return 'manifest'
    return 'config'


def _parent_directory(path: str) -> str:
    parent = str(PurePosixPath(path).parent)
    return '' if parent == '.' else parent
