from tortoise.transactions import in_transaction
lazy from tortoise.backends.base.client import BaseDBAsyncClient

from gitlab_radar.database.models import PackageHistoryHead, PackagePeriod, ScanItem, ScanTarget
from gitlab_radar.domain.package_history import PackageRecord, canonical_package_language, package_inventory
from gitlab_radar.schemas.project import LanguageAnalysisStatus, ProjectAnalysisStatus
from gitlab_radar.schemas.scan import ScanItemState

FINAL_ITEM_STATES = (
    ScanItemState.SUCCESS,
    ScanItemState.REUSED,
    ScanItemState.PARTIAL,
    ScanItemState.FAILED,
    ScanItemState.SKIPPED,
    ScanItemState.MISSING,
)


async def record_item_history(item_id: int, connection: BaseDBAsyncClient) -> None:
    item = await ScanItem.get(id=item_id).using_db(connection)
    await ScanTarget.get(id=item.target_id).using_db(connection).select_for_update()
    pending = (
        await ScanItem.filter(
            target_id=item.target_id, scan_id__lte=item.scan_id, history_recorded=False, state__in=FINAL_ITEM_STATES
        )
        .using_db(connection)
        .select_related('result')
        .order_by('scan_id', 'id')
    )
    for observation in pending:
        await _record_observation(observation, connection)


async def _record_observation(item: ScanItem, connection: BaseDBAsyncClient) -> None:
    payload = item.result.payload if item.result else {}
    values = {'history_recorded': True, 'diagnostic_summary': payload.get('analysis_diagnostics', [])}
    if (
        item.state in {ScanItemState.SUCCESS, ScanItemState.REUSED}
        and item.result is not None
        and item.result.status == ProjectAnalysisStatus.SUCCESS
        and not item.carried_forward
    ):
        values.update(await _record_packages(item, payload, connection))
    await ScanItem.filter(id=item.id).using_db(connection).update(**values)


async def _record_packages(item: ScanItem, payload: dict, connection: BaseDBAsyncClient) -> dict:
    heads = await PackageHistoryHead.filter(target_id=item.target_id).using_db(connection)
    previous_languages = {head.language for head in heads}
    declared = {canonical_package_language(language['code']) for language in payload.get('languages', [])}
    observed = {
        canonical_package_language(language['code'])
        for language in payload.get('languages', [])
        if language.get('analysis_status') == LanguageAnalysisStatus.ANALYZED
    } | (previous_languages - declared)
    inventory = {
        key: package for key, package in package_inventory(payload).items() if package.location.language in observed
    }
    baseline = observed - previous_languages
    periods = await PackagePeriod.filter(
        target_id=item.target_id, closed_in_id__isnull=True, language__in=observed
    ).using_db(connection)
    previous = {period.package_key: period for period in periods}
    changes = await _update_periods(item, inventory, previous, baseline, connection)
    for language in observed:
        await PackageHistoryHead.update_or_create(
            target_id=item.target_id,
            language=language,
            defaults={'last_scan_id': item.scan_id},
            using_db=connection,
        )
    return {'observed_languages': sorted(observed), 'baseline_languages': sorted(baseline), **changes}


async def _update_periods(
    item: ScanItem,
    inventory: dict[str, PackageRecord],
    previous: dict[str, PackagePeriod],
    baseline: set[str],
    connection: BaseDBAsyncClient,
) -> dict[str, int]:
    counts = {'added_packages': 0, 'removed_packages': 0, 'updated_packages': 0}
    unchanged = []
    closed = []
    created = []
    for key, old in previous.items():
        current = inventory.get(key)
        if current is not None and current.versions == old.versions:
            unchanged.append(old.id)
        else:
            closed.append(old.id)
            counts['updated_packages' if current is not None else 'removed_packages'] += 1
    for key, package in inventory.items():
        old = previous.get(key)
        if old is not None and old.versions == package.versions:
            continue
        initial = package.location.language in baseline
        if old is None and not initial:
            counts['added_packages'] += 1
        created.append(
            PackagePeriod(
                target_id=item.target_id,
                package_key=key,
                language=package.location.language,
                module_path=package.location.module_path,
                scope=package.location.scope,
                name=package.name,
                versions=package.versions,
                scan_from_id=item.scan_id,
                scan_to_id=item.scan_id,
                baseline=initial,
            )
        )
    if unchanged:
        await _update_bounds(unchanged, {'scan_to_id': item.scan_id}, connection)
    if closed:
        await _update_bounds(closed, {'closed_in_id': item.scan_id}, connection)
    if created:
        await PackagePeriod.bulk_create(created, using_db=connection, batch_size=200)
    return counts


async def _update_bounds(ids: list[int], values: dict[str, int], connection: BaseDBAsyncClient) -> None:
    batch_size = 2000
    for offset in range(0, len(ids), batch_size):
        await PackagePeriod.filter(id__in=ids[offset : offset + batch_size]).using_db(connection).update(**values)


async def backfill_package_history(limit: int = 25) -> bool:
    ids = (
        await ScanItem.filter(history_recorded=False, state__in=FINAL_ITEM_STATES)
        .order_by('scan_id', 'id')
        .limit(limit)
        .values_list('id', flat=True)
    )
    for item_id in ids:
        await backfill_item_history(item_id)
    return bool(ids)


async def backfill_item_history(item_id: int) -> None:
    async with in_transaction() as connection:
        await record_item_history(item_id, connection)
