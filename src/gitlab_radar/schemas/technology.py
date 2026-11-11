from enum import StrEnum


class PackageManager(StrEnum):
    PIP = 'pip'
    UV = 'uv'
    MAVEN = 'maven'
    GRADLE = 'gradle'
    NPM = 'npm'
    YARN = 'yarn'
    PNPM = 'pnpm'
    MIXED = 'mixed'
    UNKNOWN = 'unknown'
