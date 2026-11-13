import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime

lazy from asyncpg import Connection

from gitlab_radar.clients.gitlab import GitLabRequestCounter
from gitlab_radar.database.models import ScanRun
from gitlab_radar.database.repository import (
    carry_forward_missing_projects,
    clone_project,
    delete_project_files,
    delete_scan_files,
    find_reusable_project,
    invalidate_project_cache,
    latest_scan,
    project_files,
    recover_stale_scans,
    restore_previous_analysis,
    save_analysis,
    save_collected_project,
    set_project_scanned_at,
    sync_programming_languages,
    trim_old_scans,
)
from gitlab_radar.database.scan_lock import acquire_scan_lock, release_scan_lock
from gitlab_radar.database.webhook_privacy import webhook_masking_key
from gitlab_radar.schemas.project import LanguageAnalysisStatus, Project, ProjectAnalysisStatus, ProjectLanguage
from gitlab_radar.schemas.scan import ScanPhase, ScanState, ScanStatus
from gitlab_radar.schemas.technology import PackageManager
from gitlab_radar.services.analysis import analysis_fingerprint, language_code, select_project_files
from gitlab_radar.services.application_parameters import application_parameter_values
from gitlab_radar.services.project import fetch_projects
from gitlab_radar.services.project_analysis import analyze_project
from gitlab_radar.services.project_blacklist import blacklist_patterns
from gitlab_radar.services.project_collection import ProjectCollector, ProjectNotScannableError

logger = logging.getLogger(__name__)
LOCAL_ANALYSIS_CONCURRENCY = max(1, min(8, os.cpu_count() or 1))


@dataclass(frozen=True, slots=True)
class CollectedSnapshot:
    snapshot_id: int | None
    project: Project
    reused: bool
    collection_succeeded: bool


