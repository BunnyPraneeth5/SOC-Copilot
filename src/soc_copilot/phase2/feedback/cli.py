"""Sprint-8 Feedback CLI commands.

Provides CLI interface for recording and querying analyst feedback.
"""

import argparse
import sys
from pathlib import Path

from soc_copilot.phase2.feedback.store import FeedbackStore
from soc_copilot.core.logging import get_logger

logger = get_logger(__name__)


def setup_feedback_parser() -> argparse.ArgumentParser:
    """Set up feedback CLI parser."""
    parser = argparse.ArgumentParser(
        prog="soc-copilot-feedback",
        description="SOC Copilot Feedback Management (Sprint-8)",
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Add command
    add_parser = subparsers.add_parser("add", help="Record feedback for an alert")
    add_parser.add_argument("--alert-id", required=True, help="Alert ID")
    add_parser.add_argument(
        "--action",
        required=True,
        choices=["accept", "reject", "reclassify"],
        help="Analyst action"
    )
    add_parser.add_argument("--label", help="New label (required if reclassify)")
    add_parser.add_argument("--comment", help="Optional comment")
    
    # Stats command
    stats_parser = subparsers.add_parser("stats", help="Show feedback statistics")
    
    return parser


def cmd_add(args, store: FeedbackStore) -> int:
    """Add feedback record."""
    if args.action == "reclassify" and not args.label:
        print("Error: --label is required when action is 'reclassify'")
        return 1
    
    record_id = store.add_feedback(
        alert_id=args.alert_id,
        analyst_action=args.action,
        analyst_label=args.label,
        comment=args.comment,
    )
    
    print(f"Feedback recorded (ID: {record_id})")
    print(f"  Alert: {args.alert_id}")
    print(f"  Action: {args.action}")
    if args.label:
        print(f"  Label: {args.label}")
    
    return 0


def cmd_stats(args, store: FeedbackStore) -> int:
    """Show feedback statistics."""
    stats = store.get_feedback_stats()
    
    print("\nFeedback Statistics")
    print("=" * 40)
    print(f"Total: {stats.total_count}")
    print(f"  Accept: {stats.accept_count}")
    print(f"  Reject: {stats.reject_count}")
    print(f"  Reclassify: {stats.reclassify_count}")
    
    if stats.by_label:
        print(f"\nReclassified Labels:")
        for label, count in sorted(stats.by_label.items(), key=lambda x: -x[1]):
            print(f"  {label}: {count}")
    
    print()
    return 0


def main() -> int:
    """Main entry point."""
    parser = setup_feedback_parser()
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 0
    
    # Initialize store
    store = FeedbackStore()
    store.initialize()
    
    try:
        if args.command == "add":
            return cmd_add(args, store)
        elif args.command == "stats":
            return cmd_stats(args, store)
        else:
            print(f"Unknown command: {args.command}")
            return 1
    finally:
        store.close()


if __name__ == "__main__":
    sys.exit(main())
