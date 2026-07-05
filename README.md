# awto-verilog2amaranth

Standalone Verilog-to-Amaranth conversion package.

Current scope:
- Subset converter for ANSI-style module ports and continuous assign statements.
- Explicit gap logging for unsupported semantic constructs.

## Usage

```bash
python3 -m awto_verilog2amaranth.cli \
  --verilog-in path/to/module.v \
  --out-dir ./out
```

Outputs:
- `<module>.py` generated Amaranth module
- `<module>.gaps.jsonl` semantic/construct gaps
- `<module>.status.json` conversion summary

## Intent

This package is intended to live in its own repository (`awto-verilog2amaranth`) and be consumed by tools such as `renode2rtl` as a dependency.
