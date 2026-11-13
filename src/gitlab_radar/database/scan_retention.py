from dataclasses import dataclass
from time import monotonic

from tortoise.expressions import Subquery
from tortoise.transactions import in_transaction

from gitlab_radar.database.models import AnalysisResult, ScanFile, ScanItem, ScanRun, ScanTarget
from gitlab_radar.database.package_history import record_item_history


@dataclass(slots=True)
class CleanupClock:
    next_collection: float = 0


_CLEANUP_CLOCK = CleanupClock()
ORPHAN_COLLECTION_INTERVAL = 60
LOG_METADATA_FIELDS = {'id', 'name', 'path_with_namespace', 'default_branch', 'web_url'}


async def archive_old_results(keep: int, limit: int = 50) -> bool:
    keep = max(1, keep)
    recent = await ScanRun.filter(completed_at__isnull=False).order_by('-id').limit(keep).values_list('id', flat=True)
    if len(recent) < keep:
        return False
    published = await ScanRun.filter(published=True).order_by('-id').limit(keep).values_list('id', flat=True)
    old_runs = ScanRun.filter(completed_at__isnull=False, id__lt=recent[-1]).exclude(id__in=published)
    await old_runs.filter(results_archived=False).update(results_archived=True, updated_project_ids=[])
    ids = (
        await ScanItem.filter(scan_id__in=Subquery(old_runs.values_list('id', flat=True)), results_archived=False)
        .exclude(
            id__in=Subquery(ScanTarget.filter(last_attempt_id__isnull=False).values_list('last_attempt_id', flat=True))
        )
        .exclude(
            id__in=Subquery(
                ScanTarget.filter(last_completed_item_id__isnull=False).values_list('last_completed_item_id', flat=True)
            )
        )
        .order_by('scan_id', 'id')
        .limit(limit)
        .values_list('id', flat=True)
    )
    for item_id in ids:
        async with in_transaction() as connection:
            await record_item_history(item_id, connection)
            item = await ScanItem.get(id=item_id).using_db(connection)
            metadata = {key: value for key, value in item.metadata.items() if key in LOG_METADATA_FIELDS}
            await (
                ScanItem.filter(id=item_id)
                .using_db(connection)
                .update(
                    result_id=None,
                    fallback_result_id=None,
                    metadata=metadata,
                    fallback_metadata={},
                    results_archived=True,
                )
            )
            await ScanFile.filter(item_id=item_id).using_db(connection).delete()
    if ids or monotonic() >= _CLEANUP_CLOCK.next_collection:
        await _delete_unused_results()
        _CLEANUP_CLOCK.next_collection = monotonic() + ORPHAN_COLLECTION_INTERVAL
    return bool(ids)


async def _delete_unused_results() -> None:
    await (
        AnalysisResult.all()
        .exclude(
            id__in=Subquery(
                ScanTarget.filter(last_successful_result_id__isnull=False).values_list(
                    'last_successful_result_id', flat=True
                )
            )
        )
        .exclude(id__in=Subquery(ScanItem.filter(result_id__isnull=False).values_list('result_id', flat=True)))
        .exclude(
            id__in=Subquery(
                ScanItem.filter(fallback_result_id__isnull=False).values_list('fallback_result_id', flat=True)
            )
        )
        .delete()
    )
