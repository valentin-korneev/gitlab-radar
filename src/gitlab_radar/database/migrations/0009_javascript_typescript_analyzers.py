from typing import ClassVar

from tortoise import migrations
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    operations: ClassVar[list[object]] = [
        ops.RunSQL(
            sql=(
                "INSERT INTO package_manager (code, name) VALUES ('npm', 'npm'), ('yarn', 'Yarn'), ('pnpm', 'pnpm') "
                'ON CONFLICT (code) DO NOTHING; '
                'INSERT INTO language_package_manager (language_id, package_manager_id) '
                'SELECT language.id, manager.id FROM programming_language language '
                'CROSS JOIN package_manager manager '
                "WHERE language.code IN ('javascript', 'typescript') "
                "AND manager.code IN ('npm', 'yarn', 'pnpm') "
                'ON CONFLICT (language_id, package_manager_id) DO NOTHING; '
                "UPDATE programming_language SET oldest_current_version = '22' "
                "WHERE code IN ('javascript', 'typescript') AND oldest_current_version IS NULL; "
                'INSERT INTO companyrequirement '
                '(code, title, group_id, description, condition, enabled, sort_order) '
                "SELECT 'javascript-version-current', 'Версия Node.js для JavaScript выше заданной', "
                'requirement_group.id, '
                "'Проект использует версию Node.js не ниже минимальной поддерживаемой LTS для JavaScript.', "
                "'{\"logic\":\"and\",\"items\":[{\"source\":\"runtime_version\","
                "\"operator\":\"greater_than_or_equal\","
                "\"values\":[\"$javascript_oldest_current_version\"]}]}'::jsonb, "
                'TRUE, COALESCE(MAX(requirement.sort_order), 0) + 1 '
                'FROM companyrequirementgroup requirement_group '
                'LEFT JOIN companyrequirement requirement ON requirement.group_id = requirement_group.id '
                "WHERE requirement_group.name = 'Версии языков' GROUP BY requirement_group.id "
                'ON CONFLICT (code) DO NOTHING; '
                'INSERT INTO companyrequirement '
                '(code, title, group_id, description, condition, enabled, sort_order) '
                "SELECT 'typescript-version-current', 'Версия Node.js для TypeScript выше заданной', "
                'requirement_group.id, '
                "'Проект использует версию Node.js не ниже минимальной поддерживаемой LTS для TypeScript.', "
                "'{\"logic\":\"and\",\"items\":[{\"source\":\"runtime_version\","
                "\"operator\":\"greater_than_or_equal\","
                "\"values\":[\"$typescript_oldest_current_version\"]}]}'::jsonb, "
                'TRUE, COALESCE(MAX(requirement.sort_order), 0) + 1 '
                'FROM companyrequirementgroup requirement_group '
                'LEFT JOIN companyrequirement requirement ON requirement.group_id = requirement_group.id '
                "WHERE requirement_group.name = 'Версии языков' GROUP BY requirement_group.id "
                'ON CONFLICT (code) DO NOTHING; '
                'INSERT INTO company_requirement_language (requirement_id, language_id) '
                'SELECT requirement.id, language.id FROM companyrequirement requirement '
                'JOIN programming_language language ON language.code = '
                "CASE requirement.code WHEN 'javascript-version-current' THEN 'javascript' ELSE 'typescript' END "
                "WHERE requirement.code IN ('javascript-version-current', 'typescript-version-current') "
                'ON CONFLICT (requirement_id, language_id) DO NOTHING'
            ),
            reverse_sql=(
                'DELETE FROM company_requirement_language WHERE requirement_id IN '
                '(SELECT id FROM companyrequirement '
                "WHERE code IN ('javascript-version-current', 'typescript-version-current')); "
                "DELETE FROM companyrequirement WHERE code IN "
                "('javascript-version-current', 'typescript-version-current'); "
                'UPDATE programming_language SET oldest_current_version = NULL '
                "WHERE code IN ('javascript', 'typescript') AND oldest_current_version = '22'; "
                'DELETE FROM language_package_manager '
                "WHERE language_id IN (SELECT id FROM programming_language WHERE code IN ('javascript', 'typescript')) "
                "AND package_manager_id IN (SELECT id FROM package_manager WHERE code IN ('npm', 'yarn', 'pnpm')); "
                "DELETE FROM package_manager WHERE code IN ('npm', 'yarn', 'pnpm')"
            ),
        ),
    ]
