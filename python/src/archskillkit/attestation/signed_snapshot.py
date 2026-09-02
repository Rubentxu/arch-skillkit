"""Signed snapshot prototype (V2.4 M3 slice 12, docs/v2/65).

Ed25519 detached signature over the canonical JSON of a snapshot.
Asymmetric so verification needs only the public key (no need to
share the signing key with CI). Key material lives under
XDG_STATE_HOME/signing/ with restrictive file modes.

This is the spike: the format is stable enough to prototype against
but the wiring into CI, key distribution, rotation policy and
revocation are deliberately out of scope (see docs/v2/65).
"""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from archskillkit.ids import arch_state_root

SIGNATURE_FORMAT_ID = "arch-skillkit/sig-v1"


@dataclass(frozen=True)
class Signature:
    format: str
    key_id: str
    value_b64: str

    def to_dict(self) -> dict:
        return {"format": self.format, "key_id": self.key_id,
                "value_b64": self.value_b64}

    @classmethod
    def from_dict(cls, data: dict) -> Signature:
        return cls(format=data["format"], key_id=data["key_id"],
                   value_b64=data["value_b64"])


def _key_dir() -> Path:
    d = arch_state_root() / "signing"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _priv_path(key_id: str) -> Path:
    return _key_dir() / f"{key_id}.priv.pem"


def _pub_path(key_id: str) -> Path:
    return _key_dir() / f"{key_id}.pub.pem"


def generate_keypair(key_id: str = "default") -> Ed25519PublicKey:
    priv = Ed25519PrivateKey.generate()
    priv_bytes = priv.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption())
    pub_bytes = priv.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo)
    priv_path = _priv_path(key_id)
    pub_path = _pub_path(key_id)
    priv_path.write_text(priv_bytes.decode())
    pub_path.write_text(pub_bytes.decode())
    os.chmod(priv_path, 0o600)
    os.chmod(pub_path, 0o644)
    return priv.public_key()


def load_public_key(key_id: str = "default") -> Ed25519PublicKey:
    text = _pub_path(key_id).read_text()
    key = serialization.load_pem_public_key(text.encode())
    assert isinstance(key, Ed25519PublicKey)
    return key


def load_private_key(key_id: str = "default") -> Ed25519PrivateKey:
    text = _priv_path(key_id).read_text()
    key = serialization.load_pem_private_key(text.encode(), password=None)
    assert isinstance(key, Ed25519PrivateKey)
    return key


def sign(payload: bytes, key_id: str = "default") -> Signature:
    priv = load_private_key(key_id)
    raw = priv.sign(payload)
    return Signature(format=SIGNATURE_FORMAT_ID, key_id=key_id,
                     value_b64=base64.b64encode(raw).decode())


def verify(payload: bytes, signature: Signature,
           public_key: Ed25519PublicKey | None = None) -> bool:
    if signature.format != SIGNATURE_FORMAT_ID:
        return False
    pub = public_key or load_public_key(signature.key_id)
    try:
        pub.verify(base64.b64decode(signature.value_b64), payload)
        return True
    except (InvalidSignature, ValueError):
        return False


def attach_to_manifest(payload: bytes, signature: Signature) -> dict:
    """Return a manifest dict that bundles payload + signature
    together. The snapshot itself is not wrapped: callers decide
    whether to embed payload_b64 or reference it by digest."""
    return {
        "format": SIGNATURE_FORMAT_ID,
        "key_id": signature.key_id,
        "payload_b64": base64.b64encode(payload).decode(),
        "signature_b64": signature.value_b64,
    }


def verify_manifest(manifest: dict,
                    public_key: Ed25519PublicKey | None = None) -> bool:
    if manifest.get("format") != SIGNATURE_FORMAT_ID:
        return False
    payload = base64.b64decode(manifest["payload_b64"])
    sig = Signature(format=SIGNATURE_FORMAT_ID,
                    key_id=manifest["key_id"],
                    value_b64=manifest["signature_b64"])
    return verify(payload, sig, public_key)
