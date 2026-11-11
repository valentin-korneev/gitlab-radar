from fastapi import APIRouter, Depends, HTTPException
from tortoise.exceptions import IntegrityError

from gitlab_radar.auth import management_access_dependency
from gitlab_radar.database.models import ProjectBlacklistRule as ProjectBlacklistRuleModel
from gitlab_radar.schemas.project_blacklist import ProjectBlacklistRule, ProjectBlacklistRulePayload

router = APIRouter(dependencies=[Depends(management_access_dependency)])


@router.get('/')
async def get_project_blacklist() -> list[ProjectBlacklistRule]:
    rows = await ProjectBlacklistRuleModel.all().order_by('id')
    return [ProjectBlacklistRule(id=row.id, pattern=row.pattern) for row in rows]


@router.post('/', status_code=201)
async def create_project_blacklist_rule(payload: ProjectBlacklistRulePayload) -> ProjectBlacklistRule:
    try:
        row = await ProjectBlacklistRuleModel.create(pattern=payload.pattern)
    except IntegrityError as error:
        raise HTTPException(status_code=409, detail='Такой шаблон уже добавлен') from error
    return ProjectBlacklistRule(id=row.id, pattern=row.pattern)


@router.put('/{rule_id}')
async def update_project_blacklist_rule(
    rule_id: int,
    payload: ProjectBlacklistRulePayload,
) -> ProjectBlacklistRule:
    row = await ProjectBlacklistRuleModel.get_or_none(id=rule_id)
    if row is None:
        raise HTTPException(status_code=404, detail='Правило чёрного списка не найдено')
    row.pattern = payload.pattern
    try:
        await row.save(update_fields=['pattern'])
    except IntegrityError as error:
        raise HTTPException(status_code=409, detail='Такой шаблон уже добавлен') from error
    return ProjectBlacklistRule(id=row.id, pattern=row.pattern)


@router.delete('/{rule_id}', status_code=204)
async def delete_project_blacklist_rule(rule_id: int) -> None:
    deleted = await ProjectBlacklistRuleModel.filter(id=rule_id).delete()
    if not deleted:
        raise HTTPException(status_code=404, detail='Правило чёрного списка не найдено')
