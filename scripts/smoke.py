"""Read-only smoke checks against a running development Docker stack."""

import json
from urllib.request import urlopen


def main() -> None:
    for url in (
        "http://localhost:8000/health/live",
        "http://localhost:8000/health/ready",
        "http://localhost:3000/health/live",
    ):
        with urlopen(url, timeout=10) as response:
            data = json.load(response)
            if response.status != 200 or data.get("status") != "ok":
                raise SystemExit(f"FAIL {url}")
        print(f"PASS {url}")
    with urlopen("http://localhost:3000", timeout=15) as response:
        html = response.read().decode("utf-8")
        if "Mới trong thư viện" not in html or "Thư viện đang gián đoạn" in html:
            raise SystemExit("FAIL web cannot reach catalogue API")
    print("PASS web connects to API, PostgreSQL and Redis")


if __name__ == "__main__":
    main()
