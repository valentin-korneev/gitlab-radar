import logging
import tomllib
from typing import Any
lazy from collections.abc import Collection

from gitlab_radar.schemas.technology import PackageManager

logger = logging.getLogger(__name__)

PYPROJECT_FILENAME = 'pyproject.toml'
UV_CONFIG_FILENAME = 'uv.toml'
POETRY_LOCK_FILENAME = 'poetry.lock'
UV_LOCK_FILENAME = 'uv.lock'
PACKAGE_FILES = (
    PYPROJECT_FILENAME,
    UV_CONFIG_FILENAME,
    POETRY_LOCK_FILENAME,
    UV_LOCK_FILENAME,
)


def detect_package_manager(
    pyproject_content: bytes | None,
    available_files: Collection[str] = (),
) -> PackageManager:
    pyproject = _parse_pyproject(pyproject_content)

    poetry_detected = _has_tool_section(pyproject, 'poetry') or _uses_build_system(
        pyproject,
        backend_prefix='poetry.core',
        package='poetry-core',
    )
    uv_detected = (
        UV_CONFIG_FILENAME in available_files
        or _has_tool_section(pyproject, 'uv')
        or _uses_build_system(
            pyproject,
            backend_prefix='uv_build',
            package='uv-build',
        )
    )

    configured_manager = _manager_from_markers(poetry=poetry_detected, uv=uv_detected)
    if configured_manager is not PackageManager.UNKNOWN:
        return configured_manager

    locked_manager = _manager_from_markers(
        poetry=POETRY_LOCK_FILENAME in available_files,
        uv=UV_LOCK_FILENAME in available_files,
    )
    if locked_manager is not PackageManager.UNKNOWN:
        return locked_manager

    if pyproject_content is None and not available_files:
        return PackageManager.PIP
    return PackageManager.UNKNOWN


def _parse_pyproject(content: bytes | None) -> dict[str, Any]:
    if content is None:
        return {}
    try:
        return tomllib.loads(content.decode('utf-8'))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError):
        logger.warning('Не удалось разобрать pyproject.toml')
        return {}


def _manager_from_markers(*, poetry: bool, uv: bool) -> PackageManager:
    if poetry == uv:
        return PackageManager.UNKNOWN
    if poetry:
        return PackageManager.POETRY
    return PackageManager.UV


def _has_tool_section(pyproject: dict[str, Any], name: str) -> bool:
    tool = pyproject.get('tool')
    return isinstance(tool, dict) and isinstance(tool.get(name), dict)


def _uses_build_system(
    pyproject: dict[str, Any],
    *,
    backend_prefix: str,
    package: str,
) -> bool:
    build_system = pyproject.get('build-system')
    if not isinstance(build_system, dict):
        return False

    backend = build_system.get('build-backend')
    if isinstance(backend, str) and backend.startswith(backend_prefix):
        return True

    requirements = build_system.get('requires')
    if not isinstance(requirements, list):
        return False
    return any(
        isinstance(requirement, str) and _requirement_name(requirement) == package
        for requirement in requirements
    )


def _requirement_name(requirement: str) -> str:
    name = requirement.strip().partition(';')[0]
    for separator in ('[', ' ', '<', '>', '=', '!', '~'):
        name = name.partition(separator)[0]
    return name.lower().replace('_', '-')
