#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize conversion gaps from Amber batch outputs")
    parser.add_argument(
        "--batch-root",
        default="tmp/amber-batch",
        help="Batch output root containing results.json",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=20,
        help="Top N entries for summary sections",
    )
    args = parser.parse_args()

    batch_root = Path(args.batch_root)
    results_path = batch_root / "results.json"
    if not results_path.exists():
        raise SystemExit(f"results file not found: {results_path}")

    results = json.loads(results_path.read_text(encoding="utf-8"))

    kind_counter: Counter[str] = Counter()
    reason_counter: Counter[str] = Counter()
    file_gap_count: Counter[str] = Counter()
    per_file_kinds: dict[str, Counter[str]] = defaultdict(Counter)

    for row in results:
        status_file = Path(row["status_file"])
        if not status_file.exists():
            continue
        status = json.loads(status_file.read_text(encoding="utf-8"))
        gaps_file = status.get("gaps_file")
        if not gaps_file:
            continue
        gf = Path(gaps_file)
        if not gf.exists():
            continue

        lines = [ln for ln in gf.read_text(encoding="utf-8").splitlines() if ln.strip()]
        for ln in lines:
            gap = json.loads(ln)
            kind = gap.get("kind", "unknown")
            reason = gap.get("reason", "")
            kind_counter[kind] += 1
            reason_counter[reason] += 1
            file_gap_count[row["file"]] += 1
            per_file_kinds[row["file"]][kind] += 1

    summary = {
        "total_files": len(results),
        "files_with_gaps": sum(1 for _, c in file_gap_count.items() if c > 0),
        "total_gap_records": sum(kind_counter.values()),
        "top_gap_kinds": kind_counter.most_common(args.top),
        "top_gap_reasons": reason_counter.most_common(args.top),
        "top_files_by_gap_count": file_gap_count.most_common(args.top),
    }

    out_json = batch_root / "gap-summary.json"
    out_md = batch_root / "gap-summary.md"

    out_json.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    lines: list[str] = []
    lines.append("# Amber Gap Summary")
    lines.append("")
    lines.append(f"- total_files: {summary['total_files']}")
    lines.append(f"- files_with_gaps: {summary['files_with_gaps']}")
    lines.append(f"- total_gap_records: {summary['total_gap_records']}")
    lines.append("")

    lines.append("## Top Gap Kinds")
    lines.append("")
    for kind, count in summary["top_gap_kinds"]:
        lines.append(f"- {kind}: {count}")
    lines.append("")

    lines.append("## Top Files By Gap Count")
    lines.append("")
    for file_name, count in summary["top_files_by_gap_count"]:
        kinds = ", ".join(f"{k}:{v}" for k, v in per_file_kinds[file_name].most_common(3))
        lines.append(f"- {file_name}: {count} ({kinds})")
    lines.append("")

    lines.append("## Top Gap Reasons")
    lines.append("")
    for reason, count in summary["top_gap_reasons"]:
        lines.append(f"- {count}x {reason}")

    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps({"gap_summary_json": str(out_json), "gap_summary_md": str(out_md)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
