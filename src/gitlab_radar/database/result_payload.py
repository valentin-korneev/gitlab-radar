import hashlib
import json
from collections.abc import Mapping

from gitlab_radar.schemas.project import Project

METADATA_FIELDS = frozenset(
    {
        'id',
        'name',
        'path_with_namespace',
        'default_branch',
        'web_url',
        'last_activity_at',
        'scanned_at',
        'webhooks',
        'webhooks_accessible',
        'gitlab_access_level',
        'revision',
        'is_empty',
    }
)
DERIVED_FIELDS = frozenset({'frameworks', 'data_status', 'company_compliance_percentage', 'company_rule_results'})


def project_metadata(project: Project) -> dict:
    payload = project.model_dump(mode='json', include=METADATA_FIELDS)
    payload['languages'] = [language.model_dump(mode='json') for language in project.languages]
    return payload


def analysis_payload(project: Project) -> dict:
    payload = project.model_dump(mode='json', exclude=METADATA_FIELDS | DERIVED_FIELDS)
    payload['languages'] = [language.model_dump(mode='json', exclude={'percentage'}) for language in project.languages]
    payload['subprojects'] = [
        module.model_dump(mode='json', exclude={'company_compliance_percentage', 'company_rule_results'})
        for module in project.subprojects
    ]
    return payload


def input_digest(files: Mapping[str, str]) -> str:
    digest = hashlib.sha256()
    for path, content in sorted(files.items()):
        for value in (path, content):
            encoded = value.encode('utf-8')
            digest.update(len(encoded).to_bytes(8, 'big'))
            digest.update(encoded)
    return digest.hexdigest()


def result_cache_key(gitlab_id: int, digest: str, fingerprint: str) -> str:
    value = json.dumps([gitlab_id, digest, fingerprint], separators=(',', ':'))
    return hashlib.sha256(value.encode()).hexdigest()


def result_identity(gitlab_id: int, digest: str | None, fingerprint: str, payload: dict) -> str:
    value = json.dumps([gitlab_id, digest, fingerprint, payload], sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(value.encode()).hexdigest()
