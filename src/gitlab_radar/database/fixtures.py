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
        await _load_python_version_requirement()
        return

    groups = [
        CompanyRequirementGroupCreate.model_validate(item) for item in _read_fixture('company_requirement_groups.yaml')
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
    await _load_python_version_requirement()


async def _load_python_version_requirement() -> None:
    fixture_name = 'company-requirement-python-version-inclusive'
    if await DataFixture.filter(name=fixture_name).exists():
        return

    requirement_item = next(
        item for item in _read_fixture('company_requirements.yaml') if item['code'] == 'python-version-current'
    )
    group_name = str(requirement_item['group'])
    group_item = next(
        item for item in _read_fixture('company_requirement_groups.yaml') if item['name'] == group_name
    )
    group, _ = await CompanyRequirementGroup.get_or_create(
        name=group_name,
        defaults={
            'description': group_item.get('description', ''),
            'sort_order': group_item.get('sort_order', 0),
        },
    )
    requirement = _requirement_from_fixture(
        requirement_item,
        {group_name: group},
    )
    row = await CompanyRequirement.get_or_none(code=requirement.code)
    if row is None:
        await CompanyRequirement.create(**requirement.model_dump(mode='json'))
        logger.info('Загружен fixture требования компании: %s', requirement.code)
    elif _migrate_python_version_operator(row.condition):
        await row.save(update_fields=['condition'])
        logger.info('Обновлен оператор fixture требования компании: %s', requirement.code)
    await DataFixture.create(name=fixture_name)


def _migrate_python_version_operator(node: dict) -> bool:
    changed = False
    if node.get('source') == 'python_version' and node.get('operator') == 'greater_than':
        node['operator'] = 'greater_than_or_equal'
        changed = True
    for item in node.get('items', []):
        if isinstance(item, dict):
            changed = _migrate_python_version_operator(item) or changed
    return changed


async def _load_application_parameters() -> None:
    fixture_name = 'application-parameters'
    if await DataFixture.filter(name=fixture_name).exists():
        return
    parameters = [
        ApplicationParameterSchema.model_validate(item) for item in _read_fixture('application_parameters.yaml')
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
