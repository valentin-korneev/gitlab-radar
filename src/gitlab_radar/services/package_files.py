import logging
from http import HTTPStatus
lazy from pathlib import Path, PurePosixPath

from gitlab.exceptions import GitlabGetError
lazy from gitlab.v4.objects import Project as GitLabProject

from gitlab_radar.clients.gitlab import gitlab_client
from gitlab_radar.schemas.project import ProjectSubproject
from gitlab_radar.schemas.technology import PackageManager
from gitlab_radar.services.package_manager import PACKAGE_FILES, PYPROJECT_FILENAME, detect_package_manager
lazy from gitlab_radar.schemas.project import Project

logger = logging.getLogger(__name__)


class PackageFilesService:
    def __init__(self, projects_directory: Path) -> None:
        self._projects_directory = projects_directory

    def scan_projects(self, projects: list[Project]) -> list[str]:
        errors: list[str] = []
        logger.info('Обработка файлов пакетных менеджеров: проектов %d', len(projects))
        for number, project in enumerate(projects, start=1):
            logger.info(
                'Поиск файлов пакетного менеджера: проект %d/%d (%s)',
                number,
                len(projects),
                project.path_with_namespace,
            )
            try:
                self.scan_project(project)
            except Exception as error:
                project.package_manager = PackageManager.UNKNOWN
                errors.append(f'{project.path_with_namespace}: {error}')
                logger.exception('Не удалось обработать проект %s', project.path_with_namespace)
        logger.info(
            'Обработка файлов завершена: успешно %d, ошибок %d',
            len(projects) - len(errors),
            len(errors),
        )
        return errors

    def scan_project(self, project: Project) -> None:
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
        file_sets = self._get_file_sets(gitlab_project, project.default_branch)
        self._save_files(project, file_sets)
        project.subprojects = [self._build_subproject(files) for files in file_sets]
        project.package_manager = self._project_package_manager(project.subprojects)
        for subproject in project.subprojects:
            logger.info(
                'Подпроект %s: пакетный менеджер %s',
                subproject.path,
                subproject.package_manager,
            )
        logger.info(
            'Проект %s обработан: подпроектов %d, итоговый пакетный менеджер %s',
            project.path_with_namespace,
            len(file_sets),
            project.package_manager,
        )

    def _get_file_sets(self, project: GitLabProject, default_branch: str) -> list[dict[str, bytes]]:
        pyproject_paths = self._find_file_paths(project, PYPROJECT_FILENAME, default_branch)
        if pyproject_paths:
            logger.info('Найдено файлов pyproject.toml: %d', len(pyproject_paths))
            return [self._read_file_set(project, path, default_branch) for path in pyproject_paths]

        logger.info('Файл pyproject.toml не найден; поиск конфигураций и файлов блокировки')
        paths_by_directory: dict[str, set[str]] = {}
        for filename in PACKAGE_FILES:
            if filename == PYPROJECT_FILENAME:
                continue
            for path in self._find_file_paths(project, filename, default_branch):
                directory = self._parent_directory(path)
                paths_by_directory.setdefault(directory, set()).add(path)

        return [
            {
                path: self._read_file(project, path, default_branch)
                for path in sorted(paths)
            }
            for _, paths in sorted(paths_by_directory.items())
        ]

    def _read_file_set(
        self,
        project: GitLabProject,
        pyproject_path: str,
        default_branch: str,
    ) -> dict[str, bytes]:
        directory = self._parent_directory(pyproject_path)
        logger.info('Чтение набора файлов подпроекта: %s', directory or '.')
        files = {pyproject_path: self._read_file(project, pyproject_path, default_branch)}
        for filename in PACKAGE_FILES:
            if filename == PYPROJECT_FILENAME:
                continue
            path = f'{directory}/{filename}' if directory else filename
            content = self._read_file_if_exists(project, path, default_branch)
            if content is not None:
                files[path] = content
        return files

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
        first_path = next(iter(files))
        path = PackageFilesService._parent_directory(first_path) or '.'
        pyproject_content = next(
            (
                content
                for file_path, content in files.items()
                if PurePosixPath(file_path).name == PYPROJECT_FILENAME
            ),
            None,
        )
        return ProjectSubproject(
            path=path,
            package_manager=detect_package_manager(
                pyproject_content,
                {PurePosixPath(file_path).name for file_path in files},
            ),
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
