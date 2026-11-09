#!/usr/bin/env python3
"""Create/update the backend Kubernetes Secret from the repository's ignored .env file."""

import base64
import subprocess
import sys
from pathlib import Path

from dotenv import dotenv_values

REPO_ROOT = Path(__file__).resolve().parents[1]
SECRET_KEYS = (
    "ORGANIZER_API_KEY",
    "OPENROUTER_API_KEY",
    "ES_API_KEY",
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "OTEL_EXPORTER_OTLP_HEADERS",
)


def main() -> int:
    env_file = REPO_ROOT / ".env"
    if not env_file.is_file():
        print("Missing .env; copy .env.example and fill in the required keys first.", file=sys.stderr)
        return 1

    values = dotenv_values(env_file)
    missing = [key for key in SECRET_KEYS[:2] if not values.get(key)]
    if missing:
        print(f"Missing required .env variable(s): {', '.join(missing)}", file=sys.stderr)
        return 1

    data = {
        key: base64.b64encode(value.encode()).decode("ascii")
        for key in SECRET_KEYS
        if (value := values.get(key))
    }
    manifest = "\n".join(
        [
            "apiVersion: v1",
            "kind: Secret",
            "metadata:",
            "  name: wemakedevs2026-backend-secrets",
            "type: Opaque",
            "data:",
            *(f"  {key}: {value}" for key, value in data.items()),
            "",
        ]
    )
    result = subprocess.run(
        ["kubectl", "apply", "-f", "-"],
        input=manifest,
        text=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if result.returncode:
        print("kubectl could not create the backend Secret.", file=sys.stderr)
        return result.returncode
    print("Backend Kubernetes Secret updated from .env.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
