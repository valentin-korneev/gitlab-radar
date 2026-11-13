from gitlab_radar.database.models import LanguagePackageManager, PackageManagerCatalog, ProgrammingLanguage
from gitlab_radar.schemas.project import ProjectLanguage
from gitlab_radar.services.analysis import analyzer_for


async def sync_programming_languages(
    languages: list[ProjectLanguage],
) -> dict[str, ProgrammingLanguage]:
    result: dict[str, ProgrammingLanguage] = {}
    for item in languages:
        row, _ = await ProgrammingLanguage.get_or_create(
            code=item.code,
            defaults={
                'name': item.name,
                'enabled': analyzer_for(item.code) is not None,
            },
        )
        if row.name != item.name:
            row.name = item.name
            await row.save(update_fields=['name'])
        analyzer = analyzer_for(item.code)
        if analyzer is not None:
            for manager_code in analyzer.package_manager_codes:
                manager, _ = await PackageManagerCatalog.get_or_create(
                    code=manager_code,
                    defaults={'name': manager_code},
                )
                await LanguagePackageManager.get_or_create(
                    language=row,
                    package_manager=manager,
                )
        result[item.code] = row
    return result
