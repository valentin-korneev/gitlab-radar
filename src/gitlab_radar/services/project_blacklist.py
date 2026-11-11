from fnmatch import fnmatchcase
lazy from collections.abc import Iterable

from gitlab_radar.database.models import ProjectBlacklistRule


async def blacklist_patterns() -> list[str]:
    return list(await ProjectBlacklistRule.all().order_by('id').values_list('pattern', flat=True))


def project_is_blacklisted(path_with_namespace: str, patterns: Iterable[str]) -> bool:
    path = path_with_namespace.casefold()
    return any(fnmatchcase(path, pattern.casefold()) for pattern in patterns)
