import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from gitlab_radar.config import settings
from gitlab_radar.database.models import ProjectFile, ProjectSnapshot, ScanRun
from gitlab_radar.schemas.project import Project
from gitlab_radar.schemas.scan import ScanState
from gitlab_radar.services.company_rules import apply_company_compliance

logger = logging.getLogger(__name__)


class ProjectCache:
    def __init__(self) -> None:
        self.scan_id: int | None = None
        self.projects: list[Project] = []

    def invalidate(self) -> None:
        self.scan_id = None


PROJECT_CACHE = ProjectCache()


async def import_legacy_snapshot() -> None:
    if await ScanRun.filter(published=True).exists():
        return

    path = settings.application.data_dir / 'projects.json'
    if not path.exists():
        return

    try:
        payloads = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        logger.exception('Не удалось импортировать прежний снимок проектов из %s', path)
        return
    if not isinstance(payloads, list):
        logger.warning('Прежний снимок проектов имеет неожиданный формат: %s', path)
        return

    now = datetime.now(UTC)
    scan = await ScanRun.create(
        state=ScanState.COMPLETED,
        phase='completed',
        started_at=now,
        completed_at=now,
        projects_count=len(payloads),
        total_steps=len(payloads),
        completed_steps=len(payloads),
        collected_projects=len(payloads),
        analyzed_projects=len(payloads),
        published=True,
    )
    snapshots = []
    for payload in payloads:
        if not isinstance(payload, dict) or not isinstance(payload.get('id'), int):
            continue
        project_payload = _without_compliance(payload)
        snapshots.append(
            ProjectSnapshot(
                scan=scan,
                gitlab_id=project_payload['id'],
                payload=project_payload,
                collected=True,
                analyzed=True,
            ),
        )
    await ProjectSnapshot.bulk_create(snapshots)
    logger.info('Прежний JSON-снимок импортирован в SQLite: проектов %d', len(snapshots))


async def latest_published_scan() -> ScanRun | None:
    return await ScanRun.filter(published=True).order_by('-id').first()


async def latest_scan() -> ScanRun | None:
    return await ScanRun.all().order_by('-id').first()


async def load_projects() -> list[Project]:
    scan = await latest_published_scan()
    if scan is None:
        return []
    if PROJECT_CACHE.scan_id != scan.id:
        rows = await ProjectSnapshot.filter(scan_id=scan.id).order_by('gitlab_id').values_list('payload', flat=True)
        projects = [Project.model_validate(payload) for payload in rows]
        for project in projects:
            apply_company_compliance(project)
        PROJECT_CACHE.scan_id = scan.id
        PROJECT_CACHE.projects = projects
        logger.info('Снимок %d загружен из SQLite: проектов %d', scan.id, len(projects))
    return [project.model_copy(deep=True) for project in PROJECT_CACHE.projects]


def invalidate_project_cache() -> None:
    PROJECT_CACHE.invalidate()


async def find_reusable_project(gitlab_id: int, revision: str | None) -> ProjectSnapshot | None:
    if not revision:
        return None
    return (
        await ProjectSnapshot.filter(
            gitlab_id=gitlab_id,
            revision=revision,
            analyzed=True,
            scan__published=True,
        )
        .order_by('-scan_id')
        .first()
    )


async def clone_project(
    source: ProjectSnapshot,
    scan: ScanRun,
    project: Project,
) -> ProjectSnapshot:
    payload = dict(source.payload)
    current = _project_payload(project)
    current.pop('subprojects', None)
    payload.update(current)
    snapshot = await ProjectSnapshot.create(
        scan=scan,
        gitlab_id=project.id,
        revision=source.revision,
        payload=payload,
        collected=True,
        analyzed=True,
        reused=True,
    )
    source_files = await ProjectFile.filter(project=source)
    await ProjectFile.bulk_create(
        [
            ProjectFile(
                project=snapshot,
                path=file.path,
                local_path=file.local_path,
                size=file.size,
            )
            for file in source_files
        ],
    )
    return snapshot


async def save_collected_project(
    scan: ScanRun,
    project: Project,
    revision: str | None,
    files: dict[str, Path],
    error: str | None = None,
) -> ProjectSnapshot:
    snapshot = await ProjectSnapshot.create(
        scan=scan,
        gitlab_id=project.id,
        revision=revision,
        payload=_project_payload(project),
        collected=error is None,
        error=error,
    )
    await ProjectFile.bulk_create(
        [
            ProjectFile(
                project=snapshot,
                path=path,
                local_path=str(local_path),
                size=local_path.stat().st_size,
            )
            for path, local_path in files.items()
        ],
    )
    return snapshot


async def project_files(snapshot_id: int) -> dict[str, Path]:
    rows = await ProjectFile.filter(project_id=snapshot_id).values('path', 'local_path')
    return {row['path']: Path(row['local_path']) for row in rows}


async def save_analysis(snapshot_id: int, project: Project, error: str | None = None) -> None:
    payload = _project_payload(project)
    await ProjectSnapshot.filter(id=snapshot_id).update(
        payload=payload,
        analyzed=error is None,
        error=error,
    )


async def trim_old_scans(keep: int = 5) -> None:
    retained_ids = await ScanRun.filter(published=True).order_by('-id').limit(keep).values_list('id', flat=True)
    if retained_ids:
        await ScanRun.filter(published=True).exclude(id__in=retained_ids).delete()


def _project_payload(project: Project) -> dict:
    return _without_compliance(project.model_dump(mode='json'))


def _without_compliance(payload: dict) -> dict:
    result = dict(payload)
    result.pop('company_compliance_percentage', None)
    result.pop('company_rule_results', None)
    result['subprojects'] = [
        {
            key: value
            for key, value in subproject.items()
            if key not in {'company_compliance_percentage', 'company_rule_results'}
        }
        for subproject in result.get('subprojects', [])
        if isinstance(subproject, dict)
    ]
    return result
