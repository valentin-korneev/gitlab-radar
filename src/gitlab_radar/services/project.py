from gitlab_radar.database.repository import load_projects as load_projects_from_database
from gitlab_radar.schemas.project import Project
from gitlab_radar.services.project_blacklist import blacklist_patterns, project_is_blacklisted
from gitlab_radar.services.visibility import filter_projects_for_user


async def load_projects(
    preferred_username: str | None = None,
    visibility_group: str | None = None,
    *,
    scan_id: int | None = None,
) -> list[Project]:
    projects = await load_projects_from_database(scan_id=scan_id)
    blacklist = await blacklist_patterns()
    projects = [project for project in projects if not project_is_blacklisted(project.path_with_namespace, blacklist)]
    return await filter_projects_for_user(projects, preferred_username, visibility_group)
