from enum import StrEnum


class PackageManager(StrEnum):
    PIP = 'pip'
    POETRY = 'poetry'
    UV = 'uv'
    UNKNOWN = 'unknown'
