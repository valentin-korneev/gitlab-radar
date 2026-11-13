lazy from tortoise.backends.base.client import BaseDBAsyncClient

from gitlab_radar.database.languages import sync_programming_languages
from gitlab_radar.database.models import (
    AnalysisResult,
    LanguagePackageManager,
    PackageManagerCatalog,
    ResultLanguage,
    ResultModule,
    ResultModulePackageManager,
    ScanItem,
)
from gitlab_radar.database.result_payload import analysis_payload, result_cache_key, result_identity
from gitlab_radar.schemas.project import Project, ProjectAnalysisStatus
from gitlab_radar.schemas.technology import PackageManager


async def create_result(item: ScanItem, project: Project, connection: BaseDBAsyncClient) -> AnalysisResult:
    key = None
    if project.analysis_status == ProjectAnalysisStatus.SUCCESS and item.input_digest:
        key = result_cache_key(project.id, item.input_digest, item.analysis_fingerprint)
    payload = analysis_payload(project)
    identity = result_identity(project.id, item.input_digest, item.analysis_fingerprint, payload)
    lookup = {'cache_key': key} if key else {'identity_key': identity}
    result, created = await AnalysisResult.get_or_create(
        **lookup,
        defaults={
            'gitlab_id': project.id,
            'source_revision': item.revision,
            'analysis_fingerprint': item.analysis_fingerprint,
            'input_digest': item.input_digest,
            'status': project.analysis_status,
            'payload': payload,
            'identity_key': identity,
            'cache_key': key,
        },
        using_db=connection,
    )
    if created:
        await _save_result_languages(result, project, connection)
    return result


async def _save_result_languages(result: AnalysisResult, project: Project, connection: BaseDBAsyncClient) -> None:
    languages = await sync_programming_languages(project.languages)
    rows = {}
    for language in project.languages:
        rows[language.code] = await ResultLanguage.create(
            result=result,
            language=languages[language.code],
            analysis_status=language.analysis_status,
            analyzer_version=language.analyzer_version,
            error=language.error,
            using_db=connection,
        )
    for subproject in project.subprojects:
        if subproject.language in rows:
            module = await ResultModule.create(
                result_language=rows[subproject.language],
                path=subproject.path,
                payload=subproject.model_dump(
                    mode='json', exclude={'company_compliance_percentage', 'company_rule_results'}
                ),
                using_db=connection,
            )
            await _save_module_manager(module, subproject.package_manager, connection)


async def _save_module_manager(
    module: ResultModule, manager_code: PackageManager, connection: BaseDBAsyncClient
) -> None:
    if manager_code in {PackageManager.UNKNOWN, PackageManager.MIXED}:
        return
    manager, _ = await PackageManagerCatalog.get_or_create(
        code=manager_code.value,
        defaults={'name': manager_code.value},
        using_db=connection,
    )
    await LanguagePackageManager.get_or_create(
        language_id=module.result_language.language_id,
        package_manager=manager,
        using_db=connection,
    )
    await ResultModulePackageManager.create(module=module, package_manager=manager, using_db=connection)
