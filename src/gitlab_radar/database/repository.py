import asyncio
import logging
from datetime import UTC, datetime

from tortoise.transactions import in_transaction

from gitlab_radar.database.models import ProjectFile, ProjectSnapshot, ScanRun
from gitlab_radar.schemas.project import Project, ProjectSubproject
from gitlab_radar.schemas.technology import PackageManager
from gitlab_radar.services.application_parameters import application_parameter_values
from gitlab_radar.services.company_rules import apply_company_compliance, load_company_requirements

logger = logging.getLogger(__name__)
REUSED_PROJECT_METADATA_FIELDS = {
    'id',
    'name',
    'path_with_namespace',
    'default_branch',
    'web_url',
    'last_activity_at',
    'webhooks',
    'webhooks_accessible',
    'gitlab_access_level',
    'revision',
    'scan_error',
}


class ProjectCache:
    def __init__(self) -> None:
        self.scan_id: int | None = None
        self.projects: list[Project] = []

    def invalidate(self) -> None:
        self.scan_id = None


PROJECT_CACHE = ProjectCache()


async def latest_published_scan() -> ScanRun | None:
    return await ScanRun.filter(published=True).order_by('-id').first()


async def latest_scan() -> ScanRun | None:
    return await ScanRun.all().order_by('-id').first()


async def load_projects() -> list[Project]:
    scan = await latest_published_scan()
    if scan is None:
        return []
    if PROJECT_CACHE.scan_id != scan.id:
        requirements, parameter_values = await asyncio.gather(
            load_company_requirements(),
            application_parameter_values(),
        )
        rows = await ProjectSnapshot.filter(scan_id=scan.id).order_by('gitlab_id').values_list('payload', flat=True)
        projects = [Project.model_validate(payload) for payload in rows]
        for project in projects:
            if not project.subprojects:
                project.subprojects.append(ProjectSubproject(path='.', package_manager=PackageManager.UNKNOWN))
            apply_company_compliance(project, requirements, parameter_values)
        PROJECT_CACHE.scan_id = scan.id
        PROJECT_CACHE.projects = projects
        logger.info('Снимок %d загружен из PostgreSQL: проектов %d', scan.id, len(projects))
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
    payload.update(
        project.model_dump(
            mode='json',
            include=REUSED_PROJECT_METADATA_FIELDS,
        ),
    )
    return await ProjectSnapshot.create(
        scan=scan,
        gitlab_id=project.id,
        revision=source.revision,
        payload=payload,
        collected=True,
        analyzed=True,
        reused=True,
    )


async def save_collected_project(
    scan: ScanRun,
    project: Project,
    revision: str | None,
    files: dict[str, str],
    error: str | None = None,
) -> ProjectSnapshot:
    async with in_transaction() as connection:
        snapshot = await ProjectSnapshot.create(
            scan=scan,
            gitlab_id=project.id,
            revision=revision,
            payload=_project_payload(project),
            collected=error is None,
            error=error,
            using_db=connection,
        )
        await ProjectFile.bulk_create(
            [
                ProjectFile(
                    project=snapshot,
                    path=path,
                    content=content,
                )
                for path, content in files.items()
            ],
            using_db=connection,
        )
    return snapshot


async def project_files(snapshot_id: int) -> dict[str, str]:
    rows = await ProjectFile.filter(project_id=snapshot_id).values('path', 'content')
    return {row['path']: row['content'] for row in rows}


async def delete_project_files(snapshot_id: int) -> None:
    await ProjectFile.filter(project_id=snapshot_id).delete()


async def delete_scan_files(scan_id: int) -> None:
    snapshot_ids = await ProjectSnapshot.filter(scan_id=scan_id).values_list('id', flat=True)
    if snapshot_ids:
        await ProjectFile.filter(project_id__in=snapshot_ids).delete()


async def save_analysis(snapshot_id: int, project: Project, error: str | None = None) -> None:
    payload = _project_payload(project)
    await ProjectSnapshot.filter(id=snapshot_id).update(
        payload=payload,
        analyzed=error is None,
        error=error,
    )


async def restore_previous_analysis(snapshot_id: int, project: Project, error: str) -> bool:
    source = (
        await ProjectSnapshot.filter(
            gitlab_id=project.id,
            analyzed=True,
            scan__published=True,
        )
        .order_by('-scan_id')
        .first()
    )
    if source is None:
        return False
    payload = dict(source.payload)
    payload.update(
        project.model_dump(
            mode='json',
            include=REUSED_PROJECT_METADATA_FIELDS,
        ),
    )
    payload['revision'] = source.revision
    await ProjectSnapshot.filter(id=snapshot_id).update(
        payload=payload,
        analyzed=False,
        error=error,
    )
    return True


async def trim_old_scans(keep: int) -> None:
    retained_ids = await ScanRun.filter(published=True).order_by('-id').limit(keep).values_list('id', flat=True)
    if retained_ids:
        await ScanRun.filter(published=True).exclude(id__in=retained_ids).delete()


async def recover_stale_scans() -> None:
    scan_ids = await ScanRun.filter(state='running').values_list('id', flat=True)
    if not scan_ids:
        return
    for scan_id in scan_ids:
        await delete_scan_files(scan_id)
    await ScanRun.filter(id__in=scan_ids).update(
        state='failed',
        completed_at=datetime.now(UTC),
        error='Приложение было остановлено до завершения сканирования',
    )


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
