# awto-verilog2amaranth

Standalone Verilog-to-Amaranth conversion package.

Current scope:
- Subset converter for ANSI-style module ports and continuous assign statements.
- Explicit gap logging for unsupported semantic constructs.

## Dependencies

Required:
- Python 3.10+
- pip

Optional but recommended tools for pipeline mode:
- iverilog (normalization and lint)
- verilator (lint)
- yosys (structural check in lint pipeline, and future semantic pipeline stages)

## Fedora Setup

Install system dependencies on Fedora:

```bash
sudo dnf install -y python3 python3-pip make iverilog verilator yosys
```

## Usage

```bash
python3 -m awto_verilog2amaranth.cli \
  --verilog-in path/to/module.v \
  --out-dir ./out
```

Pipeline mode (normalize then lint, still report gaps if conversion fails):

```bash
python3 -m awto_verilog2amaranth.cli \
  --verilog-in path/to/module.v \
  --out-dir ./out \
  --normalize \
  --lint
```

Strict mode (fail fast on lint errors):

```bash
python3 -m awto_verilog2amaranth.cli \
  --verilog-in path/to/module.v \
  --out-dir ./out \
  --normalize \
  --lint \
  --strict-lint
```

Outputs:
- `<module>.py` generated Amaranth module
- `<module>.gaps.jsonl` semantic/construct gaps
- `<module>.status.json` conversion summary
- `<module>.normalized.v` preprocessed source when `--normalize` is used
- `<module>.iverilog-lint.log` and `<module>.verilator-lint.log` when `--lint` is used
- `<module>.yosys-check.log` when `--lint` is used and yosys is installed

## Build

```bash
make build
```

## Smoke Test

```bash
make smoke
```

## Pipeline Test

```bash
make pipeline
```

## Full Amber Batch

Run conversion across all Verilog files under `freecores/amber/hw`:

```bash
make amber-batch
```

Run against the module-only profile generated in `awtoau/amber`:

```bash
python3 scripts/amber_batch_convert.py \
  --amber-root /mnt/2tb/git/awtoaa/amber \
  --filelist /mnt/2tb/git/awtoaa/amber/tools/conversion/module_filelist.txt
```

Run against the core-focused profile (ETHMAC excluded):

```bash
python3 scripts/amber_batch_convert.py \
  --amber-root /mnt/2tb/git/awtoaa/amber \
  --filelist /mnt/2tb/git/awtoaa/amber/tools/conversion/module_filelist_core.txt
```

Batch artifacts:
- `tmp/amber_batch_convert.log`
- `tmp/amber-batch/summary.json`
- `tmp/amber-batch/results.json`

Generate semantic gap analytics from batch outputs:

```bash
make amber-gap-report
```

Gap report artifacts:
- `tmp/amber-batch/gap-summary.json`
- `tmp/amber-batch/gap-summary.md`

## Test Cases

- Amber benchmark profile: `docs/amber-test-case.md`
