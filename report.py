"""Render findings to console and a timestamped markdown report file."""
from datetime import datetime
from pathlib import Path

from checks import Finding

import sys
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

SEVERITY_ORDER = {"critical": 0, "warn": 1, "info": 2}
SEVERITY_ICON = {"critical": "[CRIT]", "warn": "[WARN]", "info": "[info]"}


def _sorted(findings: list[Finding]) -> list[Finding]:
    return sorted(findings, key=lambda f: (SEVERITY_ORDER[f.severity], f.category, f.ref))


def print_console(findings: list[Finding], memory_root: Path, score: float | None = None) -> None:
    print(f"\nMemory audit — {memory_root}")
    print(f"{len(findings)} findings\n")
    if not findings:
        print("No issues found.")
    else:
        for f in _sorted(findings):
            print(f"{SEVERITY_ICON[f.severity]:8} {f.category:20} {f.ref:35} {f.message}")

        counts = {}
        for f in findings:
            counts[f.severity] = counts.get(f.severity, 0) + 1
        print("\nSummary:", ", ".join(f"{k}={v}" for k, v in sorted(counts.items(), key=lambda kv: SEVERITY_ORDER[kv[0]])))

    if score is not None:
        print(f"\nSpec conformance score: {score:.1f}/100")


def write_markdown_report(findings: list[Finding], memory_root: Path, report_dir: Path,
                           keep_last_n: int, score: float | None = None,
                           report_name_prefix: str = "audit") -> Path:
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    report_path = report_dir / f"{report_name_prefix}_{timestamp}.md"

    lines = [
        f"# Memory Audit Report — {timestamp}",
        "",
        f"**Memory root:** `{memory_root}`",
        f"**Total findings:** {len(findings)}",
    ]
    if score is not None:
        lines.append(f"**Spec conformance score:** {score:.1f}/100")
    lines.append("")

    by_category: dict[str, list[Finding]] = {}
    for f in _sorted(findings):
        by_category.setdefault(f.category, []).append(f)

    if not findings:
        lines.append("No issues found.")
    else:
        for category, items in by_category.items():
            lines.append(f"## {category} ({len(items)})")
            lines.append("")
            for f in items:
                lines.append(f"- **{f.severity.upper()}** `{f.ref}` — {f.message}")
            lines.append("")

    report_path.write_text("\n".join(lines), encoding="utf-8")

    _prune_old_reports(report_dir, keep_last_n, report_name_prefix)
    return report_path


def _prune_old_reports(report_dir: Path, keep_last_n: int, report_name_prefix: str) -> None:
    reports = sorted(report_dir.glob(f"{report_name_prefix}_*.md"), key=lambda p: p.name)
    excess = len(reports) - keep_last_n
    for old in reports[:max(excess, 0)]:
        old.unlink()
