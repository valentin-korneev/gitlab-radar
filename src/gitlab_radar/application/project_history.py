from tortoise.expressions import Q

from gitlab_radar.database.models import PackagePeriod, ScanItem, ScanTarget
from gitlab_radar.schemas.history import (
    PackageChange,
    PackageChangeKind,
    PackageChangeQuery,
    PackageChangesPage,
    PackageInventoryPage,
    PackagePeriodsPage,
    PackagePeriodSummary,
    ProjectHistoryPage,
    ProjectHistoryQuery,
    ProjectObservation,
    TargetSummary,
)

OBSERVATION_FIELDS = (
    'id',
    'scan_id',
    'state',
    'revision',
    'scanned_at',
    'error',
    'results_archived',
    'history_recorded',
    'observed_languages',
    'baseline_languages',
    'added_packages',
    'removed_packages',
    'updated_packages',
    'scan__created_at',
)


async def project_observations(target: ScanTarget, filters: ProjectHistoryQuery) -> ProjectHistoryPage:
    query = ScanItem.filter(carried_forward=False, target_id=target.id)
    if filters.before is not None:
        query = query.filter(scan_id__lt=filters.before)
    rows = await query.order_by('-scan_id').limit(filters.limit + 1).values(*OBSERVATION_FIELDS)
    items = [
        ProjectObservation.model_validate({**row, 'created_at': row['scan__created_at']})
        for row in rows[: filters.limit]
    ]
    return ProjectHistoryPage(
        target=TargetSummary.model_validate(target, from_attributes=True),
        items=items,
        cursor=items[-1].scan_id if items else None,
        has_more=len(rows) > filters.limit,
    )


def _package_change(periods: list[PackagePeriod], scan_id: int) -> PackageChange:
    before = next((period for period in periods if period.closed_in_id == scan_id), None)
    after = next((period for period in periods if period.scan_from_id == scan_id), None)
    reference = after or before
    return PackageChange(
        package_key=reference.package_key,
        language=reference.language,
        module_path=reference.module_path,
        scope=reference.scope,
        name=reference.name,
        kind=PackageChangeKind.UPDATED
        if before and after
        else PackageChangeKind.ADDED
        if after
        else PackageChangeKind.REMOVED,
        before_versions=before.versions if before else [],
        after_versions=after.versions if after else [],
    )


async def package_changes(item: ScanItem, filters: PackageChangeQuery) -> PackageChangesPage:
    query = PackagePeriod.filter(
        Q(scan_from_id=item.scan_id, baseline=False) | Q(closed_in_id=item.scan_id),
        target_id=item.target_id,
        package_key__gt=filters.after,
    )
    if filters.name:
        query = query.filter(name__icontains=filters.name)
    if filters.language is not None:
        query = query.filter(language=filters.language)
    if filters.module_path is not None:
        query = query.filter(module_path=filters.module_path)
    keys = await query.order_by('package_key').distinct().limit(filters.limit + 1).values_list('package_key', flat=True)
    selected = keys[: filters.limit]
    rows = await query.filter(package_key__in=selected)
    grouped: dict[str, list[PackagePeriod]] = {}
    for row in rows:
        grouped.setdefault(row.package_key, []).append(row)
    changes = [_package_change(grouped[key], item.scan_id) for key in selected]
    return PackageChangesPage(
        items=changes,
        cursor=selected[-1] if selected else filters.after,
        has_more=len(keys) > filters.limit,
        history_recorded=item.history_recorded,
        observed_languages=item.observed_languages,
        baseline_languages=item.baseline_languages,
    )


async def package_periods(target_id: int, package_key: str, filters: ProjectHistoryQuery) -> PackagePeriodsPage:
    query = PackagePeriod.filter(target_id=target_id, package_key=package_key)
    if filters.before is not None:
        query = query.filter(scan_from_id__lt=filters.before)
    rows = await query.order_by('-scan_from_id').limit(filters.limit + 1)
    items = [PackagePeriodSummary.model_validate(row, from_attributes=True) for row in rows[: filters.limit]]
    return PackagePeriodsPage(
        items=items, cursor=items[-1].scan_from_id if items else None, has_more=len(rows) > filters.limit
    )


async def package_inventory_at(target_id: int, scan_id: int, filters: PackageChangeQuery) -> PackageInventoryPage:
    query = PackagePeriod.filter(
        Q(closed_in_id__isnull=True) | Q(closed_in_id__gt=scan_id),
        target_id=target_id,
        scan_from_id__lte=scan_id,
        package_key__gt=filters.after,
    )
    if filters.name:
        query = query.filter(name__icontains=filters.name)
    if filters.language is not None:
        query = query.filter(language=filters.language)
    if filters.module_path is not None:
        query = query.filter(module_path=filters.module_path)
    rows = await query.order_by('package_key').limit(filters.limit + 1)
    items = [PackagePeriodSummary.model_validate(row, from_attributes=True) for row in rows[: filters.limit]]
    return PackageInventoryPage(
        items=items, cursor=items[-1].package_key if items else filters.after, has_more=len(rows) > filters.limit
    )
