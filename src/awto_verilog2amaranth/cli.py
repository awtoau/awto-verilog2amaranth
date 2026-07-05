import argparse
import json
from pathlib import Path

from .converter import convert_verilog_to_amaranth


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="awto-verilog2amaranth converter")
    parser.add_argument("--verilog-in", required=True, help="Input Verilog file")
    parser.add_argument("--out-dir", required=True, help="Output directory")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    status = convert_verilog_to_amaranth(Path(args.verilog_in), Path(args.out_dir))
    print(json.dumps(status, indent=2))


if __name__ == "__main__":
    main()
