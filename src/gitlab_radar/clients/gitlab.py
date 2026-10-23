import gitlab

from gitlab_radar.config import settings

gitlab_client = gitlab.Gitlab(
    url=settings.gitlab.url,
    private_token=settings.gitlab.private_token.get_secret_value(),
)
