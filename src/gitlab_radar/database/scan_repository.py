from datetime import UTC, datetime

from tortoise.transactions import in_transaction
lazy from tortoise.backends.base.client import BaseDBAsyncClient

from gitlab_radar.database.models import AnalysisResult, ScanFile, ScanFileUsage, ScanItem, ScanRun, ScanTarget
from gitlab_radar.database.result_payload import input_digest, project_metadata, result_cache_key
from gitlab_radar.database.results import create_result
from gitlab_radar.schemas.project import Project, ProjectAnalysisStatus
from gitlab_radar.schemas.scan import ScanItemState, ScanState, ScanTargetKind
from gitlab_radar.services.analysis import FileSelection
from gitlab_radar.services.project_blacklist import project_is_blacklisted

FINAL_STATES = frozenset(
    {
        ScanItemState.SUCCESS,
        ScanItemState.PARTIAL,
        ScanItemState.FAILED,
        ScanItemState.REUSED,
        ScanItemState.MISSING,
        ScanItemState.SKIPPED,
    }
)


async def _target(project: Project, connection: BaseDBAsyncClient) -> ScanTarget:
    target, _ = await ScanTarget.get_or_create(
        gitlab_id=project.id,
        kind=ScanTargetKind.BRANCH,
        ref=project.default_branch or '',
        defaults={'is_default': True},
        using_db=connection,
    )
    await ScanTarget.filter(gitlab_id=project.id).exclude(id=target.id).using_db(connection).update(is_default=False)
    await ScanTarget.filter(id=target.id).using_db(connection).update(is_default=True)
    return target


async def prepare_scan(scan: ScanRun, projects: list[Project]) -> None:
    for project in projects:
        async with in_transaction() as connection:
            await _item(scan, project, connection)


async def _item(scan: ScanRun, project: Project, connection: BaseDBAsyncClient) -> ScanItem:
    target = await _target(project, connection)
    fallback = target.last_successful_result_id
    metadata = target.successful_metadata
    if target.last_completed_item_id:
        previous = await ScanItem.get(id=target.last_completed_item_id).using_db(connection)
        fallback = (
            previous.result_id
            if previous.state
            in {ScanItemState.SUCCESS, ScanItemState.PARTIAL, ScanItemState.REUSED, ScanItemState.MISSING}
            else previous.fallback_result_id
        )
        metadata = previous.metadata if fallback == previous.result_id else previous.fallback_metadata
    item, _ = await ScanItem.get_or_create(
        scan=scan,
        target=target,
        defaults={'metadata': project_metadata(project), 'fallback_result_id': fallback, 'fallback_metadata': metadata},
        using_db=connection,
    )
    await ScanTarget.filter(id=target.id).using_db(connection).update(last_attempt_id=item.id)
    return item


async def find_reusable_project(gitlab_id: int, revision: str | None, fingerprint: str) -> AnalysisResult | None:
    if not revision:
        return None
    observation = (
        await ScanItem.filter(
            target__gitlab_id=gitlab_id,
            revision=revision,
            analysis_fingerprint=fingerprint,
            result__status=ProjectAnalysisStatus.SUCCESS,
            state__in=[ScanItemState.SUCCESS, ScanItemState.REUSED],
        )
        .select_related('result')
        .order_by('-id')
        .first()
    )
    if observation is not None:
        return observation.result
    return await AnalysisResult.filter(
        gitlab_id=gitlab_id,
        source_revision=revision,
        analysis_fingerprint=fingerprint,
        status=ProjectAnalysisStatus.SUCCESS,
    ).first()


async def find_reusable_inputs(gitlab_id: int, files: dict[str, str], fingerprint: str) -> AnalysisResult | None:
    return await AnalysisResult.filter(
        cache_key=result_cache_key(gitlab_id, input_digest(files), fingerprint),
        status=ProjectAnalysisStatus.SUCCESS,
    ).first()


async def clone_project(source: AnalysisResult, scan: ScanRun, project: Project, fingerprint: str) -> ScanItem:
    async with in_transaction() as connection:
        item = await _item(scan, project, connection)
        project.scanned_at = datetime.now(UTC)
        await (
            ScanItem.filter(id=item.id)
            .using_db(connection)
            .update(
                metadata=project_metadata(project),
                scanned_at=project.scanned_at,
                result_id=source.id,
                revision=project.revision,
                analysis_fingerprint=fingerprint,
                input_digest=source.input_digest,
                state=ScanItemState.REUSED,
                error=None,
            )
        )
        await (
            ScanTarget.filter(id=item.target_id)
            .using_db(connection)
            .update(
                last_completed_item_id=item.id,
                last_successful_result_id=source.id,
                successful_metadata=project_metadata(project),
            )
        )
    return item


async def save_collected_project(
    scan: ScanRun, project: Project, *, files: dict[str, str], selections: list[FileSelection], fingerprint: str
) -> ScanItem:
    error = project.scan_error
    async with in_transaction() as connection:
        item = await _item(scan, project, connection)
        await (
            ScanItem.filter(id=item.id)
            .using_db(connection)
            .update(
                metadata=project_metadata(project),
                revision=project.revision,
                analysis_fingerprint=fingerprint,
                input_digest=input_digest(files) if error is None else None,
                state=ScanItemState.COLLECTED if error is None else ScanItemState.FAILED,
                error=error,
            )
        )
        await _save_files(item, files, selections, connection)
    return item


