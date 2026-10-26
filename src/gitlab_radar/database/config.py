from gitlab_radar.config import settings

TORTOISE_ORM = {
    'connections': {
        'default': {
            'engine': 'tortoise.backends.asyncpg',
            'credentials': {
                'host': settings.database.host,
                'port': settings.database.port,
                'database': settings.database.database,
                'user': settings.database.user,
                'password': settings.database.password.get_secret_value(),
                'schema': settings.database.schema_name,
            },
        },
    },
    'apps': {
        'models': {
            'models': ['gitlab_radar.database.models'],
            'default_connection': 'default',
            'migrations': 'gitlab_radar.database.migrations',
        },
    },
    'use_tz': True,
    'timezone': 'UTC',
}
