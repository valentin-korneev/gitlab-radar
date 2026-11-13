from tortoise.functions import Count

from gitlab_radar.database.models import ScanItem, ScanRun
from gitlab_radar.schemas.history import ScanChartPoint
from gitlab_radar.schemas.scan import ScanItemState, ScanSource, ScanState, ScanStatus
from gitlab_radar.schemas.scan_management import (
    ScanHistoryPage,
    ScanHistoryQuery,
    ScanItemDetail,
    ScanItemsPage,
    ScanItemSummary,
)

SUMMARY_FIELDS = (
    'id',
    'state',
    'phase',
    'created_at',
    'started_at',
    'completed_at',
    'source',
    'requested_by',
    'options',
    'schedule_id',
    'schedule_name',
    'retry_of_id',
    'projects_count',
    'total_steps',
    'completed_steps',
    'collected_projects',
    'analyzed_projects',
    'reused_projects',
    'skipped_projects',
    'gitlab_requests',
    'current_project',
    'error',
    'results_archived',
)


async def scan_history(
    before: int | None,
    limit: int,
    run_state: ScanState | None,
    source: ScanSource | None,
    schedule_id: int | None = None,
) -> ScanHistoryPage:
    query = ScanRun.all()
    if before is not None:
        query = query.filter(id__lt=before)
    if run_state is not None:
        query = query.filter(state=run_state)
    if source is not None:
        query = query.filter(source=source)
    if schedule_id is not None:
        query = query.filter(schedule_id=schedule_id)
    rows = await query.order_by('-id').limit(limit + 1).values(*SUMMARY_FIELDS)
    items = [ScanStatus.model_validate(row) for row in rows[:limit]]
    return ScanHistoryPage(items=items, cursor=items[-1].id if items else None, has_more=len(rows) > limit)


def item_summary(item: ScanItem) -> ScanItemSummary:
    return ScanItemSummary(
        id=item.id,
        project_id=item.target.gitlab_id,
        project_path=item.metadata.get('path_with_namespace')
        or item.fallback_metadata.get('path_with_namespace')
        or str(item.target.gitlab_id),
        ref=item.target.ref,
        state=item.state,
        error=item.error,
        scanned_at=item.scanned_at,
        result_id=item.result_id,
    )


async def scan_items(scan_id: int, after: int, limit: int, item_state: ScanItemState | None) -> ScanItemsPage:
    scan = await ScanRun.get(id=scan_id).only('id', 'options')
    query = ScanItem.filter(scan_id=scan_id, id__gt=after)
    selected_ids = scan.options.get('project_ids')
    if selected_ids is not None:
        query = query.filter(target__gitlab_id__in=selected_ids)
    if item_state is not None:
        query = query.filter(state=item_state)
    rows = await query.select_related('target').order_by('id').limit(limit + 1)
    items = [item_summary(item) for item in rows[:limit]]
    return ScanItemsPage(items=items, cursor=items[-1].id if items else after, has_more=len(rows) > limit)


async def scan_item_detail(scan_id: int, item_id: int) -> ScanItemDetail | None:
    item = await ScanItem.filter(id=item_id, scan_id=scan_id).select_related('target', 'result').first()
    if item is None:
        return None
    return ScanItemDetail(
        **item_summary(item).model_dump(),
        results_archived=item.results_archived,
        revision=item.revision,
        analysis_fingerprint=item.analysis_fingerprint,
        diagnostics=item.result.payload.get('analysis_diagnostics', []) if item.result else item.diagnostic_summary,
    )


async def scan_statistics(filters: ScanHistoryQuery) -> list[ScanChartPoint]:
    page = await scan_history(filters.before, filters.limit, filters.state, filters.source, filters.schedule_id)
    ids = [run.id for run in page.items]
    counts = await (
        ScanItem.filter(scan_id__in=ids, carried_forward=False)
        .group_by('scan_id', 'state')
        .annotate(total=Count('id'))
        .values('scan_id', 'state', 'total')
    )
    categories = {
        ScanItemState.SUCCESS: 'successful',
        ScanItemState.REUSED: 'successful',
        ScanItemState.PARTIAL: 'partial',
        ScanItemState.FAILED: 'failed',
        ScanItemState.SKIPPED: 'skipped',
    }
    points = {
        run.id: ScanChartPoint(
            id=run.id, created_at=run.created_at, duration_seconds=run.duration_seconds, state=run.state
        )
        for run in page.items
    }
    for count in counts:
        category = categories.get(count['state'])
        if category is not None:
            point = points[count['scan_id']]
            setattr(point, category, getattr(point, category) + count['total'])
    return [points[run.id] for run in reversed(page.items)]
