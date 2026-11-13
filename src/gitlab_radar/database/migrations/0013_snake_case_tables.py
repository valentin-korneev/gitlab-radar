from tortoise import migrations
from tortoise.migrations import operations as ops


class RenameTable(ops.AlterModelOptions):
    """Keep migration state and PostgreSQL table names in sync without recreating tables."""

    def __init__(self, name, table):
        super().__init__(name=name, options={'table': table})

    def state_forward(self, app_label, state):
        model = self.get_model_state(state, app_label, self.name)
        model.options['table'] = self.options['table']
        state.reload_model(app_label, self.name)

    def describe(self):
        return f'Rename {self.name} table to {self.options["table"]}'

    async def database_forward(self, app_label, old_state, new_state, state_editor=None):
        if state_editor is None:
            return
        old_model = old_state.apps.get_model(app_label, self.name)
        new_model = new_state.apps.get_model(app_label, self.name)
        await state_editor.rename_table(new_model, old_model._meta.db_table, new_model._meta.db_table)

    async def database_backward(self, app_label, old_state, new_state, state_editor=None):
        await self.database_forward(app_label, old_state, new_state, state_editor)


class Migration(migrations.Migration):
    dependencies = [('models', '0012_immutable_analysis_results')]

    operations = [
        RenameTable('ScanRun', 'scan_run'),
        RenameTable('WebSocketTicket', 'websocket_ticket'),
        RenameTable('WebSession', 'web_session'),
        RenameTable('UserVisibilityGroup', 'user_visibility_group'),
        RenameTable('UserVisibilityRule', 'user_visibility_rule'),
        RenameTable('AdminVisibilityPolicy', 'admin_visibility_policy'),
        RenameTable('AdminVisibilityPolicyRule', 'admin_visibility_policy_rule'),
        RenameTable('AdminVisibilityPolicyAssignment', 'admin_visibility_policy_assignment'),
        RenameTable('AdminUserVisibilityRule', 'admin_user_visibility_rule'),
        RenameTable('CompanyRequirementGroup', 'company_requirement_group'),
        RenameTable('CompanyRequirement', 'company_requirement'),
        RenameTable('ApplicationParameter', 'application_parameter'),
        RenameTable('DataFixture', 'data_fixture'),
    ]
