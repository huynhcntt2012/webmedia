"""Bounded read-only HTTP load check; local/private targets only."""
import argparse
import ipaddress
import json
import math
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import urlopen


def local_origin(value):
    parsed = urlsplit(value)
    try:
        permitted = parsed.hostname == "localhost" or ipaddress.ip_address(parsed.hostname).is_private
    except ValueError:
        permitted = False
    if not permitted or parsed.scheme != "http" or parsed.path or parsed.username or parsed.query or parsed.fragment:
        raise argparse.ArgumentTypeError("Use an explicit local/private HTTP origin")
    return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--origin", type=local_origin, default="http://127.0.0.1:3000")
    parser.add_argument("--requests", type=int, choices=range(1, 1001), default=200)
    parser.add_argument("--concurrency", type=int, choices=range(1, 21), default=5)
    parser.add_argument("--p95-ms", type=float, default=2000)
    args = parser.parse_args()

    def read(index):
        start = time.monotonic()
        try:
            path = ["/", "/movies", "/comics", "/health/live"][index % 4]
            with urlopen(args.origin + path, timeout=10) as response:
                response.read()
                ok = response.status == 200
        except (URLError, TimeoutError, OSError):
            ok = False
        return ok, (time.monotonic() - start) * 1000

    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        results = list(pool.map(read, range(args.requests)))
    p95 = sorted(ms for _, ms in results)[math.ceil(len(results) * .95) - 1]
    errors = sum(not ok for ok, _ in results)
    print(json.dumps({"requests": args.requests, "concurrency": args.concurrency,
                      "errors": errors, "p95_ms": round(p95, 2),
                      "elapsed_s": round(time.monotonic()-started, 2)}))
    raise SystemExit(0 if errors == 0 and p95 <= args.p95_ms else 1)


if __name__ == "__main__":
    main()
