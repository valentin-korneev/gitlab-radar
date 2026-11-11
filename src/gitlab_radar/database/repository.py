import asyncio
import logging
from datetime import UTC, datetime

from tortoise.transactions import in_transaction

from gitlab_radar.database.models import (
    LanguagePackageManager,
    ModulePackageManager,
    PackageManagerCatalog,
    ProgrammingFramework,
    ProgrammingLanguage,
    ProjectFile,
    ProjectFileUsage,
    ProjectModule,
    ProjectSnapshot,
    ProjectSnapshotLanguage,
    ScanRun,
)
from gitlab_radar.schemas.project import Project, ProjectFramework, ProjectLanguage, ProjectSubproject
from gitlab_radar.schemas.technology import PackageManager
from gitlab_radar.services.analysis import FileSelection, analyzer_for
from gitlab_radar.services.application_parameters import application_parameter_values
from gitlab_radar.services.company_rules import apply_company_compliance, load_company_requirements
from gitlab_radar.services.programming_languages import oldest_current_versions

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


async def latest_data_scan() -> ScanRun | None:
    scan = await latest_scan()
    if scan is not None:
        if scan.state == 'running':
            return scan
        if scan.state == 'failed' and await ProjectSnapshot.filter(scan_id=scan.id, analyzed=True).exists():
            return scan
    return await latest_published_scan()


async def load_projects() -> list[Project]:
    scan = await latest_data_scan()
    if scan is None:
        return []
    if PROJECT_CACHE.scan_id != scan.id:
        requirements, parameter_values, language_versions, framework_rows = await asyncio.gather(
            load_company_requirements(),
            application_parameter_values(),
            oldest_current_versions(),
            ProgrammingFramework.filter(enabled=True, language__enabled=True)
            .prefetch_related('language')
            .order_by('name'),
        )
        snapshots = ProjectSnapshot.filter(scan_id=scan.id)
        if not scan.published:
            snapshots = snapshots.filter(analyzed=True)
        rows = await snapshots.order_by('gitlab_id').values_list('payload', flat=True)
        projects = [Project.model_validate(payload) for payload in rows]
        for project in projects:
            if not project.is_empty and not project.subprojects and (
                not project.languages or any(language.code == 'python' for language in project.languages)
            ):
                project.subprojects.append(ProjectSubproject(path='.', package_manager=PackageManager.UNKNOWN))
            project.frameworks = _project_frameworks(project, framework_rows)
            apply_company_compliance(project, requirements, parameter_values, language_versions)
        PROJECT_CACHE.scan_id = scan.id
        PROJECT_CACHE.projects = projects
        logger.info('Снимок %d загружен из PostgreSQL: проектов %d', scan.id, len(projects))
    return [project.model_copy(deep=True) for project in PROJECT_CACHE.projects]


def invalidate_project_cache() -> None:
    PROJECT_CACHE.invalidate()


def _project_frameworks(
    project: Project,
    frameworks: list[ProgrammingFramework],
) -> list[ProjectFramework]:
    result: list[ProjectFramework] = []
    for framework in frameworks:
        expected_dependencies = {str(name).casefold() for name in framework.dependency_names}
        detected = any(
            subproject.language == framework.language.code
            and bool(expected_dependencies & _subproject_dependency_names(subproject))
            for subproject in project.subprojects
        )
        if detected:
            result.append(
                ProjectFramework(
                    code=framework.code,
                    name=framework.name,
                    language=framework.language.name,
                ),
            )
    return result


def _subproject_dependency_names(subproject: ProjectSubproject) -> set[str]:
    dependencies = [
        *subproject.dependencies,
        *subproject.transitive_dependencies,
        *(dependency for group in subproject.optional_dependencies for dependency in group.dependencies),
    ]
    return {dependency.name.casefold() for dependency in dependencies}


