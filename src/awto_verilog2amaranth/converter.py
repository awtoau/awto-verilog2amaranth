from __future__ import annotations

import json
import keyword
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Port:
    direction: str
    name: str
    width: int


@dataclass
class Assign:
    lhs: str
    rhs: str


@dataclass
class Net:
    name: str
    width: int


@dataclass
class AlwaysAssign:
    lhs: str
    rhs: str
    domain: str


def _strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    text = re.sub(r"//.*", "", text)
    return text


def _width_from_range(rng: str | None) -> int:
    if not rng:
        return 1
    m = re.match(r"\[(\d+)\s*:\s*(\d+)\]", rng)
    if not m:
        return 1
    msb = int(m.group(1))
    lsb = int(m.group(2))
    return abs(msb - lsb) + 1


def _parse_ports(port_blob: str) -> list[Port]:
    ports: list[Port] = []
    parts = [p.strip() for p in port_blob.replace("\n", " ").split(",") if p.strip()]
    for part in parts:
        m = re.match(
            r"^(input|output|inout)\s+(?:wire\s+|reg\s+)?(\[[^\]]+\])?\s*([A-Za-z_][A-Za-z0-9_]*)$",
            part,
        )
        if not m:
            continue
        ports.append(
            Port(
                direction=m.group(1),
                name=m.group(3),
                width=_width_from_range(m.group(2)),
            )
        )
    return ports


def _parse_assigns(body: str) -> list[Assign]:
    assigns: list[Assign] = []
    for m in re.finditer(r"assign\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?);", body, flags=re.DOTALL):
        lhs = m.group(1).strip()
        rhs = " ".join(m.group(2).split())
        assigns.append(Assign(lhs=lhs, rhs=rhs))
    return assigns


def _parse_internal_nets(body: str) -> list[Net]:
    nets: dict[str, int] = {}
    for m in re.finditer(r"\b(?:wire|reg)\b\s+(?:signed\s+)?(\[[^\]]+\])?\s*([^;]+);", body):
        width = _width_from_range(m.group(1))
        items = [p.strip() for p in m.group(2).split(",") if p.strip()]
        for item in items:
            name = item.split("=", 1)[0].strip()
            if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", name):
                nets[name] = max(width, nets.get(name, 1))
    return [Net(name=n, width=w) for n, w in sorted(nets.items())]


def _parse_trivial_always_assigns(body: str) -> list[AlwaysAssign]:
    assigns: list[AlwaysAssign] = []
    patt = re.compile(
        r"always\s*@\s*\((.*?)\)\s*([A-Za-z_][A-Za-z0-9_]*\s*(?:<=|=)\s*.*?;)",
        flags=re.DOTALL,
    )

    for m in patt.finditer(body):
        sens = (m.group(1) or "").strip()
        stmt = " ".join((m.group(2) or "").split())
        am = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*(?:<=|=)\s*(.*);$", stmt)
        if not am:
            continue

        lhs = am.group(1)
        rhs = am.group(2).strip()
        if not rhs:
            continue

        domain = "sync" if re.search(r"\b(posedge|negedge)\b", sens) else "comb"
        assigns.append(AlwaysAssign(lhs=lhs, rhs=rhs, domain=domain))

    return assigns


def _emit_gap(gaps: list[dict], kind: str, detail: str, source_file: Path) -> None:
    gaps.append(
        {
            "severity": "medium",
            "kind": kind,
            "reason": detail,
            "source_file": str(source_file),
        }
    )


def _py_ident(name: str) -> str:
    return f"{name}_" if keyword.iskeyword(name) else name


def _convert_literal(tok: str, gaps: list[dict], source_file: Path) -> str:
    m = re.match(r"^(\d+)'([bdhBDH])\s*([0-9a-fA-F_xXzZ]+)$", tok)
    if not m:
        return tok
    base = m.group(2).lower()
    raw = m.group(3).replace("_", "")
    if "x" in raw.lower() or "z" in raw.lower():
        _emit_gap(gaps, "unsupported-literal", f"x/z literal not supported: {tok}", source_file)
        return "0"
    try:
        if base == "b":
            return str(int(raw, 2))
        if base == "h":
            return str(int(raw, 16))
        return str(int(raw, 10))
    except ValueError:
        _emit_gap(gaps, "unsupported-literal", f"literal parse failed: {tok}", source_file)
        return "0"


