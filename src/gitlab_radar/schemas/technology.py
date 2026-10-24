from enum import StrEnum


class PackageManager(StrEnum):
    CONDA = 'conda'
    PIP = 'pip'
    PIPENV = 'pipenv'
    POETRY = 'poetry'
    UV = 'uv'
    UNKNOWN = 'unknown'
