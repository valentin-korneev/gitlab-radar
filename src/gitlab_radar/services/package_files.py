import logging
from http import HTTPStatus
lazy from collections.abc import Callable
lazy from pathlib import Path, PurePosixPath

from gitlab.exceptions import GitlabError, GitlabGetError
lazy from gitlab.v4.objects import Project as GitLabProject

from gitlab_radar.clients.gitlab import gitlab_client
from gitlab_radar.schemas.project import ProjectSubproject
from gitlab_radar.schemas.technology import PackageManager
from gitlab_radar.services.company_rules import project_compliance_percentage
from gitlab_radar.services.gitlab_ci import parse_gitlab_components
from gitlab_radar.services.package_manager import (
    CONTAINER_FILES,
    PACKAGE_DISCOVERY_FILES,
    PYPROJECT_FILENAME,
    SUBPROJECT_FILES,
    detect_package_manager,
)
from gitlab_radar.services.project_metadata import parse_project_metadata
lazy from gitlab_radar.schemas.project import Project

logger = logging.getLogger(__name__)

GITLAB_CI_FILENAMES = ('.gitlab-ci.yml', '.gitlab-ci.yaml')
TARGET_FILENAMES = frozenset((*SUBPROJECT_FILES, *GITLAB_CI_FILENAMES))
TARGET_SEARCH_PATTERNS = (
    r'(^|/)(pyproject\.toml|uv\.(toml|lock)|poetry\.lock|Pipfile(\.lock)?|requirements\.txt)$',
    r'(^|/)(environment\.ya?ml|conda-lock\.ya?ml|\.python-version)$',
    r'(^|/)([Dd]ockerfile|(docker-)?compose\.ya?ml|\.gitlab-ci\.ya?ml)$',
)

