#!/usr/bin/env python3
"""Small authenticated read-load benchmark for a pre-production BHUMI-X API."""
import argparse
import concurrent.futures
import getpass
import json
import math
import os
import time
import urllib.error
import urllib.request


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, math.ceil(q * len(ordered)) - 1)] if ordered else 0.0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--email", default=os.getenv("BHUMIX_BENCH_EMAIL"))
    parser.add_argument("--iterations", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=8)
    args = parser.parse_args()
    if args.iterations < 1 or args.concurrency < 1:
        parser.error("iterations and concurrency must be positive")
    email = args.email or input("Benchmark user email: ")
    password = getpass.getpass("Benchmark user password: ")
    base = args.base_url.rstrip("/")
    login_request = urllib.request.Request(
        base + "/api/auth/login", data=json.dumps({"email": email, "password": password}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(login_request, timeout=30) as response:
        token = json.load(response)["access_token"]
    endpoints = ["/api/statistics", "/api/parcels?limit=2000", "/api/matches?limit=3000"]
    calls = [endpoints[index % len(endpoints)] for index in range(args.iterations)]

    def call(path):
        request = urllib.request.Request(base + path, headers={"Authorization": f"Bearer {token}"})
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                response.read()
                return (time.perf_counter() - started) * 1000, response.status
        except urllib.error.HTTPError as error:
            error.read()
            return (time.perf_counter() - started) * 1000, error.code

    started = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        results = list(executor.map(call, calls))
    elapsed = time.perf_counter() - started
    latencies = [latency for latency, status in results]
    failures = sum(status >= 400 for _, status in results)
    print(f"requests: {len(results)} | concurrency: {args.concurrency} | elapsed: {elapsed:.2f}s | throughput: {len(results) / elapsed:.2f} req/s")
    print(f"latency ms: p50={percentile(latencies, .50):.1f} p95={percentile(latencies, .95):.1f} p99={percentile(latencies, .99):.1f} max={max(latencies, default=0):.1f}")
    print(f"http failures: {failures}")
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
