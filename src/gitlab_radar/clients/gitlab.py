from typing import Self

import gitlab

from gitlab_radar.config import settings

gitlab_client = gitlab.Gitlab(
    url=settings.gitlab.url,
    private_token=settings.gitlab.private_token.get_secret_value(),
)


class GitLabRequestCounter:
    def __init__(self) -> None:
        self.count = 0

    def __enter__(self) -> Self:
        gitlab_client.session.hooks.setdefault('response', []).append(self._count)
        return self

    def __exit__(self, *_: object) -> None:
        hooks = gitlab_client.session.hooks.get('response', [])
        if self._count in hooks:
            hooks.remove(self._count)

    def _count(self, response: object, **_: object) -> object:
        self.count += 1
        return response
