import logging
from pathlib import PurePosixPath

from gitlab_radar.config import settings
from gitlab_radar.schemas.project import Project, ProjectSubproject
from gitlab_radar.schemas.technology import PackageManager
from gitlab_radar.services.container_parser import parse_container_images
from gitlab_radar.services.dependency_parser import parse_pyproject_document
from gitlab_radar.services.gitlab_ci import parse_gitlab_components
from gitlab_radar.services.package_manager import (
    PYPROJECT_FILENAME,
    detect_package_manager,
    is_container_filename,
    is_package_discovery_filename,
    is_subproject_filename,
)
from gitlab_radar.services.project_collection import GITLAB_CI_FILENAMES
from gitlab_radar.services.project_metadata import parse_project_metadata

logger = logging.getLogger(__name__)


def analyze_project(project: Project, files: dict[str, str], revision: str | None) -> Project:
    contents = {path: content.encode() for path, content in files.items()}
    file_sets = _build_file_sets(contents)
    ci_files = {path: content for path, content in contents.items() if PurePosixPath(path).name in GITLAB_CI_FILENAMES}
    project.revision = revision
    project.subprojects = [_build_subproject(path, file_set) for path, file_set in file_sets]
    project.package_manager = _project_package_manager(project.subprojects)
    project.has_docker = any(is_container_filename(PurePosixPath(path).name) for path in contents)
    project.has_gitlab_ci = bool(ci_files)
    project.gitlab_ci_components = parse_gitlab_components(ci_files, settings.gitlab.url)
    project.container_images = parse_container_images(contents)
    project.package_registries = sorted(
        {registry for item in project.subprojects for registry in item.package_registries}
    )
    project.scan_error = None
    logger.info(
        'Проект %s проанализирован: подпроектов %d, файлов %d',
        project.path_with_namespace,
        len(project.subprojects),
        len(contents),
    )
    return project


def _build_file_sets(files: dict[str, bytes]) -> list[tuple[str, dict[str, bytes]]]:
    subproject_files = {
        path: content for path, content in files.items() if is_subproject_filename(PurePosixPath(path).name)
    }
    directories = {
        _parent_directory(path) for path in subproject_files if is_package_discovery_filename(PurePosixPath(path).name)
    }
    if not directories:
        return [('.', subproject_files)]
    return [
        (
            directory or '.',
            {
                path: content
                for path, content in sorted(subproject_files.items())
                if _parent_directory(path) == directory
            },
        )
        for directory in sorted(directories)
    ]


def _build_subproject(path: str, files: dict[str, bytes]) -> ProjectSubproject:
    files_by_name = {PurePosixPath(file_path).name: content for file_path, content in files.items()}
    pyproject = parse_pyproject_document(files_by_name.get(PYPROJECT_FILENAME))
    metadata = parse_project_metadata(files_by_name, pyproject)
    return ProjectSubproject(
        path=path,
        package_manager=detect_package_manager(pyproject, files_by_name),
        python_version=metadata.python_version,
        python_constraint=metadata.python_constraint,
        python_version_source=metadata.python_version_source,
        dependencies=metadata.dependencies,
        optional_dependencies=metadata.optional_dependencies,
        transitive_dependencies=metadata.transitive_dependencies,
        configured_tools=metadata.configured_tools,
        package_registries=metadata.package_registries,
        container_images=parse_container_images(files),
        has_docker=any(is_container_filename(name) for name in files_by_name),
    )


def _project_package_manager(subprojects: list[ProjectSubproject]) -> PackageManager:
    if not subprojects:
        return PackageManager.UNKNOWN
    managers = {subproject.package_manager for subproject in subprojects}
    return managers.pop() if len(managers) == 1 else PackageManager.MIXED


def _parent_directory(path: str) -> str:
    parent = str(PurePosixPath(path).parent)
    return '' if parent == '.' else parent
