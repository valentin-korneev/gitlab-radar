from functools import partial
from pathlib import PurePosixPath

from gitlab_radar.schemas.project import Project, ProjectSubproject
from gitlab_radar.services.analysis.base import FileSelection
from gitlab_radar.services.analysis.diagnostics import analyze_module
from gitlab_radar.services.container_parser import parse_container_images
from gitlab_radar.services.dependency_parser import parse_pyproject_document
from gitlab_radar.services.package_manager import (
    PYPROJECT_FILENAME,
    detect_package_manager,
    is_package_discovery_filename,
    is_subproject_filename,
)
from gitlab_radar.services.project_metadata import parse_project_metadata


class PythonAnalyzer:
    key = 'python'
    language_code = 'python'
    version = '2'
    package_manager_codes = ('pip', 'uv')

    def select_files(self, repository_paths: list[str]) -> list[FileSelection]:
        return [
            FileSelection(
                path=path,
                analyzer_key=self.key,
                language_code=self.language_code,
                role=_file_role(PurePosixPath(path).name),
            )
            for path in repository_paths
            if is_subproject_filename(PurePosixPath(path).name)
        ]

    def analyze(self, project: Project, files: dict[str, bytes]) -> list[ProjectSubproject]:
        return [
            module
            for path, file_set in _build_file_sets(files)
            if (module := analyze_module(project, self.language_code, path, partial(_build_subproject, path, file_set)))
            is not None
        ]


def _build_file_sets(files: dict[str, bytes]) -> list[tuple[str, dict[str, bytes]]]:
    subproject_files = {
        path: content for path, content in files.items() if is_subproject_filename(PurePosixPath(path).name)
    }
    directories = {
        _parent_directory(path) for path in subproject_files if is_package_discovery_filename(PurePosixPath(path).name)
    }
    if not directories:
        return [('.', subproject_files)] if subproject_files else []
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
        language='python',
        package_manager=detect_package_manager(pyproject, files_by_name),
        runtime_version=metadata.python_version or metadata.python_constraint,
        python_version=metadata.python_version,
        python_constraint=metadata.python_constraint,
        python_version_source=metadata.python_version_source,
        dependencies=metadata.dependencies,
        optional_dependencies=metadata.optional_dependencies,
        transitive_dependencies=metadata.transitive_dependencies,
        configured_tools=metadata.configured_tools,
        package_registries=metadata.package_registries,
        container_images=parse_container_images(files),
        has_docker=any(PurePosixPath(file_path).name.lower().startswith('dockerfile') for file_path in files),
    )


def _file_role(filename: str) -> str:
    if filename.endswith('.lock'):
        return 'lock'
    if is_package_discovery_filename(filename):
        return 'manifest'
    return 'config'


def _parent_directory(path: str) -> str:
    parent = str(PurePosixPath(path).parent)
    return '' if parent == '.' else parent
