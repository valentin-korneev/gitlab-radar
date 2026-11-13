import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime

from asyncpg import PostgresError
from gitlab.exceptions import GitlabError
from tortoise.exceptions import BaseORMException
from tortoise.transactions import in_transaction

from gitlab_radar.clients.gitlab import ScanGitLab
from gitlab_radar.database.languages import sync_programming_languages
from gitlab_radar.database.models import ScanRun
from gitlab_radar.database.scan_authority import assert_scan_owner
from gitlab_radar.database.scan_jobs import update_progress
from gitlab_radar.database.scan_repository import (
    carry_forward_missing_projects,
    clone_project,
    delete_project_files,
    find_reusable_inputs,
    find_reusable_project,
    prepare_scan,
    project_files,
    restore_previous_analysis,
    save_analysis,
    save_collected_project,
    skip_project,
)
from gitlab_radar.database.webhook_privacy import webhook_masking_key
from gitlab_radar.domain.scanning import StopSignal
from gitlab_radar.scanner.collection import fetch_projects
from gitlab_radar.scanner.control import thread_call
from gitlab_radar.scanner.project_collection import ProjectCollector, ProjectNotScannableError
from gitlab_radar.schemas.project import LanguageAnalysisStatus, Project, ProjectAnalysisStatus, ProjectLanguage
from gitlab_radar.schemas.scan import ScanPhase, ScanState
from gitlab_radar.schemas.scan_options import ScanOptions
from gitlab_radar.schemas.technology import PackageManager
from gitlab_radar.services.analysis import analysis_fingerprint, language_code, select_project_files
from gitlab_radar.services.analysis.diagnostics import PARSE_ERRORS
from gitlab_radar.services.project_analysis import analyze_project
from gitlab_radar.services.project_blacklist import blacklist_patterns

logger = logging.getLogger(__name__)
SCAN_ERRORS = (*PARSE_ERRORS, GitlabError, BaseORMException, PostgresError, OSError, RuntimeError)
LOCAL_ANALYSIS_CONCURRENCY = max(1, min(8, os.cpu_count() or 1))


@dataclass(frozen=True, slots=True)
class CollectedSnapshot:
    snapshot_id: int | None
    project: Project
    reused: bool
    collection_succeeded: bool


