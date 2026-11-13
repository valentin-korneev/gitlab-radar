import asyncio
import logging

from gitlab_radar.database.languages import sync_programming_languages
from gitlab_radar.database.models import AnalysisResult, ProgrammingFramework, ScanItem, ScanRun, ScanTarget
from gitlab_radar.database.scan_repository import (
    carry_forward_missing_projects,
    clone_project,
    delete_project_files,
    delete_scan_files,
    fail_pending_items,
    find_reusable_inputs,
    find_reusable_project,
    prepare_scan,
    project_files,
    recover_stale_scans,
    restore_previous_analysis,
    save_analysis,
    save_collected_project,
    skip_project,
    trim_old_scans,
)
from gitlab_radar.schemas.project import (
    Project,
    ProjectAnalysisStatus,
    ProjectDataStatus,
    ProjectFramework,
    ProjectSubproject,
)
from gitlab_radar.schemas.scan import ScanItemState
from gitlab_radar.schemas.technology import PackageManager
from gitlab_radar.services.application_parameters import application_parameter_values
from gitlab_radar.services.company_rules import apply_company_compliance, load_company_requirements
from gitlab_radar.services.frameworks import detected_framework_codes
from gitlab_radar.services.programming_languages import oldest_current_versions

__all__ = [
    'carry_forward_missing_projects',
    'clone_project',
    'delete_project_files',
    'delete_scan_files',
    'fail_pending_items',
    'find_reusable_inputs',
    'find_reusable_project',
    'invalidate_project_cache',
    'latest_published_scan',
    'latest_scan',
    'load_projects',
    'prepare_scan',
    'project_files',
    'recover_stale_scans',
    'restore_previous_analysis',
    'save_analysis',
    'save_collected_project',
    'skip_project',
    'sync_programming_languages',
    'trim_old_scans',
]

logger = logging.getLogger(__name__)


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


async def latest_data_scan() -> ScanRun | None:
    return await latest_scan()


async def load_projects(scan_id: int | None = None) -> list[Project]:
    scan = await latest_data_scan() if scan_id is None else await ScanRun.get_or_none(id=scan_id)
    if scan is None:
        return []
    if scan_id is not None or PROJECT_CACHE.scan_id != scan.id:
        requirements, parameter_values, language_versions, framework_rows = await asyncio.gather(
            load_company_requirements(),
            application_parameter_values(),
            oldest_current_versions(),
            ProgrammingFramework.filter(enabled=True, language__enabled=True)
            .prefetch_related('language')
            .order_by('name'),
        )
        projects = await _projects_for_scan(scan, current=scan_id is None)
        for project in projects:
            if (
                not project.is_empty
                and not project.subprojects
                and (not project.languages or any(language.code == 'python' for language in project.languages))
            ):
                project.subprojects.append(ProjectSubproject(path='.', package_manager=PackageManager.UNKNOWN))
            project.frameworks = _project_frameworks(project, framework_rows)
            apply_company_compliance(project, requirements, parameter_values, language_versions)
        projects.sort(
            key=lambda project: (
                project.data_status is not ProjectDataStatus.CURRENT,
                project.scanned_at is None,
                project.scanned_at,
                project.id,
            ),
        )
        if scan_id is not None:
            return projects
        PROJECT_CACHE.scan_id = scan.id
        PROJECT_CACHE.projects = projects
        logger.info('Снимок %d загружен из PostgreSQL: проектов %d', scan.id, len(projects))
    return [project.model_copy(deep=True) for project in PROJECT_CACHE.projects]


async def _projects_for_scan(scan: ScanRun, *, current: bool) -> list[Project]:
    items = await ScanItem.filter(scan_id=scan.id).select_related('result', 'fallback_result', 'target').order_by('id')
    projects = [project for item in items if (project := _item_project(item)) is not None]
    if current:
        target_ids = [item.target_id for item in items]
        targets = (
            await ScanTarget.filter(is_default=True)
            .exclude(id__in=target_ids)
            .select_related(
                'last_completed_item',
                'last_completed_item__result',
                'last_completed_item__fallback_result',
                'last_successful_result',
            )
        )
        for target in targets:
            project = None
            if target.last_completed_item is not None:
                project = _item_project(target.last_completed_item)
            elif target.last_successful_result is not None:
                project = Project.model_validate(
                    _result_payload(target.successful_metadata, target.last_successful_result)
                )
            if project is not None:
                project.data_status = ProjectDataStatus.MISSING if scan.published else ProjectDataStatus.STALE
                projects.append(project)
    return projects


def _item_project(item: ScanItem) -> Project | None:
    fallback = item.state in {
        ScanItemState.PENDING,
        ScanItemState.COLLECTED,
        ScanItemState.FAILED,
        ScanItemState.SKIPPED,
    }
    result = (item.fallback_result or item.result) if fallback else item.result
    metadata = item.fallback_metadata if fallback and item.fallback_result_id else item.metadata
    if result is None and item.state in {ScanItemState.PENDING, ScanItemState.COLLECTED}:
        return None
    payload = _result_payload(metadata, result)
    if fallback:
        payload['data_status'] = ProjectDataStatus.STALE
        payload['scan_error'] = item.error
        if item.state == ScanItemState.FAILED:
            payload['analysis_status'] = ProjectAnalysisStatus.FAILED
        if item.result is not None:
            payload['analysis_status'] = item.result.status
            payload['analysis_diagnostics'] = item.result.payload.get('analysis_diagnostics', [])
    else:
        if item.error:
            payload['scan_error'] = item.error
        payload['scanned_at'] = item.scanned_at
        payload['data_status'] = (
            ProjectDataStatus.MISSING if item.state == ScanItemState.MISSING else ProjectDataStatus.CURRENT
        )
    return Project.model_validate(payload)


def _result_payload(metadata: dict, result: AnalysisResult | None) -> dict:
    payload = dict(result.payload) if result else {}
    payload.update(metadata)
    payload['languages'] = _project_languages(metadata, result.payload if result else {})
    return payload


def _project_languages(metadata: dict, payload: dict) -> list[dict]:
    analysis = {language['code']: language for language in payload.get('languages', [])}
    return [
        {**language, **analysis.get(language['code'], {}), 'percentage': language.get('percentage', 0)}
        for language in metadata.get('languages', [])
    ]


def invalidate_project_cache() -> None:
    PROJECT_CACHE.invalidate()


def _project_frameworks(
    project: Project,
    frameworks: list[ProgrammingFramework],
) -> list[ProjectFramework]:
    detected_codes = detected_framework_codes(project, frameworks)
    return [
        ProjectFramework(
            code=framework.code,
            name=framework.name,
            language=framework.language.name,
        )
        for framework in frameworks
        if framework.code in detected_codes
    ]