async def _save_files(
    item: ScanItem, files: dict[str, str], selections: list[FileSelection], connection: BaseDBAsyncClient
) -> None:
    by_path: dict[str, list[FileSelection]] = {}
    for selection in selections:
        by_path.setdefault(selection.path, []).append(selection)
    for path, content in files.items():
        row = await ScanFile.create(item=item, path=path, content=content, using_db=connection)
        usages = [
            ScanFileUsage(
                file=row,
                language_code=selection.language_code,
                analyzer_key=selection.analyzer_key,
                role=selection.role,
            )
            for selection in by_path.get(path, [])
        ]
        if usages:
            await ScanFileUsage.bulk_create(usages, using_db=connection)


async def save_analysis(item_id: int, project: Project, error: str | None = None) -> None:
    async with in_transaction() as connection:
        item = await ScanItem.get(id=item_id).using_db(connection)
        if item.state in FINAL_STATES and item.result_id is not None:
            return
        result = await create_result(item, project, connection)
        fallback = None
        fallback_metadata = {}
        if project.analysis_status == ProjectAnalysisStatus.FAILED:
            target = await ScanTarget.get(id=item.target_id).using_db(connection)
            fallback = target.last_successful_result_id
            fallback_metadata = target.successful_metadata
        project.scanned_at = datetime.now(UTC)
        await (
            ScanItem.filter(id=item_id)
            .using_db(connection)
            .update(
                scanned_at=project.scanned_at,
                result_id=result.id,
                state=ScanItemState(project.analysis_status.value),
                metadata=project_metadata(project),
                error=error or project.scan_error,
                fallback_result_id=fallback,
                fallback_metadata=fallback_metadata,
            )
        )
        values = {'last_completed_item_id': item_id}
        if project.analysis_status == ProjectAnalysisStatus.SUCCESS:
            values['last_successful_result_id'] = result.id
            values['successful_metadata'] = project_metadata(project)
        await ScanTarget.filter(id=item.target_id).using_db(connection).update(**values)
        await ScanFile.filter(item_id=item_id).using_db(connection).delete()


async def restore_previous_analysis(item_id: int, project: Project, error: str) -> bool:
    # Failure is an observation too: save its result and the target-local fallback atomically.
    await save_analysis(item_id, project, error)
    item = await ScanItem.get(id=item_id)
    return item.fallback_result_id is not None


async def skip_project(scan: ScanRun, project: Project, error: str) -> None:
    async with in_transaction() as connection:
        item = await _item(scan, project, connection)
        await ScanItem.filter(id=item.id).using_db(connection).update(state=ScanItemState.SKIPPED, error=error)


async def project_files(item_id: int) -> dict[str, str]:
    return dict(await ScanFile.filter(item_id=item_id).values_list('path', 'content'))


async def delete_project_files(item_id: int) -> None:
    await ScanFile.filter(item_id=item_id).delete()


async def delete_scan_files(scan_id: int) -> None:
    await ScanFile.filter(item__scan_id=scan_id).delete()


async def carry_forward_missing_projects(scan: ScanRun, blacklist: tuple[str, ...]) -> None:
    current_targets = await ScanItem.filter(scan_id=scan.id).values_list('target_id', flat=True)
    targets = (
        await ScanTarget.filter(is_default=True).exclude(id__in=current_targets).select_related('last_completed_item')
    )
    for target in targets:
        previous = target.last_completed_item
        if previous is None or project_is_blacklisted(previous.metadata.get('path_with_namespace', ''), blacklist):
            continue
        result_id = (
            previous.result_id
            if previous.state != ScanItemState.FAILED
            else (previous.fallback_result_id or previous.result_id)
        )
        metadata = previous.metadata if result_id == previous.result_id else previous.fallback_metadata
        async with in_transaction() as connection:
            item = await ScanItem.create(
                scan=scan,
                target=target,
                result_id=result_id,
                metadata=metadata,
                revision=previous.revision,
                analysis_fingerprint=previous.analysis_fingerprint,
                input_digest=previous.input_digest,
                state=ScanItemState.MISSING,
                error=previous.error,
                scanned_at=previous.scanned_at,
                using_db=connection,
            )
            await ScanTarget.filter(id=target.id).using_db(connection).update(last_completed_item_id=item.id)


async def trim_old_scans(keep: int) -> None:
    retained = await ScanRun.filter(published=True).order_by('-id').limit(keep).values_list('id', flat=True)
    if retained:
        await ScanRun.filter(published=True).exclude(id__in=retained).delete()
    used = set(await ScanTarget.all().values_list('last_successful_result_id', flat=True))
    used.update(await ScanItem.all().values_list('result_id', flat=True))
    used.update(await ScanItem.all().values_list('fallback_result_id', flat=True))
    used.discard(None)
    await AnalysisResult.all().exclude(id__in=list(used)).delete()


async def fail_pending_items(scan_id: int, error: str) -> None:
    await ScanItem.filter(scan_id=scan_id, state__in=[ScanItemState.PENDING, ScanItemState.COLLECTED]).update(
        state=ScanItemState.FAILED,
        error=error,
    )


async def recover_stale_scans() -> None:
    scan_ids = await ScanRun.filter(state=ScanState.RUNNING).values_list('id', flat=True)
    for scan_id in scan_ids:
        await delete_scan_files(scan_id)
        await fail_pending_items(scan_id, 'Приложение остановлено до завершения обработки')
    if scan_ids:
        await ScanRun.filter(id__in=scan_ids).update(
            state=ScanState.FAILED,
            completed_at=datetime.now(UTC),
            error='Приложение было остановлено до завершения сканирования',
        )
