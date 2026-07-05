"""Vendor-side tool: make an Ed25519 keypair and sign client licenses.

This is the OTHER half of core/license.py. It runs on YOUR machine (the vendor),
never ships to the client. The client only ever gets: the app + the public key +
a signed token.

USAGE
-----
1) One-time — create a signing keypair. Keep the private key SECRET.
       python -m tools.gen_license keygen --out-dir ./keys
   -> ./keys/license_priv.pem  (secret — never commit / never ship)
      ./keys/license_pub.pem   (safe — bundle this with every app build)

2) Per client — sign a license token.
       python -m tools.gen_license sign \
           --key ./keys/license_priv.pem \
           --client HCL --days 365 \
           --modules attendance,transit,investigations \
           --cameras 10 --recognition-cameras 6 --storage-gb 500 \
           --feature age_gender --feature export
   -> prints the JWT. Hand it to the client as VE_LICENSE_TOKEN / a file.

Requires: pyjwt[crypto], cryptography  (already in pyproject).
"""

from __future__ import annotations

import argparse
import datetime as dt
from pathlib import Path

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def cmd_keygen(args: argparse.Namespace) -> None:
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    priv = Ed25519PrivateKey.generate()
    priv_pem = priv.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub_pem = priv.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    (out / "license_priv.pem").write_bytes(priv_pem)
    (out / "license_pub.pem").write_bytes(pub_pem)
    print(f"wrote {out/'license_priv.pem'} (SECRET) and {out/'license_pub.pem'} (ship this)")


def cmd_sign(args: argparse.Namespace) -> None:
    private_key = Path(args.key).read_text()
    now = dt.datetime.now(dt.timezone.utc)

    limits: dict = {}
    if args.cameras is not None:
        limits["cameras"] = args.cameras
    if args.recognition_cameras is not None:
        limits["recognition_cameras"] = args.recognition_cameras
    if args.storage_gb is not None:
        limits["storage_gb"] = args.storage_gb

    payload = {
        "client": args.client,
        "iat": now,
        "exp": now + dt.timedelta(days=args.days),
        "modules": [m.strip() for m in args.modules.split(",") if m.strip()],
        "limits": limits,
        "features": {name: True for name in (args.feature or [])},
    }
    token = jwt.encode(payload, private_key, algorithm="EdDSA")
    print(token)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate/sign Vizor scenario-app licenses.")
    sub = parser.add_subparsers(dest="command", required=True)

    kg = sub.add_parser("keygen", help="create an Ed25519 signing keypair")
    kg.add_argument("--out-dir", default="./keys")
    kg.set_defaults(func=cmd_keygen)

    sg = sub.add_parser("sign", help="sign a client license token")
    sg.add_argument("--key", required=True, help="path to license_priv.pem")
    sg.add_argument("--client", required=True)
    sg.add_argument("--days", type=int, default=365)
    sg.add_argument("--modules", default="", help="comma-separated module ids")
    sg.add_argument("--cameras", type=int)
    sg.add_argument("--recognition-cameras", type=int)
    sg.add_argument("--storage-gb", type=float)
    sg.add_argument("--feature", action="append", help="repeatable feature flag, e.g. --feature age_gender")
    sg.set_defaults(func=cmd_sign)

    return parser


if __name__ == "__main__":
    ns = build_parser().parse_args()
    ns.func(ns)
