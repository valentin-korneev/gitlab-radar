import logging
from collections.abc import Mapping

import yaml

from gitlab_radar.schemas.project import GitLabComponent

logger = logging.getLogger(__name__)


def parse_gitlab_components(files: Mapping[str, bytes]) -> list[GitLabComponent]:
    components: dict[tuple[str, str | None], GitLabComponent] = {}
    for path, content in files.items():
        try:
            document = yaml.safe_load(content.decode('utf-8'))
        except (UnicodeDecodeError, yaml.YAMLError):
            logger.warning('Не удалось разобрать конфигурацию GitLab CI: %s', path)
            continue
        if not isinstance(document, dict):
            continue
        includes = document.get('include', [])
        if isinstance(includes, dict):
            includes = [includes]
        if not isinstance(includes, list):
            continue
        for include in includes:
            if not isinstance(include, dict) or not isinstance(include.get('component'), str):
                continue
            reference = include['component'].strip()
            name, separator, version = reference.rpartition('@')
            component = GitLabComponent(
                name=name if separator else reference,
                version=version or None if separator else None,
            )
            components[(component.name, component.version)] = component
    return sorted(components.values(), key=lambda component: (component.name, component.version or ''))
