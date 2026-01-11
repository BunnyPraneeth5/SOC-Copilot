#!/usr/bin/env python3
"""SOC Copilot CLI - Command-line interface for log analysis.

Usage:
    python -m soc_copilot.cli analyze <path> [options]
    python -m soc_copilot.cli status
    
Examples:
    python -m soc_copilot.cli analyze logs/access.log
    python -m soc_copilot.cli analyze logs/ --recursive
    python -m soc_copilot.cli analyze logs/suspicious.json --verbose
"""

import argparse
import sys
import json
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root / "src"))

from soc_copilot.pipeline import SOCCopilot, SOCCopilotConfig, create_soc_copilot
from soc_copilot.models.ensemble import format_alert_summary, RiskLevel
from soc_copilot.core.logging import get_logger
from soc_copilot.phase2.feedback.store import FeedbackStore

logger = get_logger(__name__)


def setup_parser() -> argparse.ArgumentParser:
    """Set up argument parser."""
    parser = argparse.ArgumentParser(
        prog="soc-copilot",
        description="SOC Copilot - AI-Powered Security Log Analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Analyze a single log file:
    python -m soc_copilot.cli analyze logs/access.log

  Analyze a directory recursively:
    python -m soc_copilot.cli analyze logs/ --recursive

  Output alerts as JSON:
    python -m soc_copilot.cli analyze logs/ --output-format json

  Only show high priority alerts:
    python -m soc_copilot.cli analyze logs/ --min-priority P2-Medium
""",
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Analyze command
    analyze_parser = subparsers.add_parser(
        "analyze",
        help="Analyze log files for security threats",
    )
    analyze_parser.add_argument(
        "path",
        type=str,
        help="Path to log file or directory",
    )
    analyze_parser.add_argument(
        "--recursive", "-r",
        action="store_true",
        help="Recursively search directories",
    )
    analyze_parser.add_argument(
        "--models-dir",
        type=str,
        default="data/models",
        help="Path to trained models directory",
    )
    analyze_parser.add_argument(
        "--output-format",
        choices=["text", "json", "summary"],
        default="text",
        help="Output format for results",
    )
    analyze_parser.add_argument(
        "--min-priority",
        choices=["P0-Critical", "P1-High", "P2-Medium", "P3-Low", "P4-Info"],
        default="P4-Info",
        help="Minimum alert priority to display",
    )
    analyze_parser.add_argument(
        "--output-file",
        type=str,
        help="Write output to file instead of stdout",
    )
    analyze_parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed output",
    )
    analyze_parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Only show alerts, no progress",
    )
    
    # Status command
    status_parser = subparsers.add_parser(
        "status",
        help="Show pipeline status and configuration",
    )
    status_parser.add_argument(
        "--models-dir",
        type=str,
        default="data/models",
        help="Path to trained models directory",
    )
    
    # Feedback command
    feedback_parser = subparsers.add_parser(
        "feedback",
        help="Manage analyst feedback on alerts",
    )
    feedback_subparsers = feedback_parser.add_subparsers(dest="feedback_command")
    
    # Feedback add
    feedback_add = feedback_subparsers.add_parser("add", help="Record feedback")
    feedback_add.add_argument("--alert-id", required=True, help="Alert ID")
    feedback_add.add_argument(
        "--action",
        required=True,
        choices=["accept", "reject", "reclassify"],
        help="Analyst action"
    )
    feedback_add.add_argument("--label", help="New label (required if reclassify)")
    feedback_add.add_argument("--comment", help="Optional comment")
    
    # Feedback stats
    feedback_stats = feedback_subparsers.add_parser("stats", help="Show statistics")
    
    return parser


def priority_order(priority_str: str) -> int:
    """Get numeric order for priority (lower = more urgent)."""
    order = {
        "P0-Critical": 0,
        "P1-High": 1,
        "P2-Medium": 2,
        "P3-Low": 3,
        "P4-Info": 4,
    }
    return order.get(priority_str, 5)


def cmd_analyze(args) -> int:
    """Run analyze command."""
    path = Path(args.path)
    
    if not path.exists():
        print(f"Error: Path not found: {path}", file=sys.stderr)
        return 1
    
    # Load pipeline
    if not args.quiet:
        print(f"Loading SOC Copilot models from {args.models_dir}...")
    
    try:
        copilot = create_soc_copilot(args.models_dir)
    except Exception as e:
        print(f"Error loading models: {e}", file=sys.stderr)
        return 1
    
    if not args.quiet:
        print(f"Models loaded. Feature count: {len(copilot._feature_order)}")
        print(f"\nAnalyzing: {path}")
        print("-" * 60)
    
    # Run analysis
    if path.is_file():
        results, alerts, stats = copilot.analyze_file(path)
    else:
        results, alerts, stats = copilot.analyze_directory(path, recursive=args.recursive)
    
    # Filter alerts by priority
    min_priority = priority_order(args.min_priority)
    filtered_alerts = [
        a for a in alerts
        if priority_order(a.priority.value) <= min_priority
    ]
    
    # Output results
    output_lines = []
    
    if args.output_format == "json":
        output_data = {
            "timestamp": datetime.now().isoformat(),
            "path": str(path),
            "stats": stats.to_dict(),
            "alerts": [
                {
                    "alert_id": a.alert_id,
                    "priority": a.priority.value,
                    "risk_level": a.risk_level.value,
                    "threat_category": a.threat_category.value,
                    "classification": a.classification,
                    "confidence": a.classification_confidence,
                    "anomaly_score": a.anomaly_score,
                    "risk_score": a.combined_risk_score,
                    "reasoning": a.reasoning,
                    "suggested_action": a.suggested_action,
                    "source_ip": a.source_ip,
                    "destination_ip": a.destination_ip,
                    "mitre_tactics": a.mitre_tactics,
                    "mitre_techniques": a.mitre_techniques,
                }
                for a in filtered_alerts
            ],
        }
        output_lines.append(json.dumps(output_data, indent=2))
        
    elif args.output_format == "summary":
        output_lines.append("\n" + "=" * 60)
        output_lines.append("SOC COPILOT ANALYSIS SUMMARY")
        output_lines.append("=" * 60)
        output_lines.append(f"\nPath: {path}")
        output_lines.append(f"Timestamp: {datetime.now().isoformat()}")
        output_lines.append(f"\nRecords Analyzed: {stats.processed_records}/{stats.total_records}")
        output_lines.append(f"Alerts Generated: {len(filtered_alerts)}")
        output_lines.append(f"\nRisk Distribution:")
        for level, count in stats.risk_distribution.items():
            pct = count / max(stats.processed_records, 1) * 100
            output_lines.append(f"  {level}: {count} ({pct:.1f}%)")
        output_lines.append(f"\nClassification Distribution:")
        for cls, count in sorted(stats.classification_distribution.items(), key=lambda x: -x[1]):
            pct = count / max(stats.processed_records, 1) * 100
            output_lines.append(f"  {cls}: {count} ({pct:.1f}%)")
        
        if filtered_alerts:
            output_lines.append(f"\nAlert Summary:")
            output_lines.append("-" * 40)
            priority_counts = {}
            for a in filtered_alerts:
                p = a.priority.value
                priority_counts[p] = priority_counts.get(p, 0) + 1
            for p in ["P0-Critical", "P1-High", "P2-Medium", "P3-Low", "P4-Info"]:
                if p in priority_counts:
                    output_lines.append(f"  {p}: {priority_counts[p]}")
        
    else:  # text format
        if not args.quiet:
            output_lines.append(f"\nAnalysis complete.")
            output_lines.append(f"Records: {stats.processed_records}/{stats.total_records}")
            output_lines.append(f"Alerts: {len(filtered_alerts)}")
        
        if filtered_alerts:
            output_lines.append(f"\n{'='*60}")
            output_lines.append("ALERTS")
            output_lines.append("=" * 60)
            
            for alert in sorted(filtered_alerts, key=lambda a: priority_order(a.priority.value)):
                output_lines.append("")
                output_lines.append(format_alert_summary(alert))
        
        if args.verbose and not args.quiet:
            output_lines.append(f"\n{'='*60}")
            output_lines.append("DETAILED STATISTICS")
            output_lines.append("=" * 60)
            output_lines.append(f"\nRisk Distribution:")
            for level, count in stats.risk_distribution.items():
                output_lines.append(f"  {level}: {count}")
            output_lines.append(f"\nClassifications:")
            for cls, count in sorted(stats.classification_distribution.items(), key=lambda x: -x[1]):
                output_lines.append(f"  {cls}: {count}")
    
    # Output
    output_text = "\n".join(output_lines)
    
    if args.output_file:
        with open(args.output_file, "w") as f:
            f.write(output_text)
        if not args.quiet:
            print(f"\nOutput written to: {args.output_file}")
    else:
        print(output_text)
    
    # Return code based on alert severity
    if any(a.priority.value == "P0-Critical" for a in filtered_alerts):
        return 2  # Critical alerts
    elif any(a.priority.value == "P1-High" for a in filtered_alerts):
        return 1  # High alerts
    return 0


def cmd_feedback(args) -> int:
    """Run feedback command."""
    store = FeedbackStore()
    store.initialize()
    
    try:
        if args.feedback_command == "add":
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
            
        elif args.feedback_command == "stats":
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
        else:
            print("Use 'add' or 'stats' subcommand")
            return 1
    finally:
        store.close()


def cmd_status(args) -> int:
    """Run status command."""
    models_dir = Path(args.models_dir)
    
    print("SOC Copilot Status")
    print("=" * 40)
    print(f"\nModels Directory: {models_dir}")
    
    if not models_dir.exists():
        print("  Status: NOT FOUND")
        return 1
    
    # Check for model files
    if_model = models_dir / "isolation_forest_v1.joblib"
    rf_model = models_dir / "random_forest_v1.joblib"
    feature_order = models_dir / "feature_order.json"
    label_map = models_dir / "label_map.json"
    
    print(f"\nModel Files:")
    print(f"  Isolation Forest: {'✓' if if_model.exists() else '✗'}")
    print(f"  Random Forest: {'✓' if rf_model.exists() else '✗'}")
    print(f"  Feature Order: {'✓' if feature_order.exists() else '✗'}")
    print(f"  Label Map: {'✓' if label_map.exists() else '✗'}")
    
    if feature_order.exists():
        import json
        with open(feature_order) as f:
            data = json.load(f)
        print(f"\nFeature Count: {data.get('feature_count', 'unknown')}")
    
    if label_map.exists():
        with open(label_map) as f:
            data = json.load(f)
        print(f"Classes: {', '.join(data.get('classes', []))}")
    
    # Try to load pipeline
    try:
        copilot = create_soc_copilot(str(models_dir))
        print(f"\nPipeline: ✓ Ready")
    except Exception as e:
        print(f"\nPipeline: ✗ Error - {e}")
        return 1
    
    return 0


def main() -> int:
    """Main entry point."""
    parser = setup_parser()
    args = parser.parse_args()
    
    if args.command is None:
        parser.print_help()
        return 0
    
    if args.command == "analyze":
        return cmd_analyze(args)
    elif args.command == "status":
        return cmd_status(args)
    elif args.command == "feedback":
        return cmd_feedback(args)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