def _convert_unsized_literal(base: str, raw: str, gaps: list[dict], source_file: Path) -> str:
    clean = raw.replace("_", "")
    if "x" in clean.lower() or "z" in clean.lower():
        _emit_gap(gaps, "unsupported-literal", f"x/z literal not supported: '{base}{raw}", source_file)
        return "0"
    try:
        b = base.lower()
        if b == "b":
            return str(int(clean, 2))
        if b == "h":
            return str(int(clean, 16))
        return str(int(clean, 10))
    except ValueError:
        _emit_gap(gaps, "unsupported-literal", f"literal parse failed: '{base}{raw}", source_file)
        return "0"


def _split_top_level(text: str, sep: str) -> list[str]:
    parts: list[str] = []
    start = 0
    paren = 0
    brace = 0
    bracket = 0
    for i, ch in enumerate(text):
        if ch == "(":
            paren += 1
        elif ch == ")":
            paren = max(paren - 1, 0)
        elif ch == "{":
            brace += 1
        elif ch == "}":
            brace = max(brace - 1, 0)
        elif ch == "[":
            bracket += 1
        elif ch == "]":
            bracket = max(bracket - 1, 0)
        elif ch == sep and paren == 0 and brace == 0 and bracket == 0:
            parts.append(text[start:i])
            start = i + 1
    parts.append(text[start:])
    return [p.strip() for p in parts if p.strip()]


def _is_wrapped(expr: str, open_ch: str, close_ch: str) -> bool:
    if len(expr) < 2 or expr[0] != open_ch or expr[-1] != close_ch:
        return False
    depth = 0
    for i, ch in enumerate(expr):
        if ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0 and i != len(expr) - 1:
                return False
    return depth == 0


def _strip_outer_parens(expr: str) -> str:
    out = expr.strip()
    while _is_wrapped(out, "(", ")"):
        out = out[1:-1].strip()
    return out


def _find_top_level_ternary(expr: str) -> tuple[int, int] | None:
    paren = 0
    brace = 0
    bracket = 0
    ternary_depth = 0
    q_idx = -1
    for i, ch in enumerate(expr):
        if ch == "(":
            paren += 1
        elif ch == ")":
            paren = max(paren - 1, 0)
        elif ch == "{":
            brace += 1
        elif ch == "}":
            brace = max(brace - 1, 0)
        elif ch == "[":
            bracket += 1
        elif ch == "]":
            bracket = max(bracket - 1, 0)
        elif paren == 0 and brace == 0 and bracket == 0:
            if ch == "?":
                if ternary_depth == 0:
                    q_idx = i
                ternary_depth += 1
            elif ch == ":" and ternary_depth > 0:
                ternary_depth -= 1
                if ternary_depth == 0 and q_idx >= 0:
                    return (q_idx, i)
    return None


def _rewrite_parenthesized_ternary(expr: str, signal_map: dict[str, str], gaps: list[dict], source_file: Path) -> str:
    changed = True
    out = expr
    while changed:
        changed = False
        stack: list[int] = []
        for i, ch in enumerate(out):
            if ch == "(":
                stack.append(i)
            elif ch == ")" and stack:
                s = stack.pop()
                inner = out[s + 1 : i]
                tern = _find_top_level_ternary(inner)
                if tern is None:
                    continue
                q_idx, c_idx = tern
                cond = _convert_expr(inner[:q_idx], signal_map, gaps, source_file)
                on_true = _convert_expr(inner[q_idx + 1 : c_idx], signal_map, gaps, source_file)
                on_false = _convert_expr(inner[c_idx + 1 :], signal_map, gaps, source_file)
                repl = f"Mux({cond}, {on_true}, {on_false})"
                out = out[:s] + repl + out[i + 1 :]
                changed = True
                break
    return out


def _convert_concat(expr: str, signal_map: dict[str, str], gaps: list[dict], source_file: Path) -> str | None:
    candidate = _strip_outer_parens(expr)
    if not _is_wrapped(candidate, "{", "}"):
        return None

    inner = candidate[1:-1].strip()
    if not inner:
        return "0"

    parts = _split_top_level(inner, ",")
    values: list[str] = []
    for part in parts:
        m = re.match(r"^(\d+)\s*\{(.*)\}$", part)
        if m and _is_wrapped("{" + m.group(2).strip() + "}", "{", "}"):
            count = int(m.group(1))
            rep_expr = m.group(2).strip()
            rep_val = _convert_expr(rep_expr, signal_map, gaps, source_file)
            values.extend([rep_val] * count)
        else:
            m_rep = re.match(r"^(.*?)\{(.*)\}$", part)
            if m_rep and m_rep.group(1).strip():
                _emit_gap(gaps, "unsupported-expression", f"non-constant replication unsupported: {part}", source_file)
                values.append("0")
            else:
                values.append(_convert_expr(part, signal_map, gaps, source_file))

    if not values:
        return "0"
    return f"Cat({', '.join(reversed(values))})"


