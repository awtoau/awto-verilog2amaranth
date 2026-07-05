#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_log(log_path: Path, line: str) -> None:
    with log_path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def run_file(repo_root: Path, verilog_file: Path, amber_root: Path, out_root: Path, log_path: Path) -> dict:
    rel = verilog_file.relative_to(amber_root)
    out_dir = out_root / rel.parent / rel.stem
    out_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        "-m",
        "awto_verilog2amaranth.cli",
        "--verilog-in",
        str(verilog_file),
        "--out-dir",
        str(out_dir),
        "--normalize",
        "--lint",
    ]

    write_log(log_path, f"[{iso_now()}] START {rel}")
    proc = subprocess.run(
        cmd,
        cwd=repo_root,
        env={**dict(os.environ), "PYTHONPATH": "src"},
        capture_output=True,
        text=True,
    )

    status_file = out_dir / f"{rel.stem}.status.json"
    status = {
        "file": str(rel),
        "returncode": proc.returncode,
        "status_file": str(status_file),
        "converted": False,
        "gaps": None,
        "python_compile_ok": False,
        "python_compile_error": "",
    }

    if proc.stdout.strip():
        write_log(log_path, proc.stdout.strip())
    if proc.stderr.strip():
        write_log(log_path, proc.stderr.strip())

    if status_file.exists():
        try:
            data = json.loads(status_file.read_text(encoding="utf-8"))
            status["converted"] = bool(data.get("converted", False))
            status["gaps"] = data.get("gaps")
            py_out = data.get("output")
            if py_out:
                py_path = Path(py_out)
                if not py_path.is_absolute():
                    py_path = repo_root / py_path
                if py_path.exists():
                    cproc = subprocess.run(
                        [sys.executable, "-m", "py_compile", str(py_path)],
                        capture_output=True,
                        text=True,
                    )
                    status["python_compile_ok"] = cproc.returncode == 0
                    if cproc.returncode != 0:
                        status["python_compile_error"] = cproc.stderr.strip()
        except Exception as exc:  # noqa: BLE001
            status["python_compile_error"] = f"status parse error: {exc}"

    write_log(
        log_path,
        f"[{iso_now()}] END {rel} rc={status['returncode']} converted={status['converted']} gaps={status['gaps']} py_ok={status['python_compile_ok']}",
    )
    return status


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    amber_root = Path("/mnt/2tb/git_mirror/freecores/amber")
    source_glob = "hw/**/*.v"

    out_root = repo_root / "tmp" / "amber-batch"
    out_root.mkdir(parents=True, exist_ok=True)

    log_path = repo_root / "tmp" / "amber_batch_convert.log"
    log_path.write_text("", encoding="utf-8")

    write_log(log_path, f"[{iso_now()}] amber batch conversion start")
    write_log(log_path, f"amber_root={amber_root}")
    write_log(log_path, f"source_glob={source_glob}")

    verilog_files = sorted(amber_root.glob(source_glob))
    results: list[dict] = []

    for vf in verilog_files:
        if vf.is_file():
            results.append(run_file(repo_root, vf, amber_root, out_root, log_path))

    converted_ok = sum(1 for r in results if r.get("converted"))
    converted_fail = len(results) - converted_ok
    py_ok = sum(1 for r in results if r.get("python_compile_ok"))
    py_fail = len(results) - py_ok
    total_gaps = sum(int(r.get("gaps") or 0) for r in results)
    files_with_gaps = sum(1 for r in results if (r.get("gaps") or 0) > 0)

    summary = {
        "timestamp": iso_now(),
        "amber_root": str(amber_root),
        "source_glob": source_glob,
        "total_files": len(results),
        "converted_ok": converted_ok,
        "converted_fail": converted_fail,
        "python_compile_ok": py_ok,
        "python_compile_fail": py_fail,
        "total_gaps": total_gaps,
        "files_with_gaps": files_with_gaps,
        "log_file": str(log_path),
        "results_file": str(out_root / "results.json"),
    }

    (out_root / "results.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    (out_root / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    write_log(log_path, f"[{iso_now()}] summary={json.dumps(summary, sort_keys=True)}")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
