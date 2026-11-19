"""Post-deployment smoke test for public web readiness and a live worker."""
import json
import os
import sys
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def check_endpoint(base_url, path):
    request = Request(base_url.rstrip("/") + path,
                      headers={"User-Agent": "AI-Workforce-Release-Smoke/1.0"})
    with urlopen(request, timeout=10) as response:
        payload = json.loads(response.read().decode("utf-8"))
        if response.status != 200:
            raise RuntimeError(f"{path} returned HTTP {response.status}")
        if payload.get("status") not in {"ok", "ready"}:
            raise RuntimeError(f"{path} returned unexpected status: {payload!r}")
        return payload


def main():
    base_url = os.environ.get("PUBLIC_BASE_URL")
    if not base_url or not base_url.startswith("https://"):
        raise SystemExit("Set PUBLIC_BASE_URL to the deployed HTTPS origin.")
    health = check_endpoint(base_url, "/healthz")
    ready = check_endpoint(base_url, "/readyz")
    print(f"Public health endpoint: OK ({health.get('service', 'service')})")
    print(f"Public readiness endpoint: OK ({ready})")
    from scripts.check_worker import main as check_worker
    check_worker()
    print("Release smoke test passed.")


if __name__ == "__main__":
    main()
