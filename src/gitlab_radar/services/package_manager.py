from collections.abc import Collection, Mapping

from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name

from gitlab_radar.schemas.technology import PackageManager

PYPROJECT_FILENAME = 'pyproject.toml'
UV_CONFIG_FILENAME = 'uv.toml'
POETRY_LOCK_FILENAME = 'poetry.lock'
UV_LOCK_FILENAME = 'uv.lock'
PIPFILE_FILENAME = 'Pipfile'
PIPFILE_LOCK_FILENAME = 'Pipfile.lock'
CONDA_CONFIG_FILENAMES = ('environment.yml', 'environment.yaml')
CONDA_LOCK_FILENAMES = ('conda-lock.yml', 'conda-lock.yaml')
REQUIREMENTS_FILENAME = 'requirements.txt'
PYTHON_VERSION_FILENAME = '.python-version'
PACKAGE_FILES = (
    PYPROJECT_FILENAME,
    UV_CONFIG_FILENAME,
    POETRY_LOCK_FILENAME,
    UV_LOCK_FILENAME,
    PIPFILE_FILENAME,
    PIPFILE_LOCK_FILENAME,
    *CONDA_CONFIG_FILENAMES,
    *CONDA_LOCK_FILENAMES,
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
    if PIPFILE_FILENAME in available_files or PIPFILE_LOCK_FILENAME in available_files:
        detected.add(PackageManager.PIPENV)
    if any(filename in available_files for filename in (*CONDA_CONFIG_FILENAMES, *CONDA_LOCK_FILENAMES)):
        detected.add(PackageManager.CONDA)

    if len(detected) == 1:
        return detected.pop()
    if detected:
        return PackageManager.UNKNOWN

    if PYPROJECT_FILENAME not in available_files:
        return PackageManager.PIP
    return PackageManager.UNKNOWN


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
