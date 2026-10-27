import re

from fastapi import APIRouter, Depends, HTTPException

from gitlab_radar.auth import management_access_dependency
from gitlab_radar.database.models import ApplicationParameter as ApplicationParameterModel
from gitlab_radar.database.repository import invalidate_project_cache
from gitlab_radar.schemas.application_parameter import (
    ApplicationParameter,
    ApplicationParameterUpdate,
    ParameterValueType,
)
from gitlab_radar.services.dashboard import invalidate_dashboard_cache

router = APIRouter()
VERSION_PATTERN = re.compile(r'^\d+\.\d+$')


@router.get('/')
async def get_parameters() -> list[ApplicationParameter]:
    rows = await ApplicationParameterModel.all().order_by('sort_order', 'key')
    return [ApplicationParameter.model_validate(row, from_attributes=True) for row in rows]


@router.put('/', dependencies=[Depends(management_access_dependency)])
async def update_parameters(payload: ApplicationParameterUpdate) -> list[ApplicationParameter]:
    rows = await ApplicationParameterModel.all().order_by('sort_order', 'key')
    rows_by_key = {row.key: row for row in rows}
    unknown_keys = payload.values.keys() - rows_by_key.keys()
    if unknown_keys:
        raise HTTPException(status_code=404, detail=f'Параметр не найден: {min(unknown_keys)}')
    for key, raw_value in payload.values.items():
        value = raw_value.strip()
        row = rows_by_key[key]
        _validate_value(row, value)
    for key, raw_value in payload.values.items():
        rows_by_key[key].value = raw_value.strip()
        await rows_by_key[key].save(update_fields=['value'])
    invalidate_dashboard_cache()
    invalidate_project_cache()
    return [ApplicationParameter.model_validate(row, from_attributes=True) for row in rows]


def _validate_value(row: ApplicationParameterModel, value: str) -> None:
    if row.value_type == ParameterValueType.VERSION:
        if not VERSION_PATTERN.fullmatch(value):
            raise HTTPException(status_code=422, detail='Версия должна быть указана в формате 3.11')
        return
    if row.value_type == ParameterValueType.INTEGER:
        try:
            number = int(value)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=f'«{row.title}» должно быть целым числом') from error
        if row.min_value is not None and number < row.min_value:
            raise HTTPException(status_code=422, detail=f'Минимальное значение «{row.title}»: {row.min_value}')
        if row.max_value is not None and number > row.max_value:
            raise HTTPException(status_code=422, detail=f'Максимальное значение «{row.title}»: {row.max_value}')
        return
    if row.value_type == ParameterValueType.PERCENTAGE_RANGE:
        try:
            lower, upper = (int(part) for part in value.split(',', maxsplit=1))
        except (ValueError, TypeError) as error:
            raise HTTPException(status_code=422, detail='Укажите две границы процентов') from error
        minimum = row.min_value if row.min_value is not None else 0
        maximum = row.max_value if row.max_value is not None else 100
        if not minimum <= lower < upper <= maximum:
            raise HTTPException(status_code=422, detail='Границы процентов должны идти по возрастанию')