class ScanPipeline:
    def __init__(self, client: ScanGitLab, signal: StopSignal) -> None:
        self.client = client
        self.signal = signal
        self._update_lock = asyncio.Lock()
        self._updated_project_ids: list[int] = []
        self.errors: list[str] = []
        self.options = ScanOptions()

    async def run(self, scan: ScanRun) -> None:
        self.options = ScanOptions.model_validate(scan.options)
        projects, skipped = await self._fetch_projects(scan)
        total_steps = len(projects) * 2 + 1
        await self._update(
            scan,
            projects_count=len(projects),
            total_steps=total_steps,
            skipped_projects=skipped,
            gitlab_requests=self.client.request_count,
        )
        await self._scan_projects(scan, projects, self.errors)
        await self._publish(scan, len(projects), total_steps, self.errors, self.client.request_count)

    async def _fetch_projects(self, scan: ScanRun) -> tuple[list[Project], int]:
        blacklist = tuple(await blacklist_patterns())
        operation = asyncio.create_task(
            thread_call(
                self.signal,
                fetch_projects,
                self.client,
                blacklist,
                self.options.project_ids,
            )
        )
        try:
            while True:
                done, _ = await asyncio.wait({operation}, timeout=1)
                if operation in done:
                    return operation.result()
                if self.client.request_count != scan.gitlab_requests:
                    await self._update(scan, gitlab_requests=self.client.request_count)
        finally:
            if not operation.done():
                self.signal.stop('Получение проектов прервано')
            await asyncio.gather(operation, return_exceptions=True)

    async def _scan_projects(
        self,
        scan: ScanRun,
        projects: list[Project],
        errors: list[str],
    ) -> None:
        await prepare_scan(scan, projects)
        collector = ProjectCollector(self.client, masking_key=await webhook_masking_key())
        analysis_queue: asyncio.Queue[CollectedSnapshot | None] = asyncio.Queue(maxsize=LOCAL_ANALYSIS_CONCURRENCY * 2)
        async with asyncio.TaskGroup() as group:
            workers = [
                group.create_task(
                    self._analysis_worker(scan, analysis_queue, errors), name=f'gitlab-radar-analysis-{number}'
                )
                for number in range(LOCAL_ANALYSIS_CONCURRENCY)
            ]
            for number, project in enumerate(projects, start=1):
                self.signal.check()
                await self._update(scan, current_project=project.path_with_namespace)
                logger.info('Сбор файлов проекта %d/%d: %s', number, len(projects), project.path_with_namespace)
                collected = await self._collect_project(scan, collector, project, errors)
                await analysis_queue.put(collected)
                await self._record_collected(scan, errors, self.client.request_count)

            await self._update(scan, phase=ScanPhase.ANALYZING, current_project=None)
            logger.info('Сбор файлов завершен; ожидается завершение локального анализа')
            for _ in workers:
                await analysis_queue.put(None)

    async def _collect_project(
        self,
        scan: ScanRun,
        collector: ProjectCollector,
        project: Project,
        errors: list[str],
    ) -> CollectedSnapshot:
        fingerprint = analysis_fingerprint()
        try:
            revision = await thread_call(self.signal, collector.revision, project)
            project.revision = revision
            enabled_language_codes = await _collect_languages(collector, project, self.signal)
            try:
                await thread_call(self.signal, collector.collect_hooks, project)
            except SCAN_ERRORS as error:
                errors.append(f'{project.path_with_namespace}: не удалось получить webhooks: {error}')
                logger.exception('Не удалось получить webhooks проекта %s', project.path_with_namespace)
            fingerprint = analysis_fingerprint(enabled_language_codes)
            reusable = (
                None if self.options.force_analysis else await find_reusable_project(project.id, revision, fingerprint)
            )
            if reusable is not None:
                snapshot = await clone_project(reusable, scan, project, fingerprint)
                logger.info('Проект %s не изменился; используется прежний анализ', project.path_with_namespace)
                return CollectedSnapshot(snapshot.id, project, True, True)
            repository_paths = await thread_call(self.signal, collector.repository_files, project, revision)
            selections = select_project_files(repository_paths, enabled_language_codes)
            selected_paths = sorted({selection.path for selection in selections})
            logger.info(
                'Для проекта %s выбрано файлов для скачивания: %d',
                project.path_with_namespace,
                len(selected_paths),
            )
            files = await thread_call(self.signal, collector.collect, project, revision, selected_paths)
            reusable = (
                None if self.options.force_analysis else await find_reusable_inputs(project.id, files, fingerprint)
            )
            if reusable is not None:
                snapshot = await clone_project(reusable, scan, project, fingerprint)
                return CollectedSnapshot(snapshot.id, project, True, True)
            snapshot = await save_collected_project(
                scan,
                project,
                files=files,
                selections=selections,
                fingerprint=fingerprint,
            )
            return CollectedSnapshot(snapshot.id, project, False, True)
        except ProjectNotScannableError as error:
            await skip_project(scan, project, str(error))
            logger.info('Проект %s пропущен: %s', project.path_with_namespace, error)
            return CollectedSnapshot(None, project, False, False)
        except SCAN_ERRORS as error:
            errors.append(f'{project.path_with_namespace}: {error}')
            project.analysis_status = ProjectAnalysisStatus.FAILED
            project.scan_error = f'Ошибка сбора ({type(error).__name__})'
            project.package_manager = PackageManager.UNKNOWN
            snapshot = await save_collected_project(
                scan,
                project,
                files={},
                selections=[],
                fingerprint=fingerprint,
            )
            await restore_previous_analysis(snapshot.id, project, project.scan_error)
            logger.exception('Не удалось собрать файлы проекта %s', project.path_with_namespace)
            return CollectedSnapshot(snapshot.id, project, False, False)

    async def _analysis_worker(
        self,
        scan: ScanRun,
        analysis_queue: asyncio.Queue[CollectedSnapshot | None],
        errors: list[str],
    ) -> None:
        while True:
            item = await analysis_queue.get()
            if item is None:
                return
            self.signal.check()
            if item.reused:
                result = 'reused'
                error = None
            elif not item.collection_succeeded:
                result = 'skipped'
                error = None
            else:
                logger.info('Локальный анализ проекта: %s', item.project.path_with_namespace)
                error = await self._analyze_snapshot(item)
                result = 'analyzed'
            if error is not None:
                errors.append(error)
            await self._record_analyzed(scan, result, errors, item)

    async def _record_collected(self, scan: ScanRun, errors: list[str], gitlab_requests: int) -> None:
        async with self._update_lock:
            collected_projects = scan.collected_projects + 1
            await self._save_update(
                scan,
                collected_projects=collected_projects,
                completed_steps=collected_projects + scan.analyzed_projects,
                errors=list(errors),
                gitlab_requests=gitlab_requests,
            )

    async def _record_analyzed(
        self,
        scan: ScanRun,
        result: str,
        errors: list[str],
        item: CollectedSnapshot,
    ) -> None:
        async with self._update_lock:
            analyzed_projects = scan.analyzed_projects + 1
            values: dict[str, object] = {}
            if result == 'reused':
                values['reused_projects'] = scan.reused_projects + 1
            elif result == 'skipped':
                values['skipped_projects'] = scan.skipped_projects + 1
            if item.snapshot_id is not None:
                self._updated_project_ids.append(item.project.id)
            await self._save_update(
                scan,
                analyzed_projects=analyzed_projects,
                completed_steps=scan.collected_projects + analyzed_projects,
                updated_project_ids=list(self._updated_project_ids),
                errors=list(errors),
                **values,
            )

    async def _analyze_snapshot(self, item: CollectedSnapshot) -> str | None:
        project = item.project
        if item.snapshot_id is None:
            return None
        try:
            files = await project_files(item.snapshot_id)
            project = await thread_call(self.signal, analyze_project, project, files, project.revision)
            restored = False
            if project.analysis_status == ProjectAnalysisStatus.FAILED and project.scan_error:
                restored = await restore_previous_analysis(item.snapshot_id, project, project.scan_error)
            if not restored:
                await save_analysis(item.snapshot_id, project, project.scan_error)
            if project.scan_error:
                return f'{project.path_with_namespace}: {project.scan_error}'
        except SCAN_ERRORS as error:
            project.analysis_status = ProjectAnalysisStatus.FAILED
            project.scan_error = f'Ошибка анализа ({type(error).__name__})'
            project.package_manager = PackageManager.UNKNOWN
            restored = await restore_previous_analysis(item.snapshot_id, project, project.scan_error)
            if not restored:
                await save_analysis(item.snapshot_id, project, project.scan_error)
            logger.exception('Не удалось проанализировать проект %s', project.path_with_namespace)
            return f'{project.path_with_namespace}: {project.scan_error}'
        finally:
            await delete_project_files(item.snapshot_id)
        return None

    async def _publish(
        self,
        scan: ScanRun,
        projects_count: int,
        total_steps: int,
        errors: list[str],
        gitlab_requests: int,
    ) -> None:
        await self._update(scan, phase=ScanPhase.PUBLISHING, current_project=None)
        logger.info('Локальный анализ завершен; результаты публикуются')
        async with in_transaction() as connection:
            await assert_scan_owner(scan.id, connection)
            blacklist = tuple(await blacklist_patterns())
            await carry_forward_missing_projects(scan, blacklist, self.options.project_ids)
            completed_at = datetime.now(UTC)
            await self._update(
                scan,
                state=ScanState.COMPLETED,
                phase=ScanPhase.COMPLETED,
                completed_at=completed_at,
                completed_steps=total_steps,
                current_project=None,
                errors=errors,
                published=True,
                gitlab_requests=gitlab_requests,
            )
        logger.info(
            'Сканирование завершено: проектов %d, обращений к GitLab %d, ошибок %d, длительность %.2f секунды',
            projects_count,
            gitlab_requests,
            len(errors),
            (completed_at - scan.started_at).total_seconds(),
        )

    async def _update(self, scan: ScanRun, **values: object) -> None:
        async with self._update_lock:
            await self._save_update(scan, **values)

    async def _save_update(self, scan: ScanRun, **values: object) -> None:
        await update_progress(scan, values)


async def _collect_languages(collector: ProjectCollector, project: Project, signal: StopSignal) -> list[str]:
    statistics = await thread_call(signal, collector.languages, project)
    project.languages = [
        ProjectLanguage(code=language_code(name), name=name, percentage=percentage)
        for name, percentage in sorted(statistics.items())
    ]
    project.is_empty = not project.languages
    rows = await sync_programming_languages(project.languages)
    for language in project.languages:
        if not rows[language.code].enabled:
            language.analysis_status = LanguageAnalysisStatus.DISABLED
    return [
        language.code for language in project.languages if language.analysis_status != LanguageAnalysisStatus.DISABLED
    ]
