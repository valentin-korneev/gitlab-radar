import hashlib
import json
import re
from pathlib import PurePosixPath

from gitlab_radar.services.analysis.base import FileSelection, LanguageAnalyzer
from gitlab_radar.services.analysis.languages import (
    JavaAnalyzer,
    JavaScriptAnalyzer,
    PythonAnalyzer,
    TypeScriptAnalyzer,
)
from gitlab_radar.services.package_manager import is_container_filename

GITLAB_CI_FILENAMES = frozenset({'.gitlab-ci.yml', '.gitlab-ci.yaml'})
LANGUAGE_CODE_OVERRIDES = {
    'C#': 'c-sharp',
    'C++': 'cpp',
    'F#': 'f-sharp',
    'Objective-C': 'objective-c',
    'Objective-C++': 'objective-cpp',
}
LANGUAGE_ANALYZERS: dict[str, LanguageAnalyzer] = {
    analyzer.language_code: analyzer
    for analyzer in (
        PythonAnalyzer(),
        JavaAnalyzer(),
        JavaScriptAnalyzer(),
        TypeScriptAnalyzer(),
    )
}
PROJECT_ANALYZER_VERSION = '2'


def language_code(name: str) -> str:
    if name in LANGUAGE_CODE_OVERRIDES:
        return LANGUAGE_CODE_OVERRIDES[name]
    return re.sub(r'-+', '-', re.sub(r'[^a-z0-9]+', '-', name.lower())).strip('-')


def analyzer_for(code: str) -> LanguageAnalyzer | None:
    return LANGUAGE_ANALYZERS.get(code)


def select_project_files(repository_paths: list[str], language_codes: list[str]) -> list[FileSelection]:
    selections = _project_file_selections(repository_paths)
    for code in language_codes:
        analyzer = analyzer_for(code)
        if analyzer is not None:
            selections.extend(analyzer.select_files(repository_paths))
    return list({(item.path, item.analyzer_key, item.role, item.language_code): item for item in selections}.values())


def analysis_fingerprint(enabled_language_codes: list[str] | None = None) -> str:
    configuration = {
        'project': {'version': PROJECT_ANALYZER_VERSION},
        'languages': {
            code: {
                'key': analyzer.key,
                'version': analyzer.version,
                'package_managers': analyzer.package_manager_codes,
            }
            for code, analyzer in sorted(LANGUAGE_ANALYZERS.items())
        },
        'enabled_languages': sorted(enabled_language_codes) if enabled_language_codes is not None else None,
    }
    payload = json.dumps(configuration, sort_keys=True, separators=(',', ':')).encode()
    return hashlib.sha256(payload).hexdigest()


def _project_file_selections(repository_paths: list[str]) -> list[FileSelection]:
    result: list[FileSelection] = []
    for path in repository_paths:
        filename = PurePosixPath(path).name
        if filename in GITLAB_CI_FILENAMES:
            result.append(FileSelection(path=path, analyzer_key='gitlab-ci', role='ci'))
        if is_container_filename(filename):
            result.append(FileSelection(path=path, analyzer_key='container', role='container'))
    return result
