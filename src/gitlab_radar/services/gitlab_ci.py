import logging
import re
from collections.abc import Mapping
from urllib.parse import urlsplit

import yaml

from gitlab_radar.schemas.project import GitLabComponent

logger = logging.getLogger(__name__)

_VARIABLE_PATTERN = re.compile(r'\$\{([A-Za-z_][A-Za-z0-9_]*)}|\$([A-Za-z_][A-Za-z0-9_]*)')


def parse_gitlab_components(files: Mapping[str, bytes], gitlab_url: str) -> list[GitLabComponent]:
    components: dict[tuple[str, str | None], GitLabComponent] = {}
    predefined_variables = _predefined_variables(gitlab_url)
    for path, content in files.items():
        try:
            document = yaml.safe_load(content.decode('utf-8'))
        except UnicodeDecodeError, yaml.YAMLError:
            logger.warning('Не удалось разобрать конфигурацию GitLab CI: %s', path)
            continue
        if not isinstance(document, dict):
            continue
        variables = {**predefined_variables, **_global_variables(document)}
        includes = document.get('include', [])
        if isinstance(includes, dict):
            includes = [includes]
        if not isinstance(includes, list):
            continue
        for include in includes:
            if not isinstance(include, dict) or not isinstance(include.get('component'), str):
                continue
            reference = _resolve_variables(include['component'], variables)
            name, separator, version = reference.rpartition('@')
            component = GitLabComponent(
                name=_normalize_component_name(name if separator else reference),
                version=version.strip() or None if separator else None,
            )
            components[(component.name, component.version)] = component
    return sorted(components.values(), key=lambda component: (component.name, component.version or ''))


def _global_variables(document: dict[str, object]) -> dict[str, str]:
    configured = document.get('variables')
    if not isinstance(configured, dict):
        return {}
    variables: dict[str, str] = {}
    for name, value in configured.items():
        if not isinstance(name, str):
            continue
        if isinstance(value, str):
            variables[name] = value
        elif isinstance(value, dict) and isinstance(value.get('value'), str):
            variables[name] = value['value']
    return variables


def _predefined_variables(gitlab_url: str) -> dict[str, str]:
    parsed = urlsplit(gitlab_url if '://' in gitlab_url else f'//{gitlab_url}')
    scheme = parsed.scheme or 'https'
    hostname = parsed.hostname or parsed.path.partition('/')[0]
    try:
        port = parsed.port
    except ValueError:
        port = None
    default_port = 443 if scheme == 'https' else 80
    server_port = port or default_port
    fqdn = f'{hostname}:{port}' if port else hostname
    server_url = gitlab_url.rstrip('/')
    return {
        'CI_SERVER_URL': server_url,
        'CI_SERVER_HOST': hostname,
        'CI_SERVER_FQDN': fqdn,
        'CI_SERVER_PROTOCOL': scheme,
        'CI_SERVER_PORT': str(server_port),
        'CI_API_V4_URL': f'{server_url}/api/v4',
    }


def _resolve_variables(value: str, variables: Mapping[str, str]) -> str:
    result = value.strip()
    for _ in range(len(variables) + 1):
        resolved = _VARIABLE_PATTERN.sub(
            lambda match: variables.get(match.group(1) or match.group(2), match.group(0)),
            result,
        )
        if resolved == result:
            break
        result = resolved
    return result.strip()


def _normalize_component_name(value: str) -> str:
    value = value.strip().rstrip('/')
    parsed = urlsplit(value if '://' in value else f'//{value}')
    if not parsed.hostname:
        return value
    try:
        port = parsed.port
    except ValueError:
        return value
    domain = parsed.hostname.lower()
    if port:
        domain = f'{domain}:{port}'
    path = parsed.path.strip('/')
    return f'{domain}/{path}' if path else domain
