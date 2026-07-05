import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from .converter import convert_verilog_to_amaranth


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="awto-verilog2amaranth converter")
    parser.add_argument("--verilog-in", required=True, help="Input Verilog file")
    parser.add_argument("--out-dir", required=True, help="Output directory")
    parser.add_argument(
        "--normalize",
        action="store_true",
        help="Run iverilog preprocessor and convert normalized output when available",
    )
    parser.add_argument(
        "--lint",
        action="store_true",
        help="Run best-effort lint checks with available tools (iverilog/verilator)",
    )
    parser.add_argument(
        "--strict-lint",
        action="store_true",
        help="Fail conversion if lint stage reports errors",
    )
    return parser.parse_args()


def _run_command(command: list[str]) -> dict:
    result = subprocess.run(command, text=True, capture_output=True)
    return {
        "command": command,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def _tool_exists(name: str) -> bool:
    return subprocess.run(["sh", "-c", f"command -v {name}"], capture_output=True).returncode == 0


def _normalize(verilog_in: Path, out_dir: Path) -> dict:
    normalized = out_dir / f"{verilog_in.stem}.normalized.v"
    stage = {
        "stage": "normalize",
        "tool": "iverilog",
        "status": "skipped",
        "normalized_file": str(normalized),
    }
    if not _tool_exists("iverilog"):
        stage["reason"] = "iverilog not found"
        return stage

    run = _run_command(["iverilog", "-E", "-o", str(normalized), str(verilog_in)])
    stage["command"] = run["command"]
    stage["returncode"] = run["returncode"]
    stage["stderr"] = run["stderr"]
    if run["returncode"] == 0 and normalized.exists() and normalized.stat().st_size > 0:
        stage["status"] = "ok"
    else:
        stage["status"] = "failed"
    return stage


def _lint(verilog_in: Path, out_dir: Path) -> list[dict]:
    stages: list[dict] = []

    lint_out = out_dir / f"{verilog_in.stem}.iverilog-lint.log"
    if _tool_exists("iverilog"):
        run = _run_command(["iverilog", "-g2005", "-t", "null", str(verilog_in)])
        lint_out.write_text(run["stdout"] + run["stderr"], encoding="utf-8")
        stages.append(
            {
                "stage": "lint",
                "tool": "iverilog",
                "status": "ok" if run["returncode"] == 0 else "failed",
                "command": run["command"],
                "returncode": run["returncode"],
                "log_file": str(lint_out),
            }
        )
    else:
        stages.append(
            {
                "stage": "lint",
                "tool": "iverilog",
                "status": "skipped",
                "reason": "iverilog not found",
            }
        )

    verilator_out = out_dir / f"{verilog_in.stem}.verilator-lint.log"
    if _tool_exists("verilator"):
        run = _run_command(["verilator", "--lint-only", str(verilog_in)])
        verilator_out.write_text(run["stdout"] + run["stderr"], encoding="utf-8")
        stages.append(
            {
                "stage": "lint",
                "tool": "verilator",
                "status": "ok" if run["returncode"] == 0 else "failed",
                "command": run["command"],
                "returncode": run["returncode"],
                "log_file": str(verilator_out),
            }
        )
    else:
        stages.append(
            {
                "stage": "lint",
                "tool": "verilator",
                "status": "skipped",
                "reason": "verilator not found",
            }
        )

    yosys_out = out_dir / f"{verilog_in.stem}.yosys-check.log"
    if _tool_exists("yosys"):
        run = _run_command(
            [
                "yosys",
                "-q",
                "-p",
                f"read_verilog {verilog_in}; hierarchy -check -auto-top; proc; check",
            ]
        )
        yosys_out.write_text(run["stdout"] + run["stderr"], encoding="utf-8")
        stages.append(
            {
                "stage": "lint",
                "tool": "yosys",
                "status": "ok" if run["returncode"] == 0 else "failed",
                "command": run["command"],
                "returncode": run["returncode"],
                "log_file": str(yosys_out),
            }
        )
    else:
        stages.append(
            {
                "stage": "lint",
                "tool": "yosys",
                "status": "skipped",
                "reason": "yosys not found",
            }
        )

    return stages


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    verilog_in = Path(args.verilog_in)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    stages: list[dict] = []
    source_for_convert = verilog_in

    if args.normalize:
        norm = _normalize(verilog_in, out_dir)
        stages.append(norm)
        if norm["status"] == "ok":
            source_for_convert = Path(norm["normalized_file"])

    if args.lint:
        lint_stages = _lint(source_for_convert, out_dir)
        stages.extend(lint_stages)
        if args.strict_lint and any(s.get("status") == "failed" for s in lint_stages):
            status = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "converted": False,
                "module": verilog_in.stem,
                "source": str(verilog_in),
                "source_for_convert": str(source_for_convert),
                "reason": "strict lint enabled and lint failed",
                "pipeline": stages,
            }
            _write_json(out_dir / f"{verilog_in.stem}.status.json", status)
            print(json.dumps(status, indent=2))
            raise SystemExit(2)

    try:
        conv = convert_verilog_to_amaranth(source_for_convert, out_dir)
        status = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "converted": True,
            "source": str(verilog_in),
            "source_for_convert": str(source_for_convert),
            "pipeline": stages,
        }
        status.update(conv)
        status["source_original"] = str(verilog_in)
        status["source_for_convert"] = str(source_for_convert)
    except Exception as exc:
        gaps_path = out_dir / f"{verilog_in.stem}.gaps.jsonl"
        gap_record = {
            "severity": "high",
            "kind": "conversion-error",
            "reason": str(exc),
            "source_file": str(source_for_convert),
        }
        gaps_path.write_text(json.dumps(gap_record, sort_keys=True) + "\n", encoding="utf-8")
        status = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "converted": False,
            "module": verilog_in.stem,
            "source": str(verilog_in),
            "source_for_convert": str(source_for_convert),
            "gaps": 1,
            "gaps_file": str(gaps_path),
            "reason": str(exc),
            "pipeline": stages,
        }

    _write_json(out_dir / f"{verilog_in.stem}.status.json", status)
    print(json.dumps(status, indent=2))


if __name__ == "__main__":
    main()
