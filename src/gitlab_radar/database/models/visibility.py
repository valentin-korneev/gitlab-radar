from tortoise import fields

from gitlab_radar.database.models.base import RadarModel


class UserVisibilityGroup(RadarModel):
    id = fields.IntField(primary_key=True)
    user = fields.ForeignKeyField('models.AuthorizedUser', related_name='visibility_groups', on_delete=fields.CASCADE)
    name = fields.CharField(max_length=100)
    is_active = fields.BooleanField(default=False, index=True)
    sort_order = fields.IntField(default=0)

    class Meta:
        table = 'user_visibility_group'
        unique_together = (('user', 'name'),)


class UserVisibilityRule(RadarModel):
    id = fields.IntField(primary_key=True)
    group = fields.ForeignKeyField('models.UserVisibilityGroup', related_name='rules', on_delete=fields.CASCADE)
    action = fields.CharField(max_length=10)
    target = fields.CharField(max_length=20, default='path', db_default='path')
    pattern = fields.CharField(max_length=500)
    sort_order = fields.IntField(default=0)

    class Meta:
        table = 'user_visibility_rule'


class AdminVisibilityPolicy(RadarModel):
    id = fields.IntField(primary_key=True)
    name = fields.CharField(max_length=100, unique=True)

    class Meta:
        table = 'admin_visibility_policy'


class AdminVisibilityPolicyRule(RadarModel):
    id = fields.IntField(primary_key=True)
    policy = fields.ForeignKeyField('models.AdminVisibilityPolicy', related_name='rules', on_delete=fields.CASCADE)
    action = fields.CharField(max_length=10)
    target = fields.CharField(max_length=20, default='path', db_default='path')
    pattern = fields.CharField(max_length=500)
    sort_order = fields.IntField(default=0)

    class Meta:
        table = 'admin_visibility_policy_rule'


class AdminVisibilityPolicyAssignment(RadarModel):
    id = fields.IntField(primary_key=True)
    policy = fields.ForeignKeyField(
        'models.AdminVisibilityPolicy', related_name='assignments', on_delete=fields.CASCADE
    )
    user = fields.ForeignKeyField(
        'models.AuthorizedUser', related_name='visibility_policy_assignments', on_delete=fields.CASCADE
    )

    class Meta:
        table = 'admin_visibility_policy_assignment'
        unique_together = (('policy', 'user'),)


class AdminUserVisibilityRule(RadarModel):
    id = fields.IntField(primary_key=True)
    user = fields.ForeignKeyField(
        'models.AuthorizedUser', related_name='admin_visibility_rules', on_delete=fields.CASCADE
    )
    action = fields.CharField(max_length=10)
    target = fields.CharField(max_length=20, default='path', db_default='path')
    pattern = fields.CharField(max_length=500)
    sort_order = fields.IntField(default=0)

    class Meta:
        table = 'admin_user_visibility_rule'
