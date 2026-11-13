from tortoise import fields

from gitlab_radar.database.models.base import RadarModel


class PackageHistoryHead(RadarModel):
    id = fields.IntField(primary_key=True)
    target = fields.ForeignKeyField(
        'models.ScanTarget', related_name='package_history_heads', on_delete=fields.RESTRICT
    )
    language = fields.CharField(max_length=100)
    last_scan = fields.ForeignKeyField('models.ScanRun', related_name=False, on_delete=fields.RESTRICT)

    class Meta:
        table = 'package_history_head'
        unique_together = (('target', 'language'),)


class PackagePeriod(RadarModel):
    id = fields.IntField(primary_key=True)
    target = fields.ForeignKeyField('models.ScanTarget', related_name='package_periods', on_delete=fields.RESTRICT)
    package_key = fields.CharField(max_length=64)
    language = fields.CharField(max_length=100)
    module_path = fields.TextField()
    scope = fields.TextField()
    name = fields.TextField()
    versions = fields.JSONField(default=list)
    scan_from = fields.ForeignKeyField('models.ScanRun', related_name=False, on_delete=fields.RESTRICT)
    scan_to = fields.ForeignKeyField('models.ScanRun', related_name=False, on_delete=fields.RESTRICT)
    closed_in = fields.ForeignKeyField('models.ScanRun', related_name=False, null=True, on_delete=fields.RESTRICT)
    baseline = fields.BooleanField(default=False)

    class Meta:
        table = 'package_period'
        unique_together = (('target', 'package_key', 'scan_from'),)
        indexes = (
            ('target_id', 'closed_in_id'),
            ('target_id', 'scan_from_id', 'package_key'),
            ('target_id', 'closed_in_id', 'package_key'),
        )
