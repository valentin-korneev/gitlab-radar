from collections.abc import Collection, Mapping
from fnmatch import fnmatchcase

from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name

from gitlab_radar.schemas.technology import PackageManager

PYPROJECT_FILENAME = 'pyproject.toml'
UV_CONFIG_FILENAME = 'uv.toml'
POETRY_LOCK_FILENAME = 'poetry.lock'
UV_LOCK_FILENAME = 'uv.lock'
REQUIREMENTS_FILENAME = 'requirements.txt'
REQUIREMENTS_FILENAME_PATTERN = 'requirements.*.txt'
PYTHON_VERSION_FILENAME = '.python-version'
PACKAGE_FILES = (
    PYPROJECT_FILENAME,
    UV_CONFIG_FILENAME,
    POETRY_LOCK_FILENAME,
    UV_LOCK_FILENAME,
)
PACKAGE_DISCOVERY_FILES = (*PACKAGE_FILES, REQUIREMENTS_FILENAME)
CONTAINER_FILES = (
    'Dockerfile',
    'dockerfile',
    'compose.yaml',
    'compose.yml',
    'docker-compose.yaml',
    'docker-compose.yml',
)
SUBPROJECT_FILES = (*PACKAGE_DISCOVERY_FILES, PYTHON_VERSION_FILENAME, *CONTAINER_FILES)


def detect_package_manager(
    pyproject: Mapping[str, object],
    available_files: Collection[str] = (),
) -> PackageManager:
    detected: set[PackageManager] = set()
    if (
        UV_CONFIG_FILENAME in available_files
        or UV_LOCK_FILENAME in available_files
        or _has_tool_section(pyproject, 'uv')
        or _uses_build_system(pyproject, backend_prefix='uv_build', package='uv-build')
    ):
        detected.add(PackageManager.UV)
    if (
        POETRY_LOCK_FILENAME in available_files
        or _has_tool_section(pyproject, 'poetry')
        or _uses_build_system(pyproject, backend_prefix='poetry.core', package='poetry-core')
    ):
        detected.add(PackageManager.POETRY)
    if len(detected) == 1:
        return detected.pop()
    if detected:
        return PackageManager.UNKNOWN

    if any(is_requirements_filename(filename) for filename in available_files):
        return PackageManager.PIP
    if PYPROJECT_FILENAME not in available_files:
        return PackageManager.PIP
    return PackageManager.UNKNOWN


def is_requirements_filename(filename: str) -> bool:
    return filename == REQUIREMENTS_FILENAME or fnmatchcase(filename, REQUIREMENTS_FILENAME_PATTERN)


def is_package_discovery_filename(filename: str) -> bool:
    return filename in PACKAGE_FILES or is_requirements_filename(filename)


def is_dockerfile_filename(filename: str) -> bool:
    return filename.lower().startswith('dockerfile')


def is_container_filename(filename: str) -> bool:
    return is_dockerfile_filename(filename) or filename in CONTAINER_FILES


def is_subproject_filename(filename: str) -> bool:
    return (
        is_package_discovery_filename(filename)
        or filename == PYTHON_VERSION_FILENAME
        or is_container_filename(filename)
    )


def _has_tool_section(pyproject: Mapping[str, object], name: str) -> bool:
    tool = pyproject.get('tool')
    return isinstance(tool, dict) and isinstance(tool.get(name), dict)


def _uses_build_system(
    pyproject: Mapping[str, object],
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
    try:
        return canonicalize_name(Requirement(requirement).name)
    except InvalidRequirement:
        return ''
