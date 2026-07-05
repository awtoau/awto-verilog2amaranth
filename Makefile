PYTHON ?= python3

.PHONY: build smoke pipeline amber-batch amber-gap-report clean

build:
	$(PYTHON) -m pip wheel . -w dist

smoke:
	mkdir -p tmp
	printf 'module smoke(input [7:0] a, input [7:0] b, output [7:0] y);\nassign y = a ^ b;\nendmodule\n' > tmp/smoke.v
	PYTHONPATH=src $(PYTHON) -m awto_verilog2amaranth.cli --verilog-in tmp/smoke.v --out-dir tmp/smoke-out

pipeline:
	mkdir -p tmp
	printf 'module smoke(input [7:0] a, input [7:0] b, output [7:0] y);\nassign y = a ^ b;\nendmodule\n' > tmp/smoke.v
	PYTHONPATH=src $(PYTHON) -m awto_verilog2amaranth.cli --verilog-in tmp/smoke.v --out-dir tmp/pipeline-out --normalize --lint

amber-batch:
	$(PYTHON) scripts/amber_batch_convert.py

amber-gap-report:
	$(PYTHON) scripts/amber_gap_report.py --batch-root tmp/amber-batch

clean:
	rm -rf dist tmp/smoke.v tmp/smoke-out tmp/pipeline-out