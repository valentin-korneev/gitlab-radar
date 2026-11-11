from enum import StrEnum


class PackageManager(StrEnum):
    PIP = 'pip'
    UV = 'uv'
    MIXED = 'mixed'
    UNKNOWN = 'unknown'
