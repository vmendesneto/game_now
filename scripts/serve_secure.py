"""Explicitly opt in to GN-093 LAN TLS; demo stays loopback-only by default.

Examples are in docs/GN-093.md. Never use a publicly reachable bind without
valid authentication, TLS certificate, and perimeter controls.
"""
from __future__ import annotations

import argparse
from ipaddress import ip_address
from pathlib import Path

from app.network_security import NetworkSecuritySettings


def validate_server(
    host: str, cert: str | None, key: str | None, settings: NetworkSecuritySettings,
) -> None:
    try:
        address = ip_address(host)
    except ValueError as exc:
        raise ValueError("Supply a numeric bind address (127.0.0.1 or a LAN interface)") from exc
    if not address.is_loopback and not settings.remote_access:
        raise ValueError("Non-loopback bind requires GAME_NOW_REMOTE_ACCESS=1")
    if settings.remote_access and (not cert or not key):
        raise ValueError("Remote mode requires both a TLS cert and private key")
    if bool(cert) != bool(key):
        raise ValueError("Specify cert and private key together")
    for value in (cert, key):
        if value is not None and not Path(value).is_file():
            raise ValueError("TLS cert/private key does not exist")


def main() -> None:
    parser = argparse.ArgumentParser(description="Game Now local/TLS server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8000, type=int)
    parser.add_argument("--tls-cert")
    parser.add_argument("--tls-key")
    args = parser.parse_args()
    try:
        settings = NetworkSecuritySettings.from_environment()
        validate_server(args.host, args.tls_cert, args.tls_key, settings)
        if not 1 <= args.port <= 65535:
            raise ValueError("Port must be between 1 and 65535")
    except ValueError as exc:
        parser.exit(2, f"Server configuration error: {exc}\n")
    import uvicorn
    uvicorn.run(
        "app.main:app", host=args.host, port=args.port,
        ssl_certfile=args.tls_cert, ssl_keyfile=args.tls_key,
        proxy_headers=False,
    )


if __name__ == "__main__":
    main()
