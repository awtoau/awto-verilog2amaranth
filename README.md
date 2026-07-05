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
- yosys (future semantic pipeline stages)

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

## Intent

This package is intended to live in its own repository (`awto-verilog2amaranth`) and be consumed by tools such as `renode2rtl` as a dependency.

## Test Cases

- Amber benchmark profile: `docs/amber-test-case.md`
