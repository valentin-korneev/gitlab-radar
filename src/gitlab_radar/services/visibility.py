from fnmatch import fnmatchcase
lazy from collections.abc import Iterable

from tortoise.transactions import in_transaction

from gitlab_radar.database.models import (
    AdminUserVisibilityRule,
    AdminVisibilityPolicyAssignment,
    AdminVisibilityPolicyRule,
    AuthorizedUser,
    UserVisibilityGroup,
    UserVisibilityRule,
)
from gitlab_radar.services.programming_languages import canonical_language_code
lazy from gitlab_radar.schemas.project import Project
lazy from gitlab_radar.schemas.visibility import VisibilityRulePayload


def apply_visibility_rules(
    projects: list[Project],
    rules: Iterable[VisibilityRulePayload | UserVisibilityRule | AdminVisibilityPolicyRule | AdminUserVisibilityRule],
) -> list[Project]:
    rule_list = list(rules)
    selected = list(projects)
    for target in ('path', 'language'):
        target_rules = [rule for rule in rule_list if rule.target == target]
        includes = [rule for rule in target_rules if rule.action == 'include']
        excludes = [rule for rule in target_rules if rule.action == 'exclude']
        if includes:
            selected = [project for project in selected if any(_matches_rule(project, rule) for rule in includes)]
        if excludes:
            selected = [
                project for project in selected if not any(_matches_rule(project, rule) for rule in excludes)
            ]
    return selected


def _matches_rule(
    project: Project,
    rule: VisibilityRulePayload | UserVisibilityRule | AdminVisibilityPolicyRule | AdminUserVisibilityRule,
) -> bool:
    if rule.target == 'language':
        pattern = canonical_language_code(rule.pattern)
        return any(_matches(canonical_language_code(language.code), pattern) for language in project.languages)
    return _matches(project.path_with_namespace, rule.pattern)


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
    admin_rules_query = AdminUserVisibilityRule.filter(user_id=preferred_username)
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
    has_user_rules = (
        selected_group is not None
        and await UserVisibilityRule.filter(group_id=selected_group.id).exists()
    )
    has_admin_rules = await admin_rules_query.exists()
    if not assignments and not has_admin_rules and not has_user_rules:
        return projects

    if assignments:
        policy_projects: dict[int, Project] = {}
        for policy_id in assignments:
            policy_rules_query = AdminVisibilityPolicyRule.filter(policy_id=policy_id)
            rules = (
                await policy_rules_query.order_by('sort_order', 'id')
                if await policy_rules_query.exists()
                else []
            )
            policy_projects.update({project.id: project for project in apply_visibility_rules(all_projects, rules)})
        projects = [project for project in all_projects if project.id in policy_projects]

    admin_rules = await admin_rules_query.order_by('sort_order', 'id') if has_admin_rules else []
    if assignments:
        include_rules = [rule for rule in admin_rules if rule.action == 'include']
        exclude_rules = [rule for rule in admin_rules if rule.action == 'exclude']
        selected_ids = {project.id for project in projects}
        selected_ids.update(
            project.id
            for project in all_projects
            if any(_matches_rule(project, rule) for rule in include_rules)
        )
        projects = [
            project
            for project in all_projects
            if project.id in selected_ids
            and not any(_matches_rule(project, rule) for rule in exclude_rules)
        ]
    else:
        projects = apply_visibility_rules(all_projects, admin_rules)
    if selected_group is not None and has_user_rules:
        user_rules = await UserVisibilityRule.filter(group_id=selected_group.id).order_by('sort_order', 'id')
        projects = apply_visibility_rules(projects, user_rules)
    return projects


async def replace_user_group_rules(group_id: int, rules: list[VisibilityRulePayload], connection: object) -> None:
    await UserVisibilityRule.filter(group_id=group_id).using_db(connection).delete()
    rows = [
        UserVisibilityRule(
            group_id=group_id,
            action=rule.action,
            target=rule.target,
            pattern=rule.pattern,
            sort_order=index,
        )
        for index, rule in enumerate(rules)
    ]
    if rows:
        await UserVisibilityRule.bulk_create(rows, using_db=connection)


async def replace_policy_rules(policy_id: int, rules: list[VisibilityRulePayload], connection: object) -> None:
    await AdminVisibilityPolicyRule.filter(policy_id=policy_id).using_db(connection).delete()
    rows = [
        AdminVisibilityPolicyRule(
            policy_id=policy_id,
            action=rule.action,
            target=rule.target,
            pattern=rule.pattern,
            sort_order=index,
        )
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
                target=rule.target,
                pattern=rule.pattern,
                sort_order=index,
            )
            for index, rule in enumerate(rules)
        ]
        if user_rules:
            await AdminUserVisibilityRule.bulk_create(user_rules, using_db=connection)


def _matches(path: str, pattern: str) -> bool:
    return fnmatchcase(path.casefold(), pattern.casefold())
