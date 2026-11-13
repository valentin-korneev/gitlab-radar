from tortoise import fields

from gitlab_radar.database.models.base import RadarModel


class CompanyRequirementGroup(RadarModel):
    id = fields.IntField(primary_key=True)
    name = fields.CharField(max_length=100, unique=True)
    description = fields.TextField(default='')
    sort_order = fields.IntField(default=0)

    class Meta:
        table = 'company_requirement_group'


class CompanyRequirement(RadarModel):
    id = fields.IntField(primary_key=True)
    code = fields.CharField(max_length=100, unique=True)
    title = fields.CharField(max_length=200)
    group = fields.ForeignKeyField(
        'models.CompanyRequirementGroup',
        related_name='requirements',
        on_delete=fields.RESTRICT,
    )
    description = fields.TextField(default='')
    condition = fields.JSONField()
    enabled = fields.BooleanField(default=True, index=True)
    sort_order = fields.IntField(default=0)

    class Meta:
        table = 'company_requirement'


class CompanyRequirementLanguage(RadarModel):
    id = fields.IntField(primary_key=True)
    requirement = fields.ForeignKeyField(
        'models.CompanyRequirement', related_name='language_links', on_delete=fields.CASCADE
    )
    language = fields.ForeignKeyField(
        'models.ProgrammingLanguage', related_name='requirement_links', on_delete=fields.RESTRICT
    )

    class Meta:
        table = 'company_requirement_language'
        unique_together = (('requirement', 'language'),)
