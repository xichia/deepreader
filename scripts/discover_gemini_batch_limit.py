"""
Manual-only Synthetic Gemini Batch Limit Discovery Script.

WARNING: This consumes live Gemini quota when provider-backed summaries are enabled.
This script is for manual execution only and must not be run as part of the automated build.
Ensure sufficient quota headroom before running.

Terminal 1 (paragraph-summary-service):
  Must already be running with:
    SUMMARY_SERVICE_PROVIDER=gemini \\
    SUMMARY_SERVICE_MODEL=gemini-3.1-flash-lite \\
    SUMMARY_SERVICE_ENABLE_PROVIDER_CALLS=true \\
    SUMMARY_MAX_PROVIDER_CALLS_PER_JOB=1 \\
    SUMMARY_BATCH_MAX_RECORDS=32 \\ (or at least the largest size in --sizes)
    SUMMARY_LANE_RPM=15 \\
    PYTHONPATH=services/paragraph-summary-service \\
    uv run --project services/paragraph-summary-service uvicorn app.main:app --host 127.0.0.1 --port 8001

Usage command example:
  uv run --with 'httpx>=0.27' python scripts/discover_gemini_batch_limit.py --sizes 12,16,20,24 --profile textbook-hard --words-per-record 180
"""

import argparse
import subprocess
import sys
import time

def str_to_bool(v):
    if isinstance(v, bool):
        return v
    if v.lower() in ('yes', 'true', 't', 'y', '1'):
        return True
    elif v.lower() in ('no', 'false', 'f', 'n', '0'):
        return False
    else:
        raise argparse.ArgumentTypeError('Boolean value expected.')

def main():
    parser = argparse.ArgumentParser(description="Discover Gemini Batch Limit")
    parser.add_argument("--sizes", type=str, default="12,16,20,24,32")
    parser.add_argument("--profile", type=str, default="textbook-hard")
    parser.add_argument("--words-per-record", type=int, default=180)
    parser.add_argument("--expected-provider", type=str, default="gemini")
    parser.add_argument("--expected-model", type=str, default="gemini-3.1-flash-lite")
    parser.add_argument("--base-url", type=str, default="http://127.0.0.1:8001")
    parser.add_argument("--require-zero-429", type=str_to_bool, default=True)
    parser.add_argument("--python", type=str, default=sys.executable)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--sleep-between", type=float, default=2.0)
    args = parser.parse_args()

    sizes = [int(s.strip()) for s in args.sizes.split(",") if s.strip()]
    if not sizes:
        print("FAIL: No sizes provided.")
        sys.exit(1)

    attempted_sizes = []
    passed_sizes = []
    first_failed_size = None

    print(f"Starting batch limit discovery ladder: {sizes}")
    print(f"Profile: {args.profile}, Words per record: {args.words_per_record}")
    print(f"Targeting: {args.expected_provider}/{args.expected_model} at {args.base_url}")
    print("--------------------------------------------------------------------------------")

    for i, size in enumerate(sizes):
        if i > 0 and args.sleep_between > 0:
            print(f"\nSleeping for {args.sleep_between}s between sizes...")
            time.sleep(args.sleep_between)

        print(f"\n>>> Evaluating batch size: {size}")
        attempted_sizes.append(size)

        cmd = [
            args.python,
            "scripts/canary_gemini_batch_escalation.py",
            "--total-records", str(size),
            "--profile", args.profile,
            "--words-per-record", str(args.words_per_record),
            "--expected-provider", args.expected_provider,
            "--expected-model", args.expected_model,
            "--max-provider-calls", "1",
            "--base-url", args.base_url,
            "--require-zero-429", "true" if args.require_zero_429 else "false"
        ]

        # Stream stdout/stderr so the user sees results live
        res = subprocess.run(cmd, stdout=sys.stdout, stderr=sys.stderr)

        if res.returncode == 0:
            passed_sizes.append(size)
            print(f"SUCCESS: Batch size {size} passed.")
        else:
            first_failed_size = size
            print(f"FAILURE: Batch size {size} failed.")
            break

    highest_passed = max(passed_sizes) if passed_sizes else None

    print("\n================================================================================")
    print("BATCH LIMIT DISCOVERY SUMMARY")
    print("================================================================================")
    print(f"Attempted batch sizes:  {attempted_sizes}")
    print(f"Passed batch sizes:     {passed_sizes}")
    print(f"First failed batch size: {first_failed_size}")
    print(f"Highest passed batch size: {highest_passed}")
    print(f"Profile:                {args.profile}")
    print(f"Words per record:       {args.words_per_record}")
    print(f"Expected provider/model: {args.expected_provider}/{args.expected_model}")
    print("================================================================================")

    # Exits nonzero if the first attempted batch size fails
    if first_failed_size == sizes[0]:
        print("FAIL: The first attempted batch size failed.")
        sys.exit(1)

    # If strict flag is enabled, exit nonzero on any failure
    if args.strict and first_failed_size is not None:
        print("FAIL: Failure encountered in strict mode.")
        sys.exit(1)

    if first_failed_size is not None:
        print(f"INFO: Limit found. Highest passed batch size: {highest_passed}")
    else:
        print("INFO: All attempted batch sizes passed.")

    sys.exit(0)

if __name__ == "__main__":
    main()
