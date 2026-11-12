from collections import Counter

from fastapi import APIRouter, Depends, HTTPException

from gitlab_radar.auth import management_access_dependency
from gitlab_radar.database.models import ProgrammingFramework as ProgrammingFrameworkModel
from gitlab_radar.database.models import ProgrammingLanguage as ProgrammingLanguageModel
from gitlab_radar.database.repository import invalidate_project_cache
from gitlab_radar.schemas.programming_language import (
    ProgrammingFramework,
    ProgrammingFrameworkEnabled,
    ProgrammingLanguage,
    ProgrammingLanguageEnabled,
    ProgrammingLanguageVersion,
)
from gitlab_radar.services.analysis import analyzer_for
from gitlab_radar.services.dashboard import invalidate_dashboard_cache
from gitlab_radar.services.programming_languages import JAVASCRIPT_TYPESCRIPT_CODES
from gitlab_radar.services.project import load_projects

router = APIRouter()


@router.get('/')
async def get_programming_languages() -> list[ProgrammingLanguage]:
    rows = await ProgrammingLanguageModel.all()
    projects = await load_projects()
    project_counts = Counter(
        language.code
        for project in projects
        for language in {item.code: item for item in project.languages}.values()
    )
    framework_counts = Counter(
        await ProgrammingFrameworkModel.all().values_list('language_id', flat=True)
    )
    rows.sort(
        key=lambda row: (
            -project_counts[row.code],
            -framework_counts[row.id],
            row.name.casefold(),
        ),
    )
    return [_serialize(row) for row in rows]


@router.get('/frameworks')
async def get_programming_frameworks() -> list[ProgrammingFramework]:
    rows = await ProgrammingFrameworkModel.all().prefetch_related('language')
    rows.sort(key=lambda row: (row.language.name.casefold(), row.name.casefold()))
    return [_serialize_framework(row) for row in rows]


@router.patch('/frameworks/{framework_id}/enabled', dependencies=[Depends(management_access_dependency)])
async def set_programming_framework_enabled(
    framework_id: int,
    payload: ProgrammingFrameworkEnabled,
) -> ProgrammingFramework:
    row = await ProgrammingFrameworkModel.filter(id=framework_id).prefetch_related('language').first()
    if row is None:
        raise HTTPException(status_code=404, detail='Фреймворк не найден')
    row.enabled = payload.enabled
    await row.save(update_fields=['enabled'])
    invalidate_project_cache()
    invalidate_dashboard_cache()
    return _serialize_framework(row)


@router.patch('/{language_id}/enabled', dependencies=[Depends(management_access_dependency)])
async def set_programming_language_enabled(
    language_id: int,
    payload: ProgrammingLanguageEnabled,
) -> ProgrammingLanguage:
    row = await ProgrammingLanguageModel.get_or_none(id=language_id)
    if row is None:
        raise HTTPException(status_code=404, detail='Язык программирования не найден')
    language_codes = JAVASCRIPT_TYPESCRIPT_CODES if row.code in JAVASCRIPT_TYPESCRIPT_CODES else {row.code}
    await ProgrammingLanguageModel.filter(code__in=language_codes).update(enabled=payload.enabled)
    row.enabled = payload.enabled
    await row.save(update_fields=['enabled'])
    invalidate_project_cache()
    invalidate_dashboard_cache()
    return _serialize(row)


@router.patch('/{language_id}/oldest-current-version', dependencies=[Depends(management_access_dependency)])
async def set_programming_language_version(
    language_id: int,
    payload: ProgrammingLanguageVersion,
) -> ProgrammingLanguage:
    row = await ProgrammingLanguageModel.get_or_none(id=language_id)
    if row is None:
        raise HTTPException(status_code=404, detail='Язык программирования не найден')
    row.oldest_current_version = payload.oldest_current_version or None
    language_codes = JAVASCRIPT_TYPESCRIPT_CODES if row.code in JAVASCRIPT_TYPESCRIPT_CODES else {row.code}
    await ProgrammingLanguageModel.filter(code__in=language_codes).update(
        oldest_current_version=row.oldest_current_version,
    )
    invalidate_project_cache()
    invalidate_dashboard_cache()
    return _serialize(row)


def _serialize(row: ProgrammingLanguageModel) -> ProgrammingLanguage:
    analyzer = analyzer_for(row.code)
    return ProgrammingLanguage(
        id=row.id,
        code=row.code,
        name=row.name,
        enabled=row.enabled,
        oldest_current_version=row.oldest_current_version,
        analyzer_key=analyzer.key if analyzer is not None else None,
        analyzer_version=analyzer.version if analyzer is not None else None,
        package_managers=list(analyzer.package_manager_codes) if analyzer is not None else [],
    )


def _serialize_framework(row: ProgrammingFrameworkModel) -> ProgrammingFramework:
    return ProgrammingFramework(
        id=row.id,
        code=row.code,
        name=row.name,
        enabled=row.enabled,
        language_code=row.language.code,
        language_name=row.language.name,
        language_enabled=row.language.enabled,
        dependency_names=[str(name) for name in row.dependency_names],
    )
