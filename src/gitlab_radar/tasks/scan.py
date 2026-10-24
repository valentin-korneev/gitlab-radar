import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from gitlab_radar.config import settings
from gitlab_radar.database.models import ScanRun
from gitlab_radar.database.repository import (
    clone_project,
    find_reusable_project,
    invalidate_project_cache,
    latest_scan,
    project_files,
    save_analysis,
    save_collected_project,
    trim_old_scans,
)
from gitlab_radar.schemas.project import Project
from gitlab_radar.schemas.scan import ScanPhase, ScanState, ScanStatus
from gitlab_radar.schemas.technology import PackageManager
from gitlab_radar.services.project import fetch_projects
from gitlab_radar.services.project_analysis import analyze_project
from gitlab_radar.services.project_collection import ProjectCollector

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CollectedSnapshot:
    snapshot_id: int
    project: Project
    reused: bool
    collection_succeeded: bool


class ScanTask:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._task: asyncio.Task[None] | None = None
        self._status = ScanStatus()

    async def start(self) -> bool:
        async with self._lock:
            if self._task is not None and not self._task.done():
                logger.warning('Запуск отклонён: сканирование уже выполняется')
                return False
            started_at = datetime.now(UTC)
            scan = await ScanRun.create(
                state=ScanState.RUNNING,
                phase=ScanPhase.COLLECTING,
                started_at=started_at,
            )
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
        return _scan_status(scan) if scan is not None else ScanStatus()

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
        try:
            projects, skipped_without_branch = await asyncio.to_thread(fetch_projects)
            total_steps = len(projects) * 2 + 1
            await self._update(
                scan,
                projects_count=len(projects),
                total_steps=total_steps,
                skipped_projects=skipped_without_branch,
            )
            collected = await self._collect_projects(scan, projects, errors)
            await self._analyze_projects(scan, collected, errors)
            await self._publish(scan, len(projects), total_steps, errors)
        except Exception as error:
            logger.exception('Сканирование проектов завершилось из-за ошибки')
            await self._fail(scan, errors, error)

    async def _collect_projects(
        self,
        scan: ScanRun,
        projects: list[Project],
        errors: list[str],
    ) -> list[CollectedSnapshot]:
        collector = ProjectCollector(settings.application.projects_dir)
        collected: list[CollectedSnapshot] = []
        for number, project in enumerate(projects, start=1):
            await self._update(scan, current_project=project.path_with_namespace)
            logger.info('Сбор файлов проекта %d/%d: %s', number, len(projects), project.path_with_namespace)
            collected.append(await self._collect_project(scan, collector, project, errors))
            await self._update(
                scan,
                collected_projects=number,
                completed_steps=number,
                errors=errors,
            )
        return collected

    @staticmethod
    async def _collect_project(
        scan: ScanRun,
        collector: ProjectCollector,
        project: Project,
        errors: list[str],
    ) -> CollectedSnapshot:
        try:
            revision = await asyncio.to_thread(collector.revision, project)
            project.revision = revision
            reusable = await find_reusable_project(project.id, revision)
            if reusable is not None:
                snapshot = await clone_project(reusable, scan, project)
                logger.info('Проект %s не изменился; используется прежний анализ', project.path_with_namespace)
                return CollectedSnapshot(snapshot.id, project, True, True)
            files = await asyncio.to_thread(collector.collect, project, revision)
            snapshot = await save_collected_project(scan, project, revision, files)
            return CollectedSnapshot(snapshot.id, project, False, True)
        except Exception as error:
            errors.append(f'{project.path_with_namespace}: {error}')
            project.scan_error = str(error)
            project.package_manager = PackageManager.UNKNOWN
            snapshot = await save_collected_project(scan, project, project.revision, {}, str(error))
            logger.exception('Не удалось собрать файлы проекта %s', project.path_with_namespace)
            return CollectedSnapshot(snapshot.id, project, False, False)

    async def _analyze_projects(
        self,
        scan: ScanRun,
        collected: list[CollectedSnapshot],
        errors: list[str],
    ) -> None:
        await self._update(scan, phase=ScanPhase.ANALYZING, current_project=None)
        logger.info('Сбор файлов завершён; начинается локальный анализ проектов')
        total = len(collected)
        for number, item in enumerate(collected, start=1):
            await self._update(scan, current_project=item.project.path_with_namespace)
            logger.info('Анализ проекта %d/%d: %s', number, total, item.project.path_with_namespace)
            values: dict[str, object] = {}
            if item.reused:
                values['reused_projects'] = scan.reused_projects + 1
            elif not item.collection_succeeded:
                values['skipped_projects'] = scan.skipped_projects + 1
            else:
                await self._analyze_snapshot(item, errors)
            await self._update(
                scan,
                analyzed_projects=number,
                completed_steps=total + number,
                errors=errors,
                **values,
            )

    @staticmethod
    async def _analyze_snapshot(item: CollectedSnapshot, errors: list[str]) -> None:
        project = item.project
        try:
            files = await project_files(item.snapshot_id)
            project = await asyncio.to_thread(analyze_project, project, files, project.revision)
            await save_analysis(item.snapshot_id, project)
        except Exception as error:
            errors.append(f'{project.path_with_namespace}: {error}')
            project.scan_error = str(error)
            project.package_manager = PackageManager.UNKNOWN
            await save_analysis(item.snapshot_id, project, str(error))
            logger.exception('Не удалось проанализировать проект %s', project.path_with_namespace)

    async def _publish(
        self,
        scan: ScanRun,
        projects_count: int,
        total_steps: int,
        errors: list[str],
    ) -> None:
        await self._update(scan, phase=ScanPhase.PUBLISHING, current_project=None)
        logger.info('Локальный анализ завершён; результаты публикуются')
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
        )
        invalidate_project_cache()
        await trim_old_scans()
        logger.info(
            'Сканирование завершено: проектов %d, ошибок %d, длительность %.2f секунды',
            projects_count,
            len(errors),
            (completed_at - scan.started_at).total_seconds(),
        )

    async def _fail(self, scan: ScanRun, errors: list[str], error: Exception) -> None:
        await self._update(
            scan,
            state=ScanState.FAILED,
            completed_at=datetime.now(UTC),
            error=str(error),
            current_project=None,
            errors=errors,
        )

    async def _update(self, scan: ScanRun, **values: object) -> None:
        database_values = dict(values)
        for key, value in database_values.items():
            setattr(scan, key, value)
        await scan.save(update_fields=list(database_values))
        async with self._lock:
            status_values = {
                key: value
                for key, value in values.items()
                if key in ScanStatus.model_fields
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
        current_project=scan.current_project,
        error=scan.error,
        errors=scan.errors,
    )


scan_task = ScanTask()
