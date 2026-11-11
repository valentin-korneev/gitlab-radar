import logging
from pathlib import PurePosixPath

from gitlab_radar.config import settings
from gitlab_radar.schemas.project import Project, ProjectLanguage, ProjectSubproject
from gitlab_radar.schemas.technology import PackageManager
from gitlab_radar.services.analysis import analyzer_for
from gitlab_radar.services.analysis.registry import GITLAB_CI_FILENAMES
from gitlab_radar.services.container_parser import parse_container_images
from gitlab_radar.services.gitlab_ci import parse_gitlab_components
from gitlab_radar.services.package_manager import is_container_filename

logger = logging.getLogger(__name__)


def analyze_project(project: Project, files: dict[str, str], revision: str | None) -> Project:
    contents = {path: content.encode() for path, content in files.items()}
    ci_files = {
        path: content for path, content in contents.items() if PurePosixPath(path).name in GITLAB_CI_FILENAMES
    }
    project.revision = revision
    project.subprojects = []
    for language in project.languages:
        _analyze_language(project, language, contents)
    project.package_manager = _project_package_manager(project.subprojects)
    project.has_docker = any(is_container_filename(PurePosixPath(path).name) for path in contents)
    project.has_gitlab_ci = bool(ci_files)
    project.gitlab_ci_components = parse_gitlab_components(ci_files, settings.gitlab.url)
    project.container_images = parse_container_images(contents)
    project.package_registries = sorted(
        {registry for item in project.subprojects for registry in item.package_registries}
    )
    language_errors = [language.error for language in project.languages if language.error]
    project.scan_error = '; '.join(language_errors) if language_errors else None
    logger.info(
        'Проект %s проанализирован: языков %d, модулей %d, файлов %d',
        project.path_with_namespace,
        len(project.languages),
        len(project.subprojects),
        len(contents),
    )
    return project


def _analyze_language(project: Project, language: ProjectLanguage, files: dict[str, bytes]) -> None:
    if language.analysis_status == 'disabled':
        language.analyzer_version = None
        language.error = None
        return
    analyzer = analyzer_for(language.code)
    if analyzer is None:
        language.analysis_status = 'unsupported'
        language.analyzer_version = None
        language.error = None
        return
    selected_paths = {selection.path for selection in analyzer.select_files(list(files))}
    selected_files = {path: content for path, content in files.items() if path in selected_paths}
    try:
        project.subprojects.extend(analyzer.analyze(project, selected_files))
    except Exception as error:  # pylint: disable=broad-exception-caught
        language.analysis_status = 'failed'
        language.analyzer_version = analyzer.version
        language.error = str(error)
        logger.exception(
            'Не удалось выполнить анализ языка %s в проекте %s',
            language.name,
            project.path_with_namespace,
        )
        return
    language.analysis_status = 'analyzed'
    language.analyzer_version = analyzer.version
    language.error = None


def _project_package_manager(subprojects: list[ProjectSubproject]) -> PackageManager:
    if not subprojects:
        return PackageManager.UNKNOWN
    managers = {
        subproject.package_manager
        for subproject in subprojects
        if subproject.package_manager is not PackageManager.UNKNOWN
    }
    if not managers:
        return PackageManager.UNKNOWN
    return managers.pop() if len(managers) == 1 else PackageManager.MIXED
