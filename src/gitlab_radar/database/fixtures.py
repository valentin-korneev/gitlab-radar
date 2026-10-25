import logging
from pathlib import Path

import yaml

from gitlab_radar.database.models import (
    ApplicationParameter,
    CompanyRequirement,
    CompanyRequirementGroup,
    DataFixture,
)
from gitlab_radar.schemas.application_parameter import ApplicationParameter as ApplicationParameterSchema
from gitlab_radar.schemas.company_requirement import CompanyRequirementCreate, CompanyRequirementGroupCreate

logger = logging.getLogger(__name__)
FIXTURES_DIR = Path(__file__).parent.parent / 'fixtures'


async def load_database_fixtures() -> None:
    await _load_application_parameters()
    fixture_name = 'company-requirements'
    if await DataFixture.filter(name=fixture_name).exists():
        return

    groups = [
        CompanyRequirementGroupCreate.model_validate(item)
        for item in _read_fixture('company_requirement_groups.yaml')
    ]
    groups_by_name: dict[str, CompanyRequirementGroup] = {}
    for group in groups:
        row = await CompanyRequirementGroup.create(
            name=group.name,
            description=group.description,
            sort_order=group.sort_order,
        )
        groups_by_name[row.name] = row

    requirement_payloads = _read_fixture('company_requirements.yaml')
    requirements = [_requirement_from_fixture(item, groups_by_name) for item in requirement_payloads]
    await CompanyRequirement.bulk_create(
        [
            CompanyRequirement(
                **requirement.model_dump(mode='json', exclude={'sort_order'}),
                sort_order=requirement.sort_order or index,
            )
            for index, requirement in enumerate(requirements, start=1)
        ],
    )
    logger.info('Загружены fixtures требований компании: %d', len(requirements))
    await DataFixture.create(name=fixture_name)


async def _load_application_parameters() -> None:
    fixture_name = 'application-parameters'
    if await DataFixture.filter(name=fixture_name).exists():
        return
    parameters = [
        ApplicationParameterSchema.model_validate(item)
        for item in _read_fixture('application_parameters.yaml')
    ]
    await ApplicationParameter.bulk_create(
        [ApplicationParameter(**parameter.model_dump(mode='json')) for parameter in parameters],
    )
    await DataFixture.create(name=fixture_name)


def _read_fixture(filename: str) -> list[dict]:
    return yaml.safe_load((FIXTURES_DIR / filename).read_text(encoding='utf-8')) or []


def _requirement_from_fixture(
    item: dict,
    groups_by_name: dict[str, CompanyRequirementGroup],
) -> CompanyRequirementCreate:
    payload = dict(item)
    group_name = str(payload.pop('group'))
    payload['group_id'] = groups_by_name[group_name].id
    return CompanyRequirementCreate.model_validate(payload)