def _find_matching_brace(text: str, start: int) -> int:
    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
    return -1


def _replace_concat_segments(expr: str, signal_map: dict[str, str], gaps: list[dict], source_file: Path) -> tuple[str, dict[str, str]]:
    out: list[str] = []
    replacements: dict[str, str] = {}
    i = 0
    while i < len(expr):
        ch = expr[i]
        if ch != "{":
            out.append(ch)
            i += 1
            continue

        end = _find_matching_brace(expr, i)
        if end < 0:
            _emit_gap(gaps, "unsupported-expression", f"unbalanced braces: {expr}", source_file)
            return ("0", {})

        segment = expr[i : end + 1]
        converted = _convert_concat(segment, signal_map, gaps, source_file)
        if converted is None:
            _emit_gap(gaps, "unsupported-expression", f"concatenation unsupported: {segment}", source_file)
            converted = "0"

        key = f"__CAT{len(replacements)}__"
        replacements[key] = converted
        out.append(key)
        i = end + 1

    return ("".join(out), replacements)


def _convert_expr(expr: str, signal_map: dict[str, str], gaps: list[dict], source_file: Path) -> str:
    expr = _strip_outer_parens(expr)
    expr = re.sub(r"(\d+)'([bdhBDH])\s+([0-9a-fA-F_xXzZ]+)", r"\1'\2\3", expr)
    if "`" in expr:
        _emit_gap(gaps, "unsupported-expression", f"macro token unsupported: {expr}", source_file)
        expr = re.sub(r"`[A-Za-z_][A-Za-z0-9_]*", "0", expr)
    expr = re.sub(
        r"'([bdhBDH])\s*([0-9a-fA-F_xXzZ]+)",
        lambda m: _convert_unsized_literal(m.group(1), m.group(2), gaps, source_file),
        expr,
    )

    ternary = _find_top_level_ternary(expr)
    if ternary is not None:
        q_idx, c_idx = ternary
        cond = _convert_expr(expr[:q_idx], signal_map, gaps, source_file)
        on_true = _convert_expr(expr[q_idx + 1 : c_idx], signal_map, gaps, source_file)
        on_false = _convert_expr(expr[c_idx + 1 :], signal_map, gaps, source_file)
        return f"Mux({cond}, {on_true}, {on_false})"

    expr = _rewrite_parenthesized_ternary(expr, signal_map, gaps, source_file)

    concat = _convert_concat(expr, signal_map, gaps, source_file)
    if concat is not None:
        return concat

    working, placeholders = _replace_concat_segments(expr, signal_map, gaps, source_file)
    if working == "0" and not placeholders:
        return "0"

    if "?" in working and ":" in working:
        _emit_gap(gaps, "unsupported-expression", f"nested ternary unsupported: {expr}", source_file)
        return "0"

    working = working.replace("&&", " & ").replace("||", " | ")
    working = re.sub(r"!(?!=)", "~", working)
    working = re.sub(
        r"\d+'[bdhBDH][0-9a-fA-F_xXzZ]+",
        lambda m: _convert_literal(m.group(0), gaps, source_file),
        working,
    )

    known_keywords = {"Cat", "Mux", "Const", "self"}

    def _replace_name(m: re.Match) -> str:
        name = m.group(1)
        suffix = m.group(2) or ""
        if name.startswith("__CAT"):
            return name
        if name in known_keywords:
            return name + suffix
        if name in signal_map:
            return f"self.{signal_map[name]}{suffix}"
        return name + suffix

    working = re.sub(r"\b([A-Za-z_][A-Za-z0-9_]*)\b(\[[^\]]+\])?", _replace_name, working)

    # Map unary reduction operators used in Verilog (e.g. |x, &x, ^x)
    # to Amaranth helpers for common signal operands.
    value_pat = r"(?:self\.)?[A-Za-z_][A-Za-z0-9_]*(?:\[[^\]]+\])?"

    def _rewrite_reduction(op: str, method: str, text: str) -> str:
        pat = re.compile(rf"(^|[(,:=+\-*/%<>!&|~]\s*)\{op}\s*({value_pat})")
        return pat.sub(lambda m: f"{m.group(1)}({m.group(2)}).{method}()", text)

    working = _rewrite_reduction("|", "any", working)
    working = _rewrite_reduction("&", "all", working)
    working = _rewrite_reduction("^", "xor", working)

    for key, value in placeholders.items():
        working = working.replace(key, value)

    return " ".join(working.split()) if working.strip() else "0"