async def find_reusable_project(
    gitlab_id: int,
    revision: str | None,
    analysis_fingerprint: str,
) -> ProjectSnapshot | None:
    if not revision:
        return None
    return (
        await ProjectSnapshot.filter(
            gitlab_id=gitlab_id,
            revision=revision,
            analysis_fingerprint=analysis_fingerprint,
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
    analysis_fingerprint: str,
) -> ProjectSnapshot:
    payload = dict(source.payload)
    payload.update(
        project.model_dump(
            mode='json',
            include=REUSED_PROJECT_METADATA_FIELDS,
        ),
    )
    snapshot = await ProjectSnapshot.create(
        scan=scan,
        gitlab_id=project.id,
        revision=source.revision,
        analysis_fingerprint=analysis_fingerprint,
        payload=payload,
        collected=True,
        analyzed=True,
        reused=True,
    )
    await _clone_language_analysis(source.id, snapshot.id)
    invalidate_project_cache()
    return snapshot


async def save_collected_project(
    scan: ScanRun,
    project: Project,
    revision: str | None,
    files: dict[str, str],
    selections: list[FileSelection],
    analysis_fingerprint: str,
    error: str | None = None,
) -> ProjectSnapshot:
    languages = await sync_programming_languages(project.languages)
    async with in_transaction() as connection:
        snapshot = await ProjectSnapshot.create(
            scan=scan,
            gitlab_id=project.id,
            revision=revision,
            analysis_fingerprint=analysis_fingerprint,
            payload=_project_payload(project),
            collected=error is None,
            error=error,
            using_db=connection,
        )
        snapshot_languages: dict[str, ProjectSnapshotLanguage] = {}
        for item in project.languages:
            snapshot_languages[item.code] = await ProjectSnapshotLanguage.create(
                project=snapshot,
                language=languages[item.code],
                percentage=item.percentage,
                analysis_status=item.analysis_status,
                analyzer_version=item.analyzer_version,
                error=item.error,
                using_db=connection,
            )
        selections_by_path: dict[str, list[FileSelection]] = {}
        for selection in selections:
            selections_by_path.setdefault(selection.path, []).append(selection)
        for path, content in files.items():
            project_file = await ProjectFile.create(
                project=snapshot,
                path=path,
                content=content,
                using_db=connection,
            )
            usages = [
                ProjectFileUsage(
                    file=project_file,
                    project_language=snapshot_languages.get(selection.language_code),
                    analyzer_key=selection.analyzer_key,
                    role=selection.role,
                )
                for selection in selections_by_path.get(path, [])
            ]
            if usages:
                await ProjectFileUsage.bulk_create(usages, using_db=connection)
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
    await _save_language_analysis(snapshot_id, project)
    payload = _project_payload(project)
    await ProjectSnapshot.filter(id=snapshot_id).update(
        payload=payload,
        analyzed=error is None,
        error=error,
    )
    invalidate_project_cache()


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
    await _restore_language_analysis(source.id, snapshot_id)
    invalidate_project_cache()
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


async def sync_programming_languages(
    languages: list[ProjectLanguage],
) -> dict[str, ProgrammingLanguage]:
    result: dict[str, ProgrammingLanguage] = {}
    for item in languages:
        row, _ = await ProgrammingLanguage.get_or_create(
            code=item.code,
            defaults={
                'name': item.name,
                'enabled': analyzer_for(item.code) is not None,
            },
        )
        if row.name != item.name:
            row.name = item.name
            await row.save(update_fields=['name'])
        analyzer = analyzer_for(item.code)
        if analyzer is not None:
            for manager_code in analyzer.package_manager_codes:
                manager, _ = await PackageManagerCatalog.get_or_create(
                    code=manager_code,
                    defaults={'name': manager_code},
                )
                await LanguagePackageManager.get_or_create(
                    language=row,
                    package_manager=manager,
                )
        result[item.code] = row
    return result


async def _save_language_analysis(snapshot_id: int, project: Project) -> None:
    rows = await ProjectSnapshotLanguage.filter(project_id=snapshot_id).prefetch_related('language')
    rows_by_code = {row.language.code: row for row in rows}
    await ProjectModule.filter(project_language__project_id=snapshot_id).delete()
    for language in project.languages:
        row = rows_by_code.get(language.code)
        if row is None:
            continue
        row.analysis_status = language.analysis_status
        row.analyzer_version = language.analyzer_version
        row.error = language.error
        await row.save(update_fields=['analysis_status', 'analyzer_version', 'error'])
    for subproject in project.subprojects:
        language_row = rows_by_code.get(subproject.language)
        if language_row is None:
            continue
        module = await ProjectModule.create(
            project_language=language_row,
            path=subproject.path,
            payload=subproject.model_dump(mode='json'),
        )
        if subproject.package_manager not in {PackageManager.UNKNOWN, PackageManager.MIXED}:
            manager, _ = await PackageManagerCatalog.get_or_create(
                code=subproject.package_manager.value,
                defaults={'name': subproject.package_manager.value},
            )
            await LanguagePackageManager.get_or_create(
                language_id=language_row.language_id,
                package_manager=manager,
            )
            await ModulePackageManager.create(module=module, package_manager=manager)


async def _clone_language_analysis(source_id: int, target_id: int) -> None:
    source_languages = await ProjectSnapshotLanguage.filter(project_id=source_id)
    target_languages: dict[int, ProjectSnapshotLanguage] = {}
    for source_language in source_languages:
        target_languages[source_language.id] = await ProjectSnapshotLanguage.create(
            project_id=target_id,
            language_id=source_language.language_id,
            percentage=source_language.percentage,
            analysis_status=source_language.analysis_status,
            analyzer_version=source_language.analyzer_version,
            error=source_language.error,
        )
    source_modules = await ProjectModule.filter(project_language__project_id=source_id)
    target_modules: dict[int, ProjectModule] = {}
    for source_module in source_modules:
        target_modules[source_module.id] = await ProjectModule.create(
            project_language=target_languages[source_module.project_language_id],
            path=source_module.path,
            payload=source_module.payload,
        )
    manager_links = (
        await ModulePackageManager.filter(module_id__in=list(target_modules)).values(
            'module_id',
            'package_manager_id',
        )
        if target_modules
        else []
    )
    cloned_manager_links = [
        ModulePackageManager(
            module=target_modules[int(link['module_id'])],
            package_manager_id=int(link['package_manager_id']),
        )
        for link in manager_links
    ]
    if cloned_manager_links:
        await ModulePackageManager.bulk_create(cloned_manager_links)


async def _restore_language_analysis(source_id: int, target_id: int) -> None:
    source_languages = await ProjectSnapshotLanguage.filter(project_id=source_id)
    target_languages = await ProjectSnapshotLanguage.filter(project_id=target_id)
    target_by_language = {row.language_id: row for row in target_languages}
    await ProjectModule.filter(project_language__project_id=target_id).delete()
    source_to_target: dict[int, ProjectSnapshotLanguage] = {}
    for source_language in source_languages:
        target = target_by_language.get(source_language.language_id)
        if target is None:
            continue
        target.analysis_status = source_language.analysis_status
        target.analyzer_version = source_language.analyzer_version
        target.error = source_language.error
        await target.save(update_fields=['analysis_status', 'analyzer_version', 'error'])
        source_to_target[source_language.id] = target
    source_modules = await ProjectModule.filter(project_language__project_id=source_id)
    target_modules: dict[int, ProjectModule] = {}
    for source_module in source_modules:
        target_language = source_to_target.get(source_module.project_language_id)
        if target_language is not None:
            target_modules[source_module.id] = await ProjectModule.create(
                project_language=target_language,
                path=source_module.path,
                payload=source_module.payload,
            )
    manager_links = (
        await ModulePackageManager.filter(module_id__in=list(target_modules)).values(
            'module_id',
            'package_manager_id',
        )
        if target_modules
        else []
    )
    restored_manager_links = [
        ModulePackageManager(
            module=target_modules[int(link['module_id'])],
            package_manager_id=int(link['package_manager_id']),
        )
        for link in manager_links
    ]
    if restored_manager_links:
        await ModulePackageManager.bulk_create(restored_manager_links)
