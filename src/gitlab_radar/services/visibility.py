from collections.abc import Iterable
from fnmatch import fnmatchcase

from tortoise.transactions import in_transaction

from gitlab_radar.database.models import (
    AdminUserVisibilityRule,
    AdminVisibilityPolicyAssignment,
    AdminVisibilityPolicyRule,
    AuthorizedUser,
    UserVisibilityGroup,
    UserVisibilityRule,
)
from gitlab_radar.schemas.project import Project
from gitlab_radar.schemas.visibility import VisibilityRulePayload


def apply_visibility_rules(
    projects: list[Project],
    rules: Iterable[VisibilityRulePayload | UserVisibilityRule | AdminVisibilityPolicyRule | AdminUserVisibilityRule],
) -> list[Project]:
    rule_list = list(rules)
    includes = [rule.pattern for rule in rule_list if rule.action == 'include']
    excludes = [rule.pattern for rule in rule_list if rule.action == 'exclude']
    selected = (
        [project for project in projects if any(_matches(project.path_with_namespace, pattern) for pattern in includes)]
        if includes
        else list(projects)
    )
    return [
        project
        for project in selected
        if not any(_matches(project.path_with_namespace, pattern) for pattern in excludes)
    ]


async def filter_projects_for_user(
    projects: list[Project],
    preferred_username: str | None,
    visibility_group: str | None = None,
) -> list[Project]:
    if not preferred_username:
        return projects
    user = await AuthorizedUser.filter(preferred_username=preferred_username).first()
    if user is None:
        return projects

    all_projects = projects
    assignments = await AdminVisibilityPolicyAssignment.filter(user_id=preferred_username).values_list(
        'policy_id', flat=True
    )
    if assignments:
        policy_projects: dict[int, Project] = {}
        for policy_id in assignments:
            rules = await AdminVisibilityPolicyRule.filter(policy_id=policy_id).order_by('sort_order', 'id')
            policy_projects.update({project.id: project for project in apply_visibility_rules(all_projects, rules)})
        projects = [project for project in all_projects if project.id in policy_projects]

    admin_rules = await AdminUserVisibilityRule.filter(user_id=preferred_username).order_by('sort_order', 'id')
    if assignments:
        include_patterns = [rule.pattern for rule in admin_rules if rule.action == 'include']
        exclude_patterns = [rule.pattern for rule in admin_rules if rule.action == 'exclude']
        selected_ids = {project.id for project in projects}
        selected_ids.update(
            project.id
            for project in all_projects
            if any(_matches(project.path_with_namespace, pattern) for pattern in include_patterns)
        )
        projects = [
            project
            for project in all_projects
            if project.id in selected_ids
            and not any(_matches(project.path_with_namespace, pattern) for pattern in exclude_patterns)
        ]
    else:
        projects = apply_visibility_rules(all_projects, admin_rules)
    selected_group = None
    if visibility_group != 'all':
        if visibility_group and visibility_group.isdigit():
            selected_group = await UserVisibilityGroup.filter(
                id=int(visibility_group), user_id=preferred_username
            ).first()
        if selected_group is None and visibility_group is None:
            selected_group = (
                await UserVisibilityGroup.filter(user_id=preferred_username, is_active=True).order_by('id').first()
            )
    if selected_group is not None:
        user_rules = await UserVisibilityRule.filter(group_id=selected_group.id).order_by('sort_order', 'id')
        projects = apply_visibility_rules(projects, user_rules)
    return projects


async def replace_user_group_rules(group_id: int, rules: list[VisibilityRulePayload], connection: object) -> None:
    await UserVisibilityRule.filter(group_id=group_id).using_db(connection).delete()
    rows = [
        UserVisibilityRule(group_id=group_id, action=rule.action, pattern=rule.pattern, sort_order=index)
        for index, rule in enumerate(rules)
    ]
    if rows:
        await UserVisibilityRule.bulk_create(rows, using_db=connection)


async def replace_policy_rules(policy_id: int, rules: list[VisibilityRulePayload], connection: object) -> None:
    await AdminVisibilityPolicyRule.filter(policy_id=policy_id).using_db(connection).delete()
    rows = [
        AdminVisibilityPolicyRule(policy_id=policy_id, action=rule.action, pattern=rule.pattern, sort_order=index)
        for index, rule in enumerate(rules)
    ]
    if rows:
        await AdminVisibilityPolicyRule.bulk_create(rows, using_db=connection)


async def replace_admin_user_visibility(
    preferred_username: str,
    policy_ids: list[int],
    rules: list[VisibilityRulePayload],
) -> None:
    async with in_transaction() as connection:
        await AdminVisibilityPolicyAssignment.filter(user_id=preferred_username).using_db(connection).delete()
        await AdminUserVisibilityRule.filter(user_id=preferred_username).using_db(connection).delete()
        assignments = [
            AdminVisibilityPolicyAssignment(user_id=preferred_username, policy_id=policy_id)
            for policy_id in dict.fromkeys(policy_ids)
        ]
        if assignments:
            await AdminVisibilityPolicyAssignment.bulk_create(assignments, using_db=connection)
        user_rules = [
            AdminUserVisibilityRule(
                user_id=preferred_username,
                action=rule.action,
                pattern=rule.pattern,
                sort_order=index,
            )
            for index, rule in enumerate(rules)
        ]
        if user_rules:
            await AdminUserVisibilityRule.bulk_create(user_rules, using_db=connection)


def _matches(path: str, pattern: str) -> bool:
    return fnmatchcase(path.casefold(), pattern.casefold())
