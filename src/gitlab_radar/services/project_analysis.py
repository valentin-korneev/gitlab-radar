import logging
from pathlib import PurePosixPath

from gitlab_radar.config import settings
from gitlab_radar.schemas.project import (
    LanguageAnalysisStatus,
    Project,
    ProjectAnalysisStatus,
    ProjectLanguage,
    ProjectSubproject,
)
from gitlab_radar.schemas.technology import PackageManager
from gitlab_radar.services.analysis import analyzer_for
from gitlab_radar.services.analysis.diagnostics import PARSE_ERRORS, report, validated_files
from gitlab_radar.services.analysis.registry import GITLAB_CI_FILENAMES
from gitlab_radar.services.container_parser import parse_container_images
from gitlab_radar.services.gitlab_ci import parse_gitlab_components
from gitlab_radar.services.package_manager import is_container_filename

logger = logging.getLogger(__name__)


def analyze_project(project: Project, files: dict[str, str], revision: str | None) -> Project:
    contents = {path: content.encode() for path, content in files.items()}
    project.analysis_diagnostics = []
    contents = validated_files(project, contents)
    ci_files = {path: content for path, content in contents.items() if PurePosixPath(path).name in GITLAB_CI_FILENAMES}
    project.revision = revision
    project.subprojects = []
    for language in project.languages:
        _analyze_language(project, language, contents)
    project.package_manager = _project_package_manager(project.subprojects)
    project.has_docker = any(is_container_filename(PurePosixPath(path).name) for path in files)
    project.has_gitlab_ci = any(PurePosixPath(path).name in GITLAB_CI_FILENAMES for path in files)
    project.gitlab_ci_components = parse_gitlab_components(ci_files, settings.gitlab.url)
    project.container_images = parse_container_images(contents)
    project.package_registries = sorted(
        {registry for item in project.subprojects for registry in item.package_registries}
    )
    messages = [f'{item.file_path}: {item.message}' for item in project.analysis_diagnostics]
    project.scan_error = '; '.join(dict.fromkeys(messages)) or None
    failed = [language for language in project.languages if language.analysis_status == LanguageAnalysisStatus.FAILED]
    if project.scan_error:
        project.analysis_status = (
            ProjectAnalysisStatus.PARTIAL
            if project.subprojects or len(failed) < len(project.languages)
            else ProjectAnalysisStatus.FAILED
        )
    else:
        project.analysis_status = ProjectAnalysisStatus.SUCCESS
    logger.info(
        'Проект %s проанализирован: языков %d, модулей %d, файлов %d',
        project.path_with_namespace,
        len(project.languages),
        len(project.subprojects),
        len(contents),
    )
    return project


def _analyze_language(project: Project, language: ProjectLanguage, files: dict[str, bytes]) -> None:
    if language.analysis_status == LanguageAnalysisStatus.DISABLED:
        language.analyzer_version = None
        language.error = None
        return
    analyzer = analyzer_for(language.code)
    if analyzer is None:
        language.analysis_status = LanguageAnalysisStatus.UNSUPPORTED
        language.analyzer_version = None
        language.error = None
        return
    selected_paths = {selection.path for selection in analyzer.select_files(list(files))}
    selected_files = {path: content for path, content in files.items() if path in selected_paths}
    try:
        project.subprojects.extend(analyzer.analyze(project, selected_files))
    except PARSE_ERRORS as error:
        language.analysis_status = LanguageAnalysisStatus.FAILED
        language.analyzer_version = analyzer.version
        language.error = f'Ошибка анализатора {language.code} ({type(error).__name__})'
        report(project, '.', language.error, language=language.code)
        logger.exception(
            'Не удалось выполнить анализ языка %s в проекте %s',
            language.name,
            project.path_with_namespace,
        )
        return
    diagnostics = [
        item
        for item in project.analysis_diagnostics
        if item.language == language.code or (item.language is None and analyzer.select_files([item.file_path]))
    ]
    language.analysis_status = (
        (
            LanguageAnalysisStatus.PARTIAL
            if any(item.language == language.code for item in project.subprojects)
            else LanguageAnalysisStatus.FAILED
        )
        if diagnostics
        else LanguageAnalysisStatus.ANALYZED
    )
    language.analyzer_version = analyzer.version
    language.error = '; '.join(f'{item.file_path}: {item.message}' for item in diagnostics) or None


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
