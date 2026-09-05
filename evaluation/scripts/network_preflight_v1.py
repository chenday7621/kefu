#!/usr/bin/env python3
"""Diagnose model-endpoint reachability without sending credentials or payloads."""
from __future__ import annotations

import argparse
import json
import os
import socket
import ssl
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]


def configured_hosts() -> tuple[list[str], bool]:
    gateway = dotenv_values(ROOT / "gateway/.env")
    retrieval = dotenv_values(ROOT / "retrieval/.env")
    urls = [
        gateway.get("UPSTREAM_1_BASE_URL"),
        retrieval.get("KAFU_LLM_BASE_URL"),
    ]
    hosts = sorted({urlparse(value or "").hostname for value in urls if urlparse(value or "").hostname})
    alternate = bool(gateway.get("UPSTREAM_2_BASE_URL") and gateway.get("UPSTREAM_2_API_KEY"))
    return hosts, alternate


def transport_probe(host: str, timeout: float) -> dict:
    addresses = sorted({item[4][0] for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)})
    result = {
        "host": host,
        "port": 443,
        "addresses": addresses,
        "tcp_status": "not_run",
        "tls_status": "not_run",
        "error": None,
    }
    try:
        with socket.create_connection((host, 443), timeout=timeout) as raw:
            result["tcp_status"] = "pass"
            raw.settimeout(timeout)
            context = ssl.create_default_context()
            with context.wrap_socket(raw, server_hostname=host):
                result["tls_status"] = "pass"
    except Exception as exc:
        failed_stage = "TLS handshake" if result["tcp_status"] == "pass" else "TCP connection"
        result["error"] = f"{type(exc).__name__}: {failed_stage} unavailable"
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=8.0)
    args = parser.parse_args()
    if args.attempts < 1:
        parser.error("--attempts must be at least 1")
    hosts, alternate = configured_hosts()
    probes = [
        {
            "host": host,
            "attempts": [transport_probe(host, args.timeout) for _ in range(args.attempts)],
        }
        for host in hosts
    ]
    proxy_names = ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy")
    report = {
        "schema_version": "network-preflight-v1",
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "credential_or_payload_sent": False,
        "proxy_environment": {name: bool(os.getenv(name)) for name in proxy_names},
        "alternate_upstream_configured": alternate,
        "probes": probes,
        "policy": "all configured hosts must pass every TLS attempt",
        "status": "pass"
        if probes
        and all(
            all(attempt["tls_status"] == "pass" for attempt in host_probe["attempts"])
            for host_probe in probes
        )
        else "fail",
    }
    out = ROOT / "evaluation/results/baseline_v1/preflight/network_egress.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