def convert_verilog_to_amaranth(verilog_path: Path, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    gaps: list[dict] = []

    raw = verilog_path.read_text(encoding="utf-8")
    text = _strip_comments(raw)

    m = re.search(
        r"module\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?:#\s*\(.*?\)\s*)?\((.*?)\)\s*;(.*)endmodule",
        text,
        flags=re.DOTALL,
    )
    if not m:
        raise ValueError(f"Could not parse module in {verilog_path}")

    module_name = m.group(1)
    port_blob = m.group(2)
    body = m.group(3)

    ports = _parse_ports(port_blob)
    internal_nets = _parse_internal_nets(body)
    assigns = _parse_assigns(body)
    always_assigns = _parse_trivial_always_assigns(body)

    always_count = len(re.findall(r"\balways\b", body))
    if always_count > len(always_assigns):
        _emit_gap(gaps, "unsupported-construct", "always blocks unsupported in subset converter", verilog_path)
    if re.search(r"\bgenerate\b", body):
        _emit_gap(gaps, "unsupported-construct", "generate blocks unsupported in subset converter", verilog_path)
    if re.search(r"\bcase\b", body):
        _emit_gap(gaps, "unsupported-construct", "case statements unsupported in subset converter", verilog_path)

    widths: dict[str, int] = {p.name: p.width for p in ports}
    for net in internal_nets:
        widths[net.name] = max(net.width, widths.get(net.name, 1))

    known_signals = set(widths.keys())
    internal_lhs = sorted({a.lhs for a in assigns if a.lhs not in known_signals})
    internal_lhs += sorted({a.lhs for a in always_assigns if a.lhs not in known_signals and a.lhs not in internal_lhs})
    for name in internal_lhs:
        widths[name] = max(widths.get(name, 1), 1)
    known_signals.update(internal_lhs)
    internal_names = sorted(n for n in known_signals if n not in {p.name for p in ports})
    signal_map = {name: _py_ident(name) for name in known_signals}

    lines: list[str] = []
    lines.append("# Auto-generated by awto-verilog2amaranth subset converter.")
    lines.append("# Supported: ANSI-style port declarations and continuous assign statements.")
    lines.append("from amaranth import Cat, Elaboratable, Module, Mux, Signal")
    lines.append("")
    lines.append(f"class {module_name.capitalize()}(Elaboratable):")
    lines.append("    def __init__(self):")

    if not ports and not internal_names:
        lines.append("        pass")
    else:
        for p in ports:
            py_name = signal_map[p.name]
            if p.width == 1:
                lines.append(f"        self.{py_name} = Signal()")
            else:
                lines.append(f"        self.{py_name} = Signal({p.width})")
        for name in internal_names:
            py_name = signal_map[name]
            width = widths.get(name, 1)
            if width == 1:
                lines.append(f"        self.{py_name} = Signal()")
            else:
                lines.append(f"        self.{py_name} = Signal({width})")

    lines.append("")
    lines.append("    def elaborate(self, platform):")
    lines.append("        m = Module()")
    for a in assigns:
        lhs = signal_map.get(a.lhs, _py_ident(a.lhs))
        rhs = _convert_expr(a.rhs, signal_map, gaps, verilog_path)
        lines.append(f"        m.d.comb += self.{lhs}.eq({rhs})")
    for a in always_assigns:
        lhs = signal_map.get(a.lhs, _py_ident(a.lhs))
        rhs = _convert_expr(a.rhs, signal_map, gaps, verilog_path)
        lines.append(f"        m.d.{a.domain} += self.{lhs}.eq({rhs})")
    lines.append("        return m")

    py_out = out_dir / f"{module_name}.py"
    py_out.write_text("\n".join(lines) + "\n", encoding="utf-8")

    gaps_path = out_dir / f"{module_name}.gaps.jsonl"
    with gaps_path.open("w", encoding="utf-8") as f:
        for g in gaps:
            f.write(json.dumps(g, sort_keys=True) + "\n")

    status = {
        "module": module_name,
        "source": str(verilog_path),
        "output": str(py_out),
        "ports": len(ports),
        "assigns": len(assigns),
        "gaps": len(gaps),
        "gaps_file": str(gaps_path),
    }
    (out_dir / f"{module_name}.status.json").write_text(json.dumps(status, indent=2) + "\n", encoding="utf-8")
    return status
