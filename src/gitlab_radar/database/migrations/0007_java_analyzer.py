from typing import ClassVar

from tortoise import migrations
from tortoise.migrations import operations as ops


class Migration(migrations.Migration):
    operations: ClassVar[list[object]] = [
        ops.RunSQL(
            sql=(
                "INSERT INTO package_manager (code, name) VALUES ('maven', 'Maven'), ('gradle', 'Gradle') "
                'ON CONFLICT (code) DO NOTHING; '
                'INSERT INTO language_package_manager (language_id, package_manager_id) '
                'SELECT language.id, manager.id FROM programming_language language '
                "CROSS JOIN package_manager manager WHERE language.code = 'java' "
                "AND manager.code IN ('maven', 'gradle') "
                'ON CONFLICT (language_id, package_manager_id) DO NOTHING; '
                "UPDATE programming_language SET oldest_current_version = '8' "
                "WHERE code = 'java' AND oldest_current_version IS NULL"
            ),
            reverse_sql=(
                "UPDATE programming_language SET oldest_current_version = NULL "
                "WHERE code = 'java' AND oldest_current_version = '8'; "
                'DELETE FROM language_package_manager WHERE language_id = '
                "(SELECT id FROM programming_language WHERE code = 'java') "
                "AND package_manager_id IN (SELECT id FROM package_manager WHERE code IN ('maven', 'gradle')); "
                "DELETE FROM package_manager WHERE code IN ('maven', 'gradle')"
            ),
        ),
    ]
