import re
from pathlib import PurePosixPath

import yaml

from gitlab_radar.schemas.project import ContainerImage, ContainerSource
from gitlab_radar.services.package_manager import is_dockerfile_filename

_ARG_PATTERN = re.compile(r'^\s*ARG\s+([A-Za-z_][A-Za-z0-9_]*)(?:=(.*))?$', re.IGNORECASE)
_FROM_PATTERN = re.compile(r'^\s*FROM\s+(?:--\S+\s+)?(\S+)(?:\s+AS\s+(\S+))?', re.IGNORECASE)
_COPY_FROM_PATTERN = re.compile(r'--from=(\S+)', re.IGNORECASE)
_VARIABLE_PATTERN = re.compile(r'\$\{([A-Za-z_][A-Za-z0-9_]*)(?::[-?](.*?))?}|\$([A-Za-z_][A-Za-z0-9_]*)')


def parse_container_images(files: dict[str, bytes]) -> list[ContainerImage]:
    images: dict[tuple[str, str, str | None], ContainerImage] = {}
    for path, content in files.items():
        name = PurePosixPath(path).name
        if is_dockerfile_filename(name):
            parsed = _parse_dockerfile(content, path)
        elif name in {'compose.yaml', 'compose.yml', 'docker-compose.yaml', 'docker-compose.yml'}:
            parsed = _parse_compose(content, path)
        else:
            continue
        for image in parsed:
            key = (image.registry, image.image, image.version)
            existing = images.get(key)
            if existing is None or (
                image.source is ContainerSource.COMPOSE and existing.source is not ContainerSource.COMPOSE
            ):
                images[key] = image
    return sorted(
        images.values(),
        key=lambda item: (item.registry, item.image, item.version or ''),
    )


def _parse_dockerfile(content: bytes, path: str) -> list[ContainerImage]:
    text = _decode(content)
    if text is None:
        return []
    arguments: dict[str, str] = {}
    stages: set[str] = set()
    result: list[ContainerImage] = []
    for line in _logical_lines(text):
        if _collect_argument(line, arguments):
            continue
        instruction = _FROM_PATTERN.match(line)
        if not instruction:
            result.extend(_copy_from_images(line, arguments, stages, path))
            continue
        value = _resolve_variables(instruction.group(1), arguments)
        image = _stage_image(value, stages, path)
        if image is not None:
            result.append(image)
        if instruction.group(2):
            stages.add(instruction.group(2).lower())
    return result


def _collect_argument(line: str, arguments: dict[str, str]) -> bool:
    match = _ARG_PATTERN.match(line)
    if not match or not match.group(2):
        return False
    arguments[match.group(1)] = match.group(2).strip()
    return True


def _copy_from_images(
    line: str,
    arguments: dict[str, str],
    stages: set[str],
    path: str,
) -> list[ContainerImage]:
    result: list[ContainerImage] = []
    for match in _COPY_FROM_PATTERN.finditer(line):
        value = _resolve_variables(match.group(1), arguments)
        if value.lower() in stages or value.isdigit():
            continue
        image = _container_image(value, ContainerSource.DOCKERFILE, path)
        if image is not None:
            result.append(image)
    return result


def _stage_image(value: str, stages: set[str], path: str) -> ContainerImage | None:
    if value.lower() == 'scratch' or value.lower() in stages:
        return None
    return _container_image(value, ContainerSource.DOCKERFILE, path)


def _parse_compose(content: bytes, path: str) -> list[ContainerImage]:
    text = _decode(content)
    if text is None:
        return []
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError:
        return []
    if not isinstance(document, dict) or not isinstance(document.get('services'), dict):
        return []
    result: list[ContainerImage] = []
    for service in document['services'].values():
        if not isinstance(service, dict) or not isinstance(service.get('image'), str):
            continue
        image = _resolve_variables(service['image'], {})
        if image:
            parsed = _container_image(image, ContainerSource.COMPOSE, path)
            if parsed is not None:
                result.append(parsed)
    return result


def _container_image(value: str, source: ContainerSource, path: str) -> ContainerImage | None:
    if _has_unresolved_template(value):
        return None
    reference, separator, digest = value.strip().partition('@')
    version = digest if separator else None
    last_slash = reference.rfind('/')
    last_colon = reference.rfind(':')
    if last_colon > last_slash:
        reference, version = reference[:last_colon], reference[last_colon + 1 :]
    parts = reference.split('/')
    first = parts[0]
    if len(parts) > 1 and ('.' in first or ':' in first or first == 'localhost' or first.startswith('$')):
        registry = first
        image = '/'.join(parts[1:])
    else:
        registry = 'docker.io'
        image = reference
    return ContainerImage(
        registry=registry,
        image=image,
        version=version or None,
        source=source,
        file_path=path,
    )


def _has_unresolved_template(value: str) -> bool:
    return '{{' in value or '}}' in value or _VARIABLE_PATTERN.search(value) is not None


def _logical_lines(text: str) -> list[str]:
    return re.sub(r'\\\s*\n', ' ', text).splitlines()


def _resolve_variables(value: str, arguments: dict[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        name = match.group(1) or match.group(3)
        default = match.group(2)
        return arguments.get(name, default if default is not None else match.group(0))

    return _VARIABLE_PATTERN.sub(replace, value).strip()


def _decode(content: bytes) -> str | None:
    try:
        return content.decode('utf-8')
    except UnicodeDecodeError:
        return None
