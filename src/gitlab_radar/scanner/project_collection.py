import base64
import logging
from http import HTTPStatus
from pathlib import PurePosixPath

from gitlab.const import AccessLevel
from gitlab.exceptions import GitlabError, GitlabGetError
lazy from gitlab.v4.objects import Project as GitLabProject

from gitlab_radar.clients.gitlab import ScanGitLab
from gitlab_radar.schemas.project import Project, ProjectHook
from gitlab_radar.services.webhook_privacy import public_webhook_identity, public_webhook_url

logger = logging.getLogger(__name__)
BATCH_SIZE = 20
UNSUPPORTED_STATUSES = {
    HTTPStatus.BAD_REQUEST,
    HTTPStatus.FORBIDDEN,
    HTTPStatus.NOT_FOUND,
    HTTPStatus.METHOD_NOT_ALLOWED,
    HTTPStatus.UNPROCESSABLE_ENTITY,
}
HOOK_EVENT_FIELDS = (
    'push_events',
    'tag_push_events',
    'issues_events',
    'confidential_issues_events',
    'merge_requests_events',
    'note_events',
    'confidential_note_events',
    'job_events',
    'pipeline_events',
    'wiki_page_events',
    'deployment_events',
    'releases_events',
    'milestone_events',
    'feature_flag_events',
    'resource_access_token_events',
    'resource_deploy_token_events',
)


class ProjectNotScannableError(Exception):
    pass


class ProjectCollector:
    def __init__(self, client: ScanGitLab, *, masking_key: bytes) -> None:
        self._client = client
        self._masking_key = masking_key
        self._batch_supported: bool | None = None

    def revision(self, project: Project) -> str:
        gitlab_project = self._gitlab_project(project)
        default_branch = self._default_branch(project)
        try:
            branch = gitlab_project.branches.get(default_branch)
        except GitlabGetError as error:
            if error.response_code != HTTPStatus.NOT_FOUND:
                raise
            msg = (
                f'Основная ветка {default_branch} проекта '
                f'{project.path_with_namespace} была удалена до начала сканирования'
            )
            raise ProjectNotScannableError(msg) from error
        commit = branch.attributes.get('commit', {})
        revision = commit.get('id') if isinstance(commit, dict) else None
        if not isinstance(revision, str) or not revision:
            msg = f'GitLab не вернул revision основной ветки проекта {project.path_with_namespace}'
            raise ValueError(msg)
        logger.info('Определена ревизия проекта %s: %s', project.path_with_namespace, revision[:12])
        return revision

    def languages(self, project: Project) -> dict[str, float]:
        values = self._gitlab_project(project).languages()
        if not isinstance(values, dict):
            msg = f'GitLab вернул неожиданный список языков: {type(values).__name__}'
            raise TypeError(msg)
        languages = {
            name: float(percentage)
            for name, percentage in values.items()
            if isinstance(name, str) and isinstance(percentage, int | float)
        }
        logger.info(
            'Языки проекта %s получены: %d',
            project.path_with_namespace,
            len(languages),
        )
        return languages

    def repository_files(self, project: Project, revision: str) -> list[str]:
        entries = self._gitlab_project(project).repository_tree(
            ref=revision,
            recursive=True,
            iterator=True,
            per_page=100,
        )
        paths = set()
        for entry in entries:
            self._client.signal.check()
            if entry.get('type') == 'blob' and isinstance((path := entry.get('path')), str):
                paths.add(path)
        result = sorted(paths, key=lambda value: (value.count('/'), value))
        logger.info(
            'Структура проекта %s получена: файлов %d',
            project.path_with_namespace,
            len(result),
        )
        return result

    def collect(self, project: Project, revision: str, paths: list[str]) -> dict[str, str]:
        gitlab_project = self._gitlab_project(project)
        contents = self._read_files(gitlab_project, paths, revision)
        files = self._text_files(contents)
        logger.info(
            'Файлы проекта %s собраны: найдено %d',
            project.path_with_namespace,
            len(files),
        )
        return files

    def collect_hooks(self, project: Project) -> None:
        if project.gitlab_access_level < AccessLevel.MAINTAINER:
            return
        hooks = self._gitlab_project(project).hooks.list(iterator=True, per_page=100)
        project.webhooks = [self._project_hook(hook.asdict()) for hook in hooks]
        project.webhooks_accessible = True
        logger.info(
            'Webhook проекта %s собраны: %d',
            project.path_with_namespace,
            len(project.webhooks),
        )

    def _project_hook(self, attributes: dict) -> ProjectHook:
        url = str(attributes.get('url') or '')
        return ProjectHook(
            id=int(attributes['id']),
            url=public_webhook_url(url, self._masking_key),
            identity=public_webhook_identity(url, self._masking_key),
            name=attributes.get('name'),
            description=attributes.get('description'),
            events=[field.removesuffix('_events') for field in HOOK_EVENT_FIELDS if attributes.get(field)],
            enable_ssl_verification=bool(attributes.get('enable_ssl_verification', True)),
            alert_status=attributes.get('alert_status'),
        )

    def _gitlab_project(self, project: Project) -> GitLabProject:
        ProjectCollector._default_branch(project)
        return self._client.projects.get(project.id, lazy=True)

    @staticmethod
    def _default_branch(project: Project) -> str:
        if project.default_branch:
            return project.default_branch
        msg = f'Проект {project.path_with_namespace} не имеет основной ветки'
        raise ValueError(msg)

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
            self._client.signal.check()
            chunk = paths[offset : offset + BATCH_SIZE]
            response = self._client.http_post(
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

    def _read_file(self, project: GitLabProject, file_path: str, default_branch: str) -> bytes:
        self._client.signal.check()
        content = project.files.raw(file_path=file_path, ref=default_branch)
        if not isinstance(content, bytes):
            msg = f'GitLab вернул неожиданный тип содержимого файла: {type(content).__name__}'
            raise TypeError(msg)
        return content

    @staticmethod
    def _text_files(files: dict[str, bytes]) -> dict[str, str]:
        contents: dict[str, str] = {}
        for file_path, content in files.items():
            relative_path = PurePosixPath(file_path)
            if relative_path.is_absolute() or '..' in relative_path.parts:
                msg = f'GitLab вернул небезопасный путь: {file_path}'
                raise ValueError(msg)
            try:
                contents[file_path] = content.decode('utf-8')
            except UnicodeDecodeError:
                contents[file_path] = (
                    '[gitlab-radar:unsupported-encoding]'
                )
                logger.warning('Файл имеет неподдерживаемую кодировку: %s', file_path)
        return contents
