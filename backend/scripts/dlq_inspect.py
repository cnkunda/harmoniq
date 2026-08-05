"""CLI tool for inspecting and managing the Harmoniq dead-letter queue.

Usage:
    python scripts/dlq_inspect.py list [--limit N]
    python scripts/dlq_inspect.py inspect INDEX
    python scripts/dlq_inspect.py requeue INDEX
    python scripts/dlq_inspect.py clear
    python scripts/dlq_inspect.py stats
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Add backend root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def cmd_list(args: argparse.Namespace) -> None:
    """List all DLQ entries."""
    from app.dead_letter import inspect_dlq

    entries = inspect_dlq(limit=args.limit)
    if not entries:
        print("Dead-letter queue is empty.")
        return

    print(f"Dead-letter queue ({len(entries)} entries):\n")
    for i, entry in enumerate(entries):
        print(f"  [{i}] job_id={entry.get('job_id', '?')}")
        print(f"      error={entry.get('error', '?')}")
        print(f"      error_code={entry.get('error_code', '?')}")
        print(f"      retry_count={entry.get('retry_count', 0)}")
        print(f"      failed_at={entry.get('failed_at', '?')}")
        print()


def cmd_inspect(args: argparse.Namespace) -> None:
    """Inspect a single DLQ entry in detail."""
    from app.dead_letter import inspect_dlq

    entries = inspect_dlq(limit=args.index + 1)
    if args.index >= len(entries):
        print(f"Error: index {args.index} out of range (queue has {len(entries)} entries)")
        sys.exit(1)

    entry = entries[args.index]
    print(json.dumps(entry, indent=2))


def cmd_requeue(args: argparse.Namespace) -> None:
    """Requeue a DLQ entry for reprocessing."""
    from app.dead_letter import requeue_from_dlq

    entry = requeue_from_dlq(index=args.index)
    if entry is None:
        print(f"Error: could not requeue index {args.index}")
        sys.exit(1)

    job_id = entry.get("job_id")
    job_data = entry.get("job_data")
    print(f"Requeued job_id={job_id}")

    if job_data:
        print(f"Original parameters: {json.dumps(job_data, indent=2)}")
        print("\nTo reprocess, run:")
        print(f"  python -c \"from app.tasks import process_analyze_job; process_analyze_job.delay('{job_id}', **{json.dumps(job_data)})\"")


def cmd_clear(args: argparse.Namespace) -> None:
    """Clear all DLQ entries."""
    from app.dead_letter import clear_dlq

    count = clear_dlq()
    print(f"Cleared {count} entries from dead-letter queue.")


def cmd_stats(args: argparse.Namespace) -> None:
    """Show DLQ statistics."""
    from app.dead_letter import dlq_length, inspect_dlq

    length = dlq_length()
    entries = inspect_dlq(limit=100)

    print(f"Dead-letter queue statistics:")
    print(f"  Total entries: {length}")

    if entries:
        # Error code distribution
        error_codes: dict[str, int] = {}
        for entry in entries:
            code = entry.get("error_code", "unknown")
            error_codes[code] = error_codes.get(code, 0) + 1

        print(f"\n  Error code distribution:")
        for code, count in sorted(error_codes.items(), key=lambda x: -x[1]):
            print(f"    {code}: {count}")

        # Retry count distribution
        retry_counts = [entry.get("retry_count", 0) for entry in entries]
        print(f"\n  Retry counts:")
        print(f"    min={min(retry_counts)} max={max(retry_counts)} avg={sum(retry_counts)/len(retry_counts):.1f}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Harmoniq DLQ Inspector")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # list
    list_parser = subparsers.add_parser("list", help="List DLQ entries")
    list_parser.add_argument("--limit", type=int, default=20, help="Max entries to show")

    # inspect
    inspect_parser = subparsers.add_parser("inspect", help="Inspect a single DLQ entry")
    inspect_parser.add_argument("index", type=int, help="Entry index")

    # requeue
    requeue_parser = subparsers.add_parser("requeue", help="Requeue a DLQ entry")
    requeue_parser.add_argument("index", type=int, help="Entry index to requeue")

    # clear
    subparsers.add_parser("clear", help="Clear all DLQ entries")

    # stats
    subparsers.add_parser("stats", help="Show DLQ statistics")

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        sys.exit(1)

    commands = {
        "list": cmd_list,
        "inspect": cmd_inspect,
        "requeue": cmd_requeue,
        "clear": cmd_clear,
        "stats": cmd_stats,
    }
    commands[args.command](args)


if __name__ == "__main__":
    main()
