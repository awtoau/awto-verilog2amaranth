# Amber as a Converter Test Case

Amber is a good system-level benchmark for Verilog-to-Amaranth conversion because it combines realistic CPU datapath logic with bus/peripheral integration.

## Why Amber

- Open-source RTL with enough complexity to expose semantic conversion gaps.
- Mix of combinational and sequential logic in one codebase.
- Practical observable behavior via UART runtime output.

## Staged Test Plan

1. Subset Stage (sanity)
- Convert simple Amber leaf modules that are mostly `assign` and basic expressions.
- Expect near-zero semantic gaps.

2. Core Stage (semantic pressure)
- Convert representative Amber23 core modules with `always`, `case`, and state logic.
- Expect non-zero gaps and use gap logs to drive feature work.

3. System Stage (behavioral proof)
- Use Amber UART test path as end-to-end check.
- Pass criteria: generated Amaranth model reproduces expected UART text and completion condition.

## Success Metrics

- Parse coverage: percentage of selected modules converted without hard failure.
- Gap density: gap records per converted module.
- Behavioral equivalence: selected tests match original RTL outcomes.
- Reproducibility: same converter revision yields same status and gap outputs.

## Minimal Amber Profile for Early CI

- Start with Amber23-focused modules that already run in open simulators.
- Keep unsupported constructs explicit in `.gaps.jsonl`.
- Treat every new unsupported construct as either:
  - a converter feature ticket, or
  - a documented non-goal for the current release.
