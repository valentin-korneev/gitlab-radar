from typing import ClassVar

from tortoise import migrations
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    operations: ClassVar[list[object]] = [
        ops.RunSQL(
            sql=(
                "UPDATE companyrequirementgroup SET name = 'Версии языков', "
                "description = 'Требования к используемым версиям языков программирования.' "
                "WHERE name = 'Python'; "
                'INSERT INTO companyrequirement '
                '(code, title, group_id, description, condition, enabled, sort_order) '
                "SELECT 'java-version-current', 'Версия Java выше заданной', requirement_group.id, "
                "'Проект использует версию Java выше установленной минимальной актуальной версии.', "
                "'{\"logic\":\"and\",\"items\":[{\"source\":\"runtime_version\","
                "\"operator\":\"greater_than_or_equal\","
                "\"values\":[\"$java_oldest_current_version\"]}]}'::jsonb, "
                'TRUE, COALESCE(MAX(requirement.sort_order), 0) + 1 '
                'FROM companyrequirementgroup requirement_group '
                'LEFT JOIN companyrequirement requirement ON requirement.group_id = requirement_group.id '
                "WHERE requirement_group.name = 'Версии языков' GROUP BY requirement_group.id "
                'ON CONFLICT (code) DO NOTHING; '
                'INSERT INTO company_requirement_language (requirement_id, language_id) '
                'SELECT requirement.id, language.id FROM companyrequirement requirement '
                'CROSS JOIN programming_language language '
                "WHERE requirement.code = 'java-version-current' AND language.code = 'java' "
                'ON CONFLICT (requirement_id, language_id) DO NOTHING; '
                "UPDATE programming_framework SET dependency_names = "
                "'[\"org.springframework:*\", \"org.springframework.boot:*\", "
                "\"org.springframework.boot\"]'::jsonb WHERE code = 'java-spring'; "
                "UPDATE programming_framework SET dependency_names = "
                "'[\"io.quarkus:*\", \"io.quarkus\"]'::jsonb WHERE code = 'java-quarkus'; "
                "UPDATE programming_framework SET dependency_names = "
                "'[\"io.micronaut:*\", \"io.micronaut.*:*\", "
                "\"io.micronaut.application\", \"io.micronaut.library\"]'::jsonb "
                "WHERE code = 'java-micronaut'"
            ),
            reverse_sql=(
                'DELETE FROM company_requirement_language WHERE requirement_id = '
                "(SELECT id FROM companyrequirement WHERE code = 'java-version-current'); "
                "DELETE FROM companyrequirement WHERE code = 'java-version-current'; "
                "UPDATE companyrequirementgroup SET name = 'Python', "
                "description = 'Требования к используемой версии Python.' "
                "WHERE name = 'Версии языков'; "
                "UPDATE programming_framework SET dependency_names = "
                "'[\"org.springframework:spring-core\", "
                "\"org.springframework.boot:spring-boot\"]'::jsonb WHERE code = 'java-spring'; "
                "UPDATE programming_framework SET dependency_names = "
                "'[\"io.quarkus:quarkus-core\"]'::jsonb WHERE code = 'java-quarkus'; "
                "UPDATE programming_framework SET dependency_names = "
                "'[\"io.micronaut:micronaut-core\"]'::jsonb WHERE code = 'java-micronaut'"
            ),
        ),
    ]
