from enum import StrEnum


class PackageManager(StrEnum):
    PIP = 'pip'
    UV = 'uv'
    MAVEN = 'maven'
    GRADLE = 'gradle'
    MIXED = 'mixed'
    UNKNOWN = 'unknown'
