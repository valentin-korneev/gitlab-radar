from typing import ClassVar

from tortoise import migrations
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    operations: ClassVar[list[object]] = [
        ops.RunSQL(
            sql=(
                'UPDATE programming_language javascript '
                'SET enabled = javascript.enabled AND typescript.enabled '
                'FROM programming_language typescript '
                "WHERE javascript.code = 'javascript' AND typescript.code = 'typescript'; "
                'UPDATE programming_language typescript '
                'SET enabled = javascript.enabled '
                'FROM programming_language javascript '
                "WHERE javascript.code = 'javascript' AND typescript.code = 'typescript'; "
                'UPDATE companyrequirement '
                "SET code = 'javascript-version-current' "
                "WHERE code = 'typescript-version-current' "
                "AND NOT EXISTS (SELECT 1 FROM companyrequirement WHERE code = 'javascript-version-current'); "
                'UPDATE companyrequirement javascript '
                'SET enabled = javascript.enabled OR typescript.enabled '
                'FROM companyrequirement typescript '
                "WHERE javascript.code = 'javascript-version-current' "
                "AND typescript.code = 'typescript-version-current'; "
                'UPDATE companyrequirement SET '
                'title = CASE '
                "WHEN title IN ('Версия Node.js для JavaScript выше заданной', "
                "'Версия Node.js для TypeScript выше заданной') "
                "THEN 'Версия Node.js выше заданной' ELSE title END, "
                'description = CASE '
                "WHEN description IN ('Проект использует версию Node.js не ниже минимальной поддерживаемой LTS "
                "для JavaScript.', 'Проект использует версию Node.js не ниже минимальной поддерживаемой LTS "
                "для TypeScript.') "
                "THEN 'Проект использует версию Node.js не ниже единой минимальной поддерживаемой LTS.' "
                " ELSE description END "
                "WHERE code = 'javascript-version-current'; "
                'DELETE FROM company_requirement_language '
                'WHERE requirement_id IN (SELECT id FROM companyrequirement '
                "WHERE code = 'typescript-version-current'); "
                "DELETE FROM companyrequirement WHERE code = 'typescript-version-current'; "
                'WITH inserted AS ( '
                'INSERT INTO companyrequirement '
                '(code, title, group_id, description, condition, enabled, sort_order) '
                "SELECT 'javascript-typescript-exclusive', 'JavaScript полностью переведен на TypeScript', "
                'requirement_group.id, '
                "'Если в проекте есть JavaScript или TypeScript, используются только файлы TypeScript, "
                "а не оба языка.', "
                "'{\"logic\":\"and\",\"items\":[{\"source\":\"project_languages\","
                "\"operator\":\"equals\",\"values\":[\"javascript\",\"typescript\"]}]}'::jsonb, "
                'TRUE, COALESCE(MAX(requirement.sort_order), 0) + 1 '
                'FROM companyrequirementgroup requirement_group '
                'LEFT JOIN companyrequirement requirement ON requirement.group_id = requirement_group.id '
                "WHERE requirement_group.name = 'Версии языков' GROUP BY requirement_group.id "
                'ON CONFLICT (code) DO NOTHING RETURNING id '
                ') '
                'INSERT INTO company_requirement_language (requirement_id, language_id) '
                'SELECT inserted.id, language.id FROM inserted '
                "JOIN programming_language language ON language.code = 'javascript' "
                'ON CONFLICT (requirement_id, language_id) DO NOTHING'
            ),
            reverse_sql='SELECT 1',
        ),
    ]