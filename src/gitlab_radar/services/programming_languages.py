from gitlab_radar.database.models import ProgrammingLanguage


JAVASCRIPT_TYPESCRIPT_CODES = frozenset({'javascript', 'typescript'})


def canonical_language_code(code: str) -> str:
    return 'javascript' if code in JAVASCRIPT_TYPESCRIPT_CODES else code


def language_display_name(code: str, name: str | None = None) -> str:
    if code in JAVASCRIPT_TYPESCRIPT_CODES:
        return 'JS / TS'
    return name or code


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
