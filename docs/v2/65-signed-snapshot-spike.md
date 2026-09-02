# V2.4 M3 slice 12 — Signed snapshot spike

Status: spike, not a feature. Ships a working Ed25519 sign/verify
prototype for snapshot attestation and a clear list of what is
deliberately out of scope. The gate wiring (sign every snapshot at
production time, verify in CI) is a follow-up slice once a project
decides who holds the private key.

## Decision

- **Algorithm**: Ed25519 via `cryptography`. Asymmetric so CI only
  needs the public key; no KMS or shared secret distribution.
- **Library**: `cryptography>=42`, already optional in the
  `attestation` extra. No new runtime dependency.
- **Signature form**: detached signature over the canonical JSON
  bytes of the snapshot. Format id `arch-skillkit/sig-v1`.
- **Key storage**: PEM files under
  `XDG_STATE_HOME/arch-skillkit/signing/{key_id}.{priv,pub}.pem`.
  Private key file mode 0o600.
- **Manifest**: the spike ships a `attach_to_manifest` helper that
  bundles `{format, key_id, payload_b64, signature_b64}`. This is
  what a future CI step would attach next to the snapshot artifact.

## What the spike proves

- `signed_snapshot.py` exposes `generate_keypair`, `sign`,
  `verify`, `attach_to_manifest`, `verify_manifest` as pure
  functions; the roundtrip is covered by `tests/test_signed_snapshot.py`.
- Tampered payload and wrong public key both fail verification.
- Private key file is mode 0o600 on disk.
- Same `format` id is the only one accepted by `verify` (forward-
  compatible versioning: a future `v2` would live alongside, not
  overwrite).

## What is intentionally NOT in the spike

- **CI wiring**: no GitHub Action / workflow yet. The CI step would
  consume `attach_to_manifest` and post the manifest to the PR.
- **Key distribution**: where does the public key live? Options are
  a repo-managed `.archskillkit/keys/`, the run ledger, or a
  separate signed-keys bucket. This is a policy decision the spike
  does not take.
- **Rotation**: no rotation policy, no overlapping key ids. The
  prototype supports multiple `key_id`s via the filename scheme,
  but does not enforce any rotation cadence.
- **Revocation**: nothing yet. Without a transparency log or a
  revocation list, a leaked private key stays valid until the
  verifier is rotated.
- **Transparency log**: Rekor / Sigstore is already an optional
  extra (`sigstore>=3.6`). The spike does not push to it; that is a
  separate decision because pushing to a public log leaks the
  fact that a snapshot exists.
- **Post-quantum**: not addressed. Ed25519 is classical; if the
  project needs PQ-readiness now, the format id would have to
  accommodate a hybrid signature (e.g. Ed25519 + ML-DSA) and the
  public key bundle would carry both. Out of scope for the spike.

## Threat model (informal)

- Adversary who can write to the world store can produce a
  snapshot. They cannot produce a valid signature without the
  private key. Verification at the consumer end gives integrity
  and authenticity of the snapshot bytes.
- Adversary who can read `XDG_STATE_HOME` can exfiltrate the
  private key. Mitigation is out-of-process storage (KMS / HSM),
  not in the spike.
- Adversary who can rewrite the snapshot and its manifest together
  cannot produce a matching signature. The verification step
  catches this by re-deriving the digest.

## Acceptance

- [x] Sign/verify roundtrip works.
- [x] Tamper detection works.
- [x] Key material persists with restrictive mode.
- [x] Decision documented in this file.
- [ ] CI integration (next slice once key policy is decided).
- [ ] Rotation / revocation policy (separate ADR).
