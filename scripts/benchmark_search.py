"""Small repeatable latency check for the search endpoint."""

import argparse
import json
import math
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlencode
from urllib.request import urlopen


def percentile(values: list[float], value: float) -> float:
    index = max(0, math.ceil(value * len(values)) - 1)
    return sorted(values)[index]


def request(url: str) -> float:
    started = time.perf_counter()
    with urlopen(url, timeout=5) as response:
        if response.status != 200:
            raise RuntimeError(f"Unexpected HTTP {response.status}")
        json.load(response)
    return (time.perf_counter() - started) * 1000


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--query", default="arquitectura")
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=10)
    args = parser.parse_args()
    url = f"{args.base_url.rstrip('/')}/api/documents/search?{urlencode({'q': args.query})}"

    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        timings = list(executor.map(lambda _: request(url), range(args.requests)))

    report = {
        "requests": len(timings),
        "concurrency": args.concurrency,
        "mean_ms": round(statistics.mean(timings), 2),
        "p50_ms": round(percentile(timings, 0.50), 2),
        "p95_ms": round(percentile(timings, 0.95), 2),
        "p99_ms": round(percentile(timings, 0.99), 2),
        "max_ms": round(max(timings), 2),
        "sla_p95_under_1000_ms": percentile(timings, 0.95) <= 1000,
    }
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["sla_p95_under_1000_ms"] else 1)


if __name__ == "__main__":
    main()
