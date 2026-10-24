import base64
import logging
from http import HTTPStatus
from pathlib import Path, PurePosixPath

from gitlab.exceptions import GitlabError
lazy from gitlab.v4.objects import Project as GitLabProject

from gitlab_radar.clients.gitlab import gitlab_client
from gitlab_radar.schemas.project import Project
from gitlab_radar.services.package_manager import SUBPROJECT_FILES

logger = logging.getLogger(__name__)

GITLAB_CI_FILENAMES = ('.gitlab-ci.yml', '.gitlab-ci.yaml')
TARGET_FILENAMES = frozenset((*SUBPROJECT_FILES, *GITLAB_CI_FILENAMES))
TARGET_SEARCH_QUERY = ' or '.join(f'file:{filename}' for filename in sorted(TARGET_FILENAMES))
BATCH_SIZE = 20
UNSUPPORTED_STATUSES = {
    HTTPStatus.BAD_REQUEST,
    HTTPStatus.FORBIDDEN,
    HTTPStatus.NOT_FOUND,
    HTTPStatus.METHOD_NOT_ALLOWED,
    HTTPStatus.UNPROCESSABLE_ENTITY,
}


class ProjectCollector:
    def __init__(self, projects_directory: Path) -> None:
        self._projects_directory = projects_directory
        self._exact_search_supported: bool | None = None
        self._batch_supported: bool | None = None

    def revision(self, project: Project) -> str:
        gitlab_project = self._gitlab_project(project)
        default_branch = self._default_branch(project)
        branch = gitlab_project.branches.get(default_branch)
        commit = branch.attributes.get('commit', {})
        revision = commit.get('id') if isinstance(commit, dict) else None
        if not isinstance(revision, str) or not revision:
            msg = f'GitLab не вернул revision основной ветки проекта {project.path_with_namespace}'
            raise ValueError(msg)
        logger.info('Определена ревизия проекта %s: %s', project.path_with_namespace, revision[:12])
        return revision

    def collect(self, project: Project, revision: str) -> dict[str, Path]:
        gitlab_project = self._gitlab_project(project)
        default_branch = self._default_branch(project)
        paths = self._find_target_paths(gitlab_project, default_branch)
        contents = self._read_files(gitlab_project, paths, default_branch)
        files = self._save_files(project, revision, contents)
        logger.info(
            'Файлы проекта %s собраны: найдено %d',
            project.path_with_namespace,
            len(files),
        )
        return files

    @staticmethod
    def _gitlab_project(project: Project) -> GitLabProject:
        ProjectCollector._default_branch(project)
        return gitlab_client.projects.get(project.id, lazy=True)

    @staticmethod
    def _default_branch(project: Project) -> str:
        if project.default_branch:
            return project.default_branch
        msg = f'Проект {project.path_with_namespace} не имеет основной ветки'
        raise ValueError(msg)

    def _find_target_paths(self, project: GitLabProject, default_branch: str) -> list[str]:
        if self._exact_search_supported is not False:
            try:
                paths = self._find_with_exact_search(project, default_branch)
            except GitlabError as error:
                if error.response_code not in UNSUPPORTED_STATUSES:
                    raise
                self._exact_search_supported = False
                logger.warning('Точный поиск GitLab недоступен; используется дерево репозитория')
            else:
                self._exact_search_supported = True
                logger.info('Точный поиск GitLab нашёл целевых файлов: %d', len(paths))
                return paths
        paths = self._find_in_repository_tree(project, default_branch)
        logger.info('В дереве репозитория найдено целевых файлов: %d', len(paths))
        return paths

    @staticmethod
    def _find_with_exact_search(project: GitLabProject, default_branch: str) -> list[str]:
        results = project.search(
            scope='blobs',
            search=TARGET_SEARCH_QUERY,
            search_type='zoekt',
            ref=default_branch,
            iterator=True,
            per_page=100,
        )
        paths: set[str] = set()
        for result in results:
            path = result.get('path')
            if isinstance(path, str) and PurePosixPath(path).name in TARGET_FILENAMES:
                paths.add(path)
        return sorted(paths, key=lambda value: (value.count('/'), value))

    @staticmethod
    def _find_in_repository_tree(project: GitLabProject, default_branch: str) -> list[str]:
        entries = project.repository_tree(
            ref=default_branch,
            recursive=True,
            iterator=True,
            per_page=100,
        )
        paths: set[str] = set()
        for entry in entries:
            path = entry.get('path')
            if (
                entry.get('type') == 'blob'
                and isinstance(path, str)
                and PurePosixPath(path).name in TARGET_FILENAMES
            ):
                paths.add(path)
        return sorted(paths, key=lambda value: (value.count('/'), value))

    def _read_files(
        self,
        project: GitLabProject,
        paths: list[str],
        default_branch: str,
    ) -> dict[str, bytes]:
        if not paths:
            return {}
        if self._batch_supported is not False:
            try:
                files = self._read_files_in_batches(project, paths, default_branch)
            except GitlabError as error:
                if error.response_code not in UNSUPPORTED_STATUSES:
                    raise
                self._batch_supported = False
                logger.warning('Пакетное получение файлов GitLab недоступно; файлы читаются отдельно')
            else:
                self._batch_supported = True
                return files
        return {path: self._read_file(project, path, default_branch) for path in paths}

    def _read_files_in_batches(
        self,
        project: GitLabProject,
        paths: list[str],
        default_branch: str,
    ) -> dict[str, bytes]:
        files: dict[str, bytes] = {}
        logger.info(
            'Пакетное получение содержимого: файлов %d, запросов %d',
            len(paths),
            (len(paths) + BATCH_SIZE - 1) // BATCH_SIZE,
        )
        for offset in range(0, len(paths), BATCH_SIZE):
            chunk = paths[offset : offset + BATCH_SIZE]
            response = gitlab_client.http_post(
                f'/projects/{project.id}/repository/blobs/batch',
                post_data={
                    'files': [{'path': path, 'ref': default_branch} for path in chunk],
                },
            )
            if not isinstance(response, list):
                msg = f'GitLab вернул неожиданный ответ пакетного чтения: {type(response).__name__}'
                raise TypeError(msg)
            returned: set[str] = set()
            for item in response:
                if not isinstance(item, dict) or not isinstance(item.get('path'), str):
                    continue
                path = item['path']
                returned.add(path)
                if item.get('truncated'):
                    files[path] = self._read_file(project, path, default_branch)
                    continue
                content = item.get('content')
                if not isinstance(content, str):
                    files[path] = self._read_file(project, path, default_branch)
                    continue
                files[path] = base64.b64decode(content, validate=True)
            for path in set(chunk) - returned:
                files[path] = self._read_file(project, path, default_branch)
        return files

    @staticmethod
    def _read_file(project: GitLabProject, file_path: str, default_branch: str) -> bytes:
        content = project.files.raw(file_path=file_path, ref=default_branch)
        if not isinstance(content, bytes):
            msg = f'GitLab вернул неожиданный тип содержимого файла: {type(content).__name__}'
            raise TypeError(msg)
        return content

    def _save_files(self, project: Project, revision: str, files: dict[str, bytes]) -> dict[str, Path]:
        project_directory = self._projects_directory / str(project.id) / revision
        destinations: dict[str, Path] = {}
        for file_path, content in files.items():
            relative_path = PurePosixPath(file_path)
            if relative_path.is_absolute() or '..' in relative_path.parts:
                msg = f'GitLab вернул небезопасный путь: {file_path}'
                raise ValueError(msg)
            destination = project_directory.joinpath(*relative_path.parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
            destinations[file_path] = destination
        return destinations
