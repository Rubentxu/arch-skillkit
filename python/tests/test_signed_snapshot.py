"""Signed snapshot prototype (V2.4 M3 spike, docs/v2/65).

Spike scope: roundtrip sign/verify works; tampering is detected;
key material persists under XDG_STATE_HOME/signing with restrictive
file modes.

Out of scope for the spike (documented in docs/v2/65): CI integration,
key distribution, rotation, revocation, transparency log, post-quantum.
"""

import base64
import os

import pytest

from archskillkit.attestation.signed_snapshot import (
    SIGNATURE_FORMAT_ID,
    Signature,
    attach_to_manifest,
    generate_keypair,
    sign,
    verify,
    verify_manifest,
)


@pytest.fixture()
def key(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    return generate_keypair("test")


class TestSignedSnapshot:
    def test_roundtrip(self, key):
        payload = b'{"schema":"arch-skillkit/x","v":1}'
        sig = sign(payload, key_id="test")
        assert sig.format == SIGNATURE_FORMAT_ID
        assert verify(payload, sig, public_key=key) is True

    def test_tampered_payload_fails(self, key):
        payload = b'{"v":1}'
        sig = sign(payload, key_id="test")
        tampered = b'{"v":2}'
        assert verify(tampered, sig, public_key=key) is False

    def test_wrong_key_fails(self, key):
        other = generate_keypair("other")
        payload = b"x"
        sig = sign(payload, key_id="test")
        assert verify(payload, sig, public_key=other) is False

    def test_unknown_format_rejected(self, key):
        payload = b"x"
        sig = sign(payload, key_id="test")
        bad = Signature(format="other/v1", key_id=sig.key_id,
                        value_b64=sig.value_b64)
        assert verify(payload, bad, public_key=key) is False

    def test_manifest_roundtrip(self, key):
        payload = b'{"snapshot":true}'
        sig = sign(payload, key_id="test")
        manifest = attach_to_manifest(payload, sig)
        assert verify_manifest(manifest, public_key=key) is True
        # tampered manifest payload
        manifest["payload_b64"] = base64.b64encode(b'{"snapshot":false}'
                                                   ).decode()
        assert verify_manifest(manifest, public_key=key) is False

    def test_private_key_is_mode_600(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
        generate_keypair("test")
        priv_path = (tmp_path / "state" / "arch-skillkit"
                     / "signing" / "test.priv.pem")
        assert priv_path.exists()
        assert oct(os.stat(priv_path).st_mode & 0o777) == "0o600"
