#!/usr/bin/env python3
"""Generate the Sigstore client trust configuration release asset.

Snapshots the production Sigstore trust root (Fulcio CAs, CTFE keyring,
Rekor keys, signing config) into a single JSON file so attestation
verification can run hermetically (`sigstore --trust-config <file> ...
--offline`) in air-gapped environments, without the sigstore client's
TUF network bootstrap (docs/v2/24 §5).

The snapshot is taken at release time on a connected machine and shipped
as a release asset; its SHA-256 is pinned in the runtime manifest.

Requires the `sigstore` package (extra `attestation`).

Usage: generate-trust-root.py [--out FILE]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path,
                        default=Path("sigstore-trust-root.json"))
    args = parser.parse_args()

    try:
        from sigstore.models import ClientTrustConfig
    except ImportError:
        print("error: the sigstore package is required to snapshot the "
              "trust root (install the attestation extra: "
              "uv sync --extra attestation)", file=sys.stderr)
        return 1

    config = ClientTrustConfig.production()
    args.out.write_text(config._inner.to_json())
    print(f"trust root written: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
