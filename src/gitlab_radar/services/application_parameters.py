from gitlab_radar.database.models import ApplicationParameter


async def application_parameter_values() -> dict[str, str]:
    rows = await ApplicationParameter.all().values('key', 'value')
    return {str(row['key']): str(row['value']) for row in rows}
