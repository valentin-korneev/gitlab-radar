from gitlab_radar.database.models import ProgrammingLanguage


async def oldest_current_versions() -> dict[str, str]:
    rows = await ProgrammingLanguage.all().values(
        'code',
        'oldest_current_version',
    )
    return {
        str(row['code']): str(row['oldest_current_version'])
        for row in rows
        if row['oldest_current_version']
    }