class PackageFilesService:
    def __init__(self, projects_directory: Path) -> None:
        self._projects_directory = projects_directory
        self._combined_search_supported: bool | None = None

    def scan_projects(
        self,
        projects: list[Project],
        progress: Callable[[int, int], None] | None = None,
    ) -> list[str]:
        errors: list[str] = []
        total = len(projects)
        logger.info('Последовательная обработка файлов: проектов %d', total)
        for number, project in enumerate(projects, start=1):
            logger.info(
                'Обработка проекта %d/%d (%s)',
                number,
                total,
                project.path_with_namespace,
            )
            try:
                files = self._fetch_project_files(project)
                self._analyze_project_files(project, files)
            except Exception as error:
                project.package_manager = PackageManager.UNKNOWN
                errors.append(f'{project.path_with_namespace}: {error}')
                logger.exception('Не удалось обработать проект %s', project.path_with_namespace)
            finally:
                if progress:
                    progress(number, total)
        logger.info(
            'Обработка файлов завершена: успешно %d, ошибок %d',
            len(projects) - len(errors),
            len(errors),
        )
        return errors

    def _fetch_project_files(self, project: Project) -> dict[str, bytes]:
        if not project.default_branch:
            msg = f'Проект {project.path_with_namespace} не имеет основной ветки'
            raise ValueError(msg)

        logger.info(
            'Обработка проекта %s: id=%d, ветка=%s',
            project.path_with_namespace,
            project.id,
            project.default_branch,
        )
        gitlab_project = gitlab_client.projects.get(project.id, lazy=True)
        paths = self._find_target_file_paths(gitlab_project, project.default_branch)
        files = {
            path: self._read_file(gitlab_project, path, project.default_branch)
            for path in paths
        }
        if '.gitlab-ci.yml' not in files:
            ci_content = self._read_file_if_exists(gitlab_project, '.gitlab-ci.yml', project.default_branch)
            if ci_content is not None:
                files['.gitlab-ci.yml'] = ci_content
        return files

    def _analyze_project_files(self, project: Project, files: dict[str, bytes]) -> None:
        self._save_files(project, [files] if files else [])
        file_sets = self._build_file_sets(files)
        ci_files = {
            path: content
            for path, content in files.items()
            if PurePosixPath(path).name in GITLAB_CI_FILENAMES
        }
        project.subprojects = [self._build_subproject(file_set) for file_set in file_sets]
        project.package_manager = self._project_package_manager(project.subprojects)
        project.has_docker = any(
            PurePosixPath(path).name in CONTAINER_FILES
            for path in files
        )
        project.has_gitlab_ci = bool(ci_files)
        project.gitlab_ci_components = parse_gitlab_components(ci_files)
        project.company_compliance_percentage = project_compliance_percentage(project)
        for subproject in project.subprojects:
            logger.info(
                'Подпроект %s: пакетный менеджер %s, Python %s, зависимостей %d',
                subproject.path,
                subproject.package_manager,
                subproject.python_version or 'не определён',
                len(subproject.dependencies)
                + sum(len(group.dependencies) for group in subproject.optional_dependencies)
                + len(subproject.transitive_dependencies),
            )
        logger.info(
            'Проект %s обработан: подпроектов %d, пакетный менеджер %s, '
            'Docker: %s, GitLab CI: %s, компонентов: %d',
            project.path_with_namespace,
            len(file_sets),
            project.package_manager,
            'да' if project.has_docker else 'нет',
            'да' if project.has_gitlab_ci else 'нет',
            len(project.gitlab_ci_components),
        )

    def _find_target_file_paths(
        self,
        project: GitLabProject,
        default_branch: str,
    ) -> list[str]:
        if self._combined_search_supported is not False:
            try:
                paths = self._find_paths_with_combined_search(project)
            except GitlabError as error:
                if error.response_code not in {
                    HTTPStatus.BAD_REQUEST,
                    HTTPStatus.FORBIDDEN,
                    HTTPStatus.NOT_FOUND,
                    HTTPStatus.UNPROCESSABLE_ENTITY,
                }:
                    raise
                self._combined_search_supported = False
                logger.warning(
                    'Объединённый поиск файлов недоступен; используется поиск по отдельным именам',
                )
            else:
                if paths:
                    self._combined_search_supported = True
                    return paths
                fallback_paths = self._find_paths_separately(project, default_branch)
                if fallback_paths:
                    self._combined_search_supported = False
                    logger.warning(
                        'Объединённый поиск не вернул файлы; используется поиск по отдельным именам',
                    )
                return fallback_paths

        return self._find_paths_separately(project, default_branch)

    def _find_paths_separately(self, project: GitLabProject, default_branch: str) -> list[str]:
        paths = {
            path
            for filename in TARGET_FILENAMES
            for path in self._find_file_paths(project, filename, default_branch)
        }
        return sorted(paths, key=lambda value: (value.count('/'), value))

    @staticmethod
    def _find_paths_with_combined_search(project: GitLabProject) -> list[str]:
        paths: set[str] = set()
        for pattern in TARGET_SEARCH_PATTERNS:
            results = project.search(
                scope='blobs',
                search=pattern,
                search_type='zoekt',
                regex=True,
                iterator=True,
                per_page=100,
            )
            for result in results:
                path = result.get('path')
                if isinstance(path, str) and PurePosixPath(path).name in TARGET_FILENAMES:
                    paths.add(path)
        sorted_paths = sorted(paths, key=lambda value: (value.count('/'), value))
        logger.info('Объединённый поиск завершён: найдено файлов %d', len(sorted_paths))
        return sorted_paths

    @staticmethod
    def _build_file_sets(files: dict[str, bytes]) -> list[dict[str, bytes]]:
        subproject_files = {
            path: content
            for path, content in files.items()
            if PurePosixPath(path).name in SUBPROJECT_FILES
        }
        pyproject_directories = {
            PackageFilesService._parent_directory(path)
            for path in subproject_files
            if PurePosixPath(path).name == PYPROJECT_FILENAME
        }
        directories = pyproject_directories or {
            PackageFilesService._parent_directory(path)
            for path in subproject_files
            if PurePosixPath(path).name in PACKAGE_DISCOVERY_FILES
        }
        return [
            {
                path: content
                for path, content in sorted(subproject_files.items())
                if PackageFilesService._parent_directory(path) == directory
            }
            for directory in sorted(directories)
        ]

    @staticmethod
    def _find_file_paths(project: GitLabProject, filename: str, default_branch: str) -> list[str]:
        logger.info('Поиск %s в ветке %s', filename, default_branch)
        results = project.search(
            scope='blobs',
            search=filename,
            ref=default_branch,
            iterator=True,
            per_page=100,
        )
        paths: set[str] = set()
        for result in results:
            path = result.get('path')
            if isinstance(path, str) and PurePosixPath(path).name == filename:
                paths.add(path)
        sorted_paths = sorted(paths, key=lambda value: (value.count('/'), value))
        logger.info('Поиск %s завершён: найдено %d', filename, len(sorted_paths))
        return sorted_paths

    @staticmethod
    def _read_file_if_exists(
        project: GitLabProject,
        file_path: str,
        default_branch: str,
    ) -> bytes | None:
        try:
            return PackageFilesService._read_file(project, file_path, default_branch)
        except GitlabGetError as error:
            if error.response_code == HTTPStatus.NOT_FOUND:
                return None
            raise

    @staticmethod
    def _read_file(project: GitLabProject, file_path: str, default_branch: str) -> bytes:
        content = project.files.raw(file_path=file_path, ref=default_branch)
        if not isinstance(content, bytes):
            msg = f'GitLab вернул неожиданный тип содержимого файла: {type(content).__name__}'
            raise TypeError(msg)
        return content

    def _save_files(self, project: Project, file_sets: list[dict[str, bytes]]) -> None:
        project_directory = self._projects_directory / str(project.id)
        for files in file_sets:
            for file_path, content in files.items():
                relative_path = PurePosixPath(file_path)
                if relative_path.is_absolute() or '..' in relative_path.parts:
                    msg = f'GitLab вернул небезопасный путь: {file_path}'
                    raise ValueError(msg)
                destination = project_directory.joinpath(*relative_path.parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(content)
                logger.info('%s сохранён: %s', file_path, destination)

    @staticmethod
    def _build_subproject(files: dict[str, bytes]) -> ProjectSubproject:
        path = PackageFilesService._file_set_directory(files) or '.'
        files_by_name = {PurePosixPath(file_path).name: content for file_path, content in files.items()}
        pyproject_content = files_by_name.get(PYPROJECT_FILENAME)
        metadata = parse_project_metadata(files_by_name)
        return ProjectSubproject(
            path=path,
            package_manager=detect_package_manager(
                pyproject_content,
                files_by_name,
            ),
            python_version=metadata.python_version,
            dependencies=metadata.dependencies,
            optional_dependencies=metadata.optional_dependencies,
            transitive_dependencies=metadata.transitive_dependencies,
            has_docker=any(name in CONTAINER_FILES for name in files_by_name),
        )

    @staticmethod
    def _project_package_manager(subprojects: list[ProjectSubproject]) -> PackageManager:
        if not subprojects:
            return PackageManager.PIP

        managers = {subproject.package_manager for subproject in subprojects}
        if len(managers) == 1:
            return managers.pop()
        return PackageManager.UNKNOWN

    @staticmethod
    def _parent_directory(path: str) -> str:
        parent = str(PurePosixPath(path).parent)
        return '' if parent == '.' else parent

    @staticmethod
    def _file_set_directory(files: dict[str, bytes]) -> str:
        return PackageFilesService._parent_directory(next(iter(files)))
