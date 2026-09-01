"""Runtime manifest schema v1 and validation (docs/v2/24-distribution-and-installation).

The manifest is the single authority for the third-party runtime: exact
versions, digests, sizes and executable layouts per platform. Flotation is
forbidden: every artifact pins an exact version and a SHA-256 digest.
"""

from __future__ import annotations

import json
import platform as _platform
import re

from pydantic import BaseModel, ValidationError, field_validator, model_validator

SUPPORTED_SCHEMA_VERSION = 1

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
_KINDS = ("binary", "npm-bundle", "wheelhouse")


class ManifestError(ValueError):
    """The manifest is malformed or uses an unsupported schema."""


class AttestationPolicy(BaseModel):
    required: bool = False
    bundle: str | None = None
    subject_sha256: str | None = None
    repository: str | None = None  # owner/repo for GitHub attestation lookup


class Artifact(BaseModel):
    id: str
    kind: str
    version: str
    url: str
    sha256: str
    size_bytes: int
    executable: str | None = None
    license: str
    attestation: AttestationPolicy = AttestationPolicy()
    install: list[str] = []

    @field_validator("kind")
    @classmethod
    def _known_kind(cls, value: str) -> str:
        if value not in _KINDS:
            raise ValueError(f"unknown artifact kind: {value}")
        return value

    @field_validator("sha256")
    @classmethod
    def _digest_shape(cls, value: str) -> str:
        if not _SHA256_RE.match(value):
            raise ValueError(f"malformed sha256 digest: {value!r}")
        return value

    @field_validator("size_bytes")
    @classmethod
    def _positive_size(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("size_bytes must be positive")
        return value

    @field_validator("executable")
    @classmethod
    def _safe_relative_path(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parts = value.split("/")
        if value.startswith("/") or ".." in parts or "\\" in value:
            raise ValueError(f"unsafe executable path: {value!r}")
        return value

    @model_validator(mode="after")
    def _attestation_shape(self) -> Artifact:
        if self.attestation.required and not (
                self.attestation.bundle or self.attestation.repository):
            raise ValueError(
                f"artifact {self.id!r} requires attestation but declares "
                "neither a bundle nor a repository to look it up")
        return self


class PlatformEntry(BaseModel):
    os: str
    arch: str
    artifacts: list[Artifact]

    @model_validator(mode="after")
    def _unique_artifact_ids(self) -> PlatformEntry:
        ids = [a.id for a in self.artifacts]
        if len(ids) != len(set(ids)):
            raise ValueError(f"duplicate artifact id for {self.os}/{self.arch}")
        return self

    def artifact(self, artifact_id: str) -> Artifact | None:
        for artifact in self.artifacts:
            if artifact.id == artifact_id:
                return artifact
        return None


class ReleaseIdentity(BaseModel):
    version: str
    git_tag: str
    commit: str

    @field_validator("commit")
    @classmethod
    def _commit_shape(cls, value: str) -> str:
        if not _COMMIT_RE.match(value):
            raise ValueError(f"malformed commit: {value!r}")
        return value


class Requirements(BaseModel):
    min_ram_mib: int = 1024
    min_disk_mib: int = 2048
    network: str = "required-for-setup"


class RuntimeManifest(BaseModel):
    schema_version: int
    release: ReleaseIdentity
    platforms: list[PlatformEntry]
    requirements: Requirements = Requirements()

    @model_validator(mode="after")
    def _schema_and_platforms(self) -> RuntimeManifest:
        if self.schema_version != SUPPORTED_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported manifest schema_version {self.schema_version}"
                f" (supported: {SUPPORTED_SCHEMA_VERSION})")
        keys = [(p.os, p.arch) for p in self.platforms]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate platform entry in manifest")
        return self

    def platform_for(self, os_name: str, arch: str) -> PlatformEntry | None:
        for entry in self.platforms:
            if entry.os == os_name and entry.arch == arch:
                return entry
        return None


def load_manifest(data: str) -> RuntimeManifest:
    try:
        payload = json.loads(data)
    except json.JSONDecodeError as exc:
        raise ManifestError(f"manifest is not valid JSON: {exc}") from exc
    try:
        return RuntimeManifest.model_validate(payload)
    except ValidationError as exc:
        raise ManifestError(f"invalid manifest: {exc}") from exc


def normalize_system(system: str | None = None) -> str:
    value = (system or _platform.system()).lower()
    if value in ("linux", "darwin", "windows"):
        return value
    raise ValueError(f"unsupported operating system: {value!r}")


def normalize_machine(machine: str | None = None) -> str:
    value = (machine or _platform.machine()).lower()
    if value in ("amd64", "x86_64"):
        return "x86_64"
    if value in ("arm64", "aarch64"):
        return "aarch64"
    raise ValueError(f"unsupported machine architecture: {value!r}")


def current_platform() -> tuple[str, str]:
    return normalize_system(), normalize_machine()