class ScanTask:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._update_lock = asyncio.Lock()
        self._task: asyncio.Task[None] | None = None
        self._database_lock: Connection | None = None
        self._status = ScanStatus()
        self._updated_project_ids: list[int] = []

    async def start(self) -> bool:
        async with self._lock:
            if self._task is not None and not self._task.done():
                logger.warning('Запуск отклонен: сканирование уже выполняется')
                return False
            database_lock = await acquire_scan_lock()
            if database_lock is None:
                logger.warning('Запуск отклонен: сканирование выполняется другой репликой')
                return False
            try:
                await recover_stale_scans()
                started_at = datetime.now(UTC)
                scan = await ScanRun.create(
                    state=ScanState.RUNNING,
                    phase=ScanPhase.COLLECTING,
                    started_at=started_at,
                )
            except Exception:
                await release_scan_lock(database_lock)
                raise
            self._database_lock = database_lock
            self._updated_project_ids = []
            self._status = ScanStatus(
                id=scan.id,
                state=ScanState.RUNNING,
                phase=ScanPhase.COLLECTING,
                started_at=started_at,
            )
            self._task = asyncio.create_task(self._run(scan), name='gitlab-radar-scan')
        logger.info('Сканирование поставлено на выполнение: запуск %d', scan.id)
        return True

    async def status(self) -> ScanStatus:
        async with self._lock:
            if self._task is not None and not self._task.done():
                return self._status.model_copy(deep=True)
        scan = await latest_scan()
        if scan is None:
            return ScanStatus()
        status = _scan_status(scan)
        if self._status.id == scan.id:
            status.updated_project_ids = list(self._updated_project_ids)
        return status

    async def stop(self) -> None:
        async with self._lock:
            task = self._task
        if task is None or task.done():
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            completed_at = datetime.now(UTC)
            if self._status.id is not None:
                await delete_scan_files(self._status.id)
                await ScanRun.filter(id=self._status.id).update(
                    state=ScanState.FAILED,
                    completed_at=completed_at,
                    error='Сканирование остановлено вместе с приложением',
                )
            async with self._lock:
                self._status = self._status.model_copy(
                    update={
                        'state': ScanState.FAILED,
                        'completed_at': completed_at,
                        'error': 'Сканирование остановлено вместе с приложением',
                    },
                )
            logger.info('Сканирование остановлено вместе с приложением')

    async def _run(self, scan: ScanRun) -> None:
        logger.info('Сканирование проектов запущено: запуск %d', scan.id)
        errors: list[str] = []
        with GitLabRequestCounter() as request_counter:
            try:
                projects, skipped_without_branch = await self._fetch_projects(scan, request_counter)
                total_steps = len(projects) * 2 + 1
                await self._update(
                    scan,
                    projects_count=len(projects),
                    total_steps=total_steps,
                    skipped_projects=skipped_without_branch,
                    gitlab_requests=request_counter.count,
                )
                await self._scan_projects(scan, projects, errors, request_counter)
                await self._publish(scan, len(projects), total_steps, errors, request_counter.count)
            except Exception as error:
                logger.exception('Сканирование проектов завершилось из-за ошибки')
                await self._fail(scan, errors, error, request_counter.count)
            finally:
                database_lock = self._database_lock
                self._database_lock = None
                if database_lock is not None:
                    await release_scan_lock(database_lock)

    async def _fetch_projects(
        self,
        scan: ScanRun,
        request_counter: GitLabRequestCounter,
    ) -> tuple[list[Project], int]:
        blacklist = tuple(await blacklist_patterns())
        fetch_task = asyncio.create_task(asyncio.to_thread(fetch_projects, blacklist))
        try:
            while True:
                done, _ = await asyncio.wait({fetch_task}, timeout=1)
                if fetch_task in done:
                    return fetch_task.result()
                if request_counter.count != scan.gitlab_requests:
                    await self._update(scan, gitlab_requests=request_counter.count)
        finally:
            if not fetch_task.done():
                fetch_task.cancel()

    async def _scan_projects(
        self,
        scan: ScanRun,
        projects: list[Project],
        errors: list[str],
        request_counter: GitLabRequestCounter,
    ) -> None:
        collector = ProjectCollector(masking_key=await webhook_masking_key())
        analysis_queue: asyncio.Queue[CollectedSnapshot | None] = asyncio.Queue()
        workers = [
            asyncio.create_task(
                self._analysis_worker(scan, analysis_queue, errors),
                name=f'gitlab-radar-analysis-{number}',
            )
            for number in range(LOCAL_ANALYSIS_CONCURRENCY)
        ]
        try:
            for number, project in enumerate(projects, start=1):
                await self._update(scan, current_project=project.path_with_namespace)
                logger.info('Сбор файлов проекта %d/%d: %s', number, len(projects), project.path_with_namespace)
                collected = await self._collect_project(scan, collector, project, errors)
                await analysis_queue.put(collected)
                await self._record_collected(scan, errors, request_counter.count)

            await self._update(scan, phase=ScanPhase.ANALYZING, current_project=None)
            logger.info('Сбор файлов завершен; ожидается завершение локального анализа')
            for _ in workers:
                await analysis_queue.put(None)
            await asyncio.gather(*workers)
        finally:
            for worker in workers:
                if not worker.done():
                    worker.cancel()
            await asyncio.gather(*workers, return_exceptions=True)

    @staticmethod
    async def _collect_project(
        scan: ScanRun,
        collector: ProjectCollector,
        project: Project,
        errors: list[str],
    ) -> CollectedSnapshot:
        fingerprint = analysis_fingerprint()
        try:
            revision = await asyncio.to_thread(collector.revision, project)
            project.revision = revision
            language_statistics = await asyncio.to_thread(collector.languages, project)
            project.languages = [
                ProjectLanguage(
                    code=language_code(name),
                    name=name,
                    percentage=percentage,
                )
                for name, percentage in sorted(language_statistics.items())
            ]
            project.is_empty = not project.languages
            language_rows = await sync_programming_languages(project.languages)
            for language in project.languages:
                if not language_rows[language.code].enabled:
                    language.analysis_status = LanguageAnalysisStatus.DISABLED
            try:
                await asyncio.to_thread(collector.collect_hooks, project)
            except Exception as error:
                errors.append(f'{project.path_with_namespace}: не удалось получить webhooks: {error}')
                logger.exception('Не удалось получить webhooks проекта %s', project.path_with_namespace)
            enabled_language_codes = [
                language.code
                for language in project.languages
                if language.analysis_status != LanguageAnalysisStatus.DISABLED
            ]
            fingerprint = analysis_fingerprint(enabled_language_codes)
            reusable = await find_reusable_project(project.id, revision, fingerprint)
            if reusable is not None:
                snapshot = await clone_project(reusable, scan, project, fingerprint)
                logger.info('Проект %s не изменился; используется прежний анализ', project.path_with_namespace)
                return CollectedSnapshot(snapshot.id, project, True, True)
            repository_paths = await asyncio.to_thread(collector.repository_files, project, revision)
            selections = select_project_files(repository_paths, enabled_language_codes)
            selected_paths = sorted({selection.path for selection in selections})
            logger.info(
                'Для проекта %s выбрано файлов для скачивания: %d',
                project.path_with_namespace,
                len(selected_paths),
            )
            files = await asyncio.to_thread(collector.collect, project, revision, selected_paths)
            snapshot = await save_collected_project(
                scan,
                project,
                revision,
                files,
                selections,
                fingerprint,
            )
            return CollectedSnapshot(snapshot.id, project, False, True)
        except ProjectNotScannableError as error:
            logger.info('Проект %s пропущен: %s', project.path_with_namespace, error)
            return CollectedSnapshot(None, project, False, False)
        except Exception as error:
            errors.append(f'{project.path_with_namespace}: {error}')
            project.analysis_status = ProjectAnalysisStatus.FAILED
            project.scan_error = f'Ошибка сбора ({type(error).__name__})'
            project.package_manager = PackageManager.UNKNOWN
            snapshot = await save_collected_project(
                scan,
                project,
                project.revision,
                {},
                [],
                fingerprint,
                str(error),
            )
            await restore_previous_analysis(snapshot.id, project, str(error))
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
                scanned_at = datetime.now(UTC)
                item.project.scanned_at = scanned_at
                await set_project_scanned_at(item.snapshot_id, scanned_at)
            invalidate_project_cache()
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

    @staticmethod
    async def _analyze_snapshot(item: CollectedSnapshot) -> str | None:
        project = item.project
        if item.snapshot_id is None:
            return None
        try:
            files = await project_files(item.snapshot_id)
            project = await asyncio.to_thread(analyze_project, project, files, project.revision)
            restored = False
            if project.analysis_status == ProjectAnalysisStatus.FAILED and project.scan_error:
                restored = await restore_previous_analysis(item.snapshot_id, project, project.scan_error)
            if not restored:
                await save_analysis(item.snapshot_id, project, project.scan_error)
            if project.scan_error:
                return f'{project.path_with_namespace}: {project.scan_error}'
        except Exception as error:
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
        blacklist = tuple(await blacklist_patterns())
        await carry_forward_missing_projects(scan, blacklist)
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
        invalidate_project_cache()
        try:
            parameter_values = await application_parameter_values()
            await trim_old_scans(int(parameter_values['retained_scan_count']))
        except Exception:
            logger.exception('Не удалось удалить старые снимки сканирования')
        logger.info(
            'Сканирование завершено: проектов %d, обращений к GitLab %d, ошибок %d, длительность %.2f секунды',
            projects_count,
            gitlab_requests,
            len(errors),
            (completed_at - scan.started_at).total_seconds(),
        )

    async def _fail(
        self,
        scan: ScanRun,
        errors: list[str],
        error: Exception,
        gitlab_requests: int,
    ) -> None:
        await delete_scan_files(scan.id)
        await self._update(
            scan,
            state=ScanState.FAILED,
            completed_at=datetime.now(UTC),
            error=str(error),
            current_project=None,
            errors=errors,
            gitlab_requests=gitlab_requests,
        )
        invalidate_project_cache()

    async def _update(self, scan: ScanRun, **values: object) -> None:
        async with self._update_lock:
            await self._save_update(scan, **values)

    async def _save_update(self, scan: ScanRun, **values: object) -> None:
        database_values = {key: value for key, value in values.items() if key != 'updated_project_ids'}
        for key, value in database_values.items():
            setattr(scan, key, value)
        if database_values:
            await scan.save(update_fields=list(database_values))
        async with self._lock:
            status_values = {
                key: value for key, value in values.items() if ScanStatus.model_fields.get(key) is not None
            }
            status_values.setdefault('projects_count', scan.projects_count)
            self._status = self._status.model_copy(update=status_values)


def _scan_status(scan: ScanRun) -> ScanStatus:
    return ScanStatus(
        id=scan.id,
        state=ScanState(scan.state),
        phase=ScanPhase(scan.phase),
        started_at=scan.started_at,
        completed_at=scan.completed_at,
        projects_count=scan.projects_count,
        total_steps=scan.total_steps,
        completed_steps=scan.completed_steps,
        collected_projects=scan.collected_projects,
        analyzed_projects=scan.analyzed_projects,
        reused_projects=scan.reused_projects,
        skipped_projects=scan.skipped_projects,
        gitlab_requests=scan.gitlab_requests,
        current_project=scan.current_project,
        error=scan.error,
        errors=scan.errors,
    )


scan_task = ScanTask()
