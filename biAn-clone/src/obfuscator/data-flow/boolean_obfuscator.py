#!/usr/bin/env python3
"""
AST-based Boolean Splitter / Obfuscator for Solidity (py-solc-x / solcx version)

This version is byte-offset-safe (uses AST byte offsets) and normalizes newlines
to single '\n' when writing output to avoid doubled blank lines on Windows.
"""

from typing import List, Dict, Tuple, Optional
import re
import secrets
import os
import sys
import json

# solcx (py-solc-x)
try:
    import solcx
    from solcx import install_solc, set_solc_version, compile_files, get_installed_solc_versions
except Exception:
    solcx = None

DEFAULT_SOLC_VERSION = "0.8.30"

def _make_true_variant() -> str:
    """
    Return a complex boolean expression (string) that evaluates to true,
    and does NOT contain the literal 'true'. Many randomized variants,
    implemented with clean f-strings (no leftover placeholders).
    """
    def r1(): return secrets.randbelow(8) + 1       # 1..8
    def r2(): return secrets.randbelow(12) + 1      # 1..12
    def r3(): return secrets.randbelow(20) + 1      # 1..20

    pick = secrets.randbelow(12)
    if pick == 0:
        a, b = r1(), r2()
        return f"((((({a} + {b}) == {a + b}) && (({a} * {b}) >= {a * b})) || (({a} % {b}) < {b})))"
    if pick == 1:
        a, b = r2(), r1()
        return (
            f"(((({a} - {b}) == {a - b}) && ((({a} % {b}) + {b}) > {a - b})) "
            f"|| ((({a} * {b}) / {b}) == {a}))"
        )
    if pick == 2:
        a = r1(); b = a + 1
        return f"((((({a} << 1) >> 1) == {a}) && (({a} & {a}) == {a})) || ((({a} | {b}) >= {b})))"
    if pick == 3:
        a, b = r3(), r2()
        return (
            f"(((({a} * {b}) % {b}) == 0) && ((({a} + {b}) == {a + b}) || (({a} ^ {a}) == 0)))"
        )
    if pick == 4:
        a, b, c = r1(), r2(), r3()
        # explicit, safe f-string without stray braces
        return (
            f"((((( {a} + {b}) == {a + b}) && ((({b} * {c}) - {b}) >= ({b} * {c} - {b}))) "
            f"|| ((({c} % {a}) < {a}))) && (({a} & {a}) == {a}))"
        )
    if pick == 5:
        a, b = r2(), r1()
        left = f"((((({a} + {b}) == {a + b}) && (({a} * {b}) >= {a * b})) || (({a} % {b}) < {b})))"
        right = f"(({b} & {b}) == {b})"
        return f"(({left}) || ({right}))"
    if pick == 6:
        a, b = r2(), r2() + 1
        part1 = f"((((({a} + {b}) == {a + b}) && (({a} * {b}) >= {a * b})) || (({a} % {b}) < {b})))"
        part2 = f"((((({b} + {a}) == {b + a}) && (({b} * {a}) >= {b * a})) || (({b} % {a}) < {a})))"
        return f"(({part1}) || ({part2}))"
    if pick == 7:
        a, b = r3(), r1()
        epic = f"((((({a} + {b}) == {a + b}) && (({a} * {b}) >= {a * b})) || (({a} % {b}) < {b})))"
        triv = f"(({a} + {b} - {b}) == {a})"
        return f"(({epic}) && ({triv}))"
    if pick == 8:
        a, b = r2(), r1()
        return f"(((({a} % {b}) == 0) || ((({a} << 1) >> 1) == {a})) && ((({a} + {b}) == {a + b})))"
    if pick == 9:
        a, b, c = r1(), r2(), r1() + 2
        term1 = f"(({a} + {b}) == {a + b})"
        term2 = f"(({b} * {c}) >= {b * c})"
        term3 = f"(({c} % {a}) < {a})"
        return f"(({term1} && {term2}) || {term3})"
    if pick == 10:
        a, b = r3(), r2()
        return f"(((({a} ^ {a}) == 0) || ((({a} + {b}) == {a + b}))))"
    # pick == 11
    a, b = r1(), r2()
    return f"(((({a} + {b}) == {a + b}) && (({a} * {b}) >= {a * b})) || (({a} % {b}) < {b}))"

def _make_false_variant() -> str:
    """
    Return a complex boolean expression (string) that evaluates to false,
    WITHOUT the literal 'false'. Uses only type-safe arithmetic so Solidity
    compiler won't complain about signed/unsigned mismatches.
    """
    def r1(): return secrets.randbelow(8) + 1
    def r2(): return secrets.randbelow(12) + 1
    def r3(): return secrets.randbelow(20) + 1

    pick = secrets.randbelow(12)
    if pick == 0:
        a = r2()
        return f"((({a} + 1) == {a}) && ((({a} * 2) / 2) == {a}))"
    if pick == 1:
        a, b = r1(), r2()
        # inverted epic with modified constants so equality fails (safe)
        return f"((((({a} + {b}) == {a + b + 1}) && (({a} * {b}) >= {a * b + 1})) || (({a} % {b}) > {b})))"
    if pick == 2:
        a, b = r3(), r2()
        return f"((({a} << 1) >> 1) == {a + 1})"
    if pick == 3:
        a, b = r2(), r1()
        return f"((({a} * {b}) % {b}) == 1)"
    if pick == 4:
        a, b = r1(), r2()
        false_left = f"(({a} + 1) == {a})"
        true_right = _make_true_variant()
        return f"(({false_left}) && ({true_right}))"
    if pick == 5:
        a = r3()
        return f"((((({a} * {a}) + 1) == ({a} * {a})) || ((({a} ^ {a}) == 1))))"
    if pick == 6:
        a, b = r2(), r2() + 1
        part1 = f"((((({a} + {b}) == {a + b + 2}) && (({a} * {b}) >= {a * b + 3})) || (({a} % {b}) > {b})))"
        part2 = f"((((({b} + {a}) == {b + a + 1}) && (({b} * {a}) >= {b * a + 1})) || (({b} % {a}) > {a})))"
        return f"(({part1}) && ({part2}))"
    if pick == 7:
        a, b, c = r1(), r2(), r3()
        return f"((({a} & {a}) == {a + 1}) || ((({b} + {c}) == {b + c + 1})))"
    if pick == 8:
        a = r2()
        return f"((({a} % {a + 1}) == {a}) || (({a} + 1) == {a}))"
    if pick == 9:
        a, b = r1(), r1() + 1
        return f"((({a} * {b}) == {a * b + 1}) && (({b} & {b}) == {b}))"
    if pick == 10:
        a, b = r2(), r3()
        return f"((({a} - {b}) == {a - b + 1}))"
    # pick == 11
    a, b = r1(), r2()
    return f"(((({a} * {b}) + 1) == ({a} * {b})) || ((({a} + {b}) == {a + b + 2})))"

def ensure_solc(version: str = DEFAULT_SOLC_VERSION) -> bool:
    if solcx is None:
        return False
    try:
        installed = get_installed_solc_versions()
        if version in installed:
            set_solc_version(version)
            return True
        install_solc(version)
        set_solc_version(version)
        return True
    except Exception:
        return False

def _get_ast_via_solcx(file_path: str) -> Optional[dict]:
    if solcx is None:
        return None
    try:
        result = compile_files([file_path], output_values=["ast"])
        asts = []
        for k, v in result.items():
            ast = v.get("ast")
            if ast:
                asts.append(ast)
        if not asts:
            return None
        return {"asts": asts}
    except Exception:
        return None

def _parse_src(src_str: str) -> Optional[Tuple[int,int,int]]:
    try:
        parts = src_str.split(':')
        if len(parts) >= 2:
            start = int(parts[0]); length = int(parts[1])
            file_index = int(parts[2]) if len(parts) >= 3 else 0
            return start, length, file_index
    except Exception:
        return None
    return None

def _collect_bool_nodes_from_ast_container(ast_container: dict) -> List[Dict]:
    results: List[Dict] = []
    def walk(node):
        if isinstance(node, dict):
            attrs = node.get("attributes") or node.get("attributes", {})
            src = None
            if isinstance(attrs, dict):
                src = attrs.get("src") or node.get("src")
            else:
                src = node.get("src")
            value = None
            if isinstance(attrs, dict):
                v = attrs.get("value") or attrs.get("literal")
                if isinstance(v, str) and v in ("true","false"):
                    value = v
            node_value = node.get("value") or node.get("literal")
            if isinstance(node_value, str) and node_value in ("true","false"):
                value = node_value
            node_type = node.get("name") or node.get("nodeType") or node.get("type") or ""
            if (value in ("true","false") or (isinstance(node_type,str) and ("Literal" in node_type or "Boolean" in node_type))) and isinstance(src, str):
                results.append({"src": src, "value": value})
            for k, v in node.items():
                if k == "attributes":
                    continue
                if isinstance(v, (dict, list)):
                    walk(v)
        elif isinstance(node, list):
            for it in node:
                walk(it)
    for ast in ast_container.get("asts", []):
        walk(ast)
    return results

def _fallback_text_split(source_text: str) -> Tuple[str, List[Dict]]:
    # text-based (safe) replacer used when AST is unavailable
    mask = [False] * len(source_text)
    for m in re.finditer(r'/\*[\s\S]*?\*/', source_text):
        for i in range(m.start(), m.end()): mask[i] = True
    for m in re.finditer(r'//[^\n\r]*', source_text):
        for i in range(m.start(), m.end()): mask[i] = True
    for m in re.finditer(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'', source_text):
        for i in range(m.start(), m.end()): mask[i] = True

    ops = []
    for m in re.finditer(r'\b(true|false)\b', source_text):
        s, e = m.start(), m.end()
        if any(mask[s:e]): continue
        orig = m.group(1)
        repl = _make_true_variant() if orig == "true" else _make_false_variant()
        ops.append({"start": s, "end": e, "original": orig, "replacement": repl, "strategy": "fallback_text"})

    new_text = source_text
    for r in sorted(ops, key=lambda x: x["start"], reverse=True):
        new_text = new_text[:r["start"]] + r["replacement"] + new_text[r["end"]:]
    return new_text, ops

def _normalize_newlines(text: str) -> str:
    """
    Normalize CRLF and CR newlines to single LF ('\n'), and remove accidental
    repeated CRLF sequences. This prevents doubled blank lines on Windows.
    """
    # replace CRLF -> LF, CR -> LF
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text

def split_booleans_file(sol_file_path: str,
                        solc_version: str = DEFAULT_SOLC_VERSION,
                        write_out: bool = True,
                        out_path: Optional[str] = None) -> Tuple[str, List[Dict]]:
    """
    AST-based (byte-accurate) boolean splitting. If AST available, operates on bytes
    using AST-provided byte offsets. Otherwise falls back to text-based replacer.
    Returns (new_source_str, ops).
    """
    if not os.path.exists(sol_file_path):
        raise FileNotFoundError(f"File not found: {sol_file_path}")

    # Read raw bytes (so we can slice by byte offsets from solc)
    with open(sol_file_path, "rb") as f:
        src_bytes = f.read()

    ast_container = None
    if solcx is not None:
        try:
            ensure_solc(solc_version)
            ast_container = _get_ast_via_solcx(sol_file_path)
        except Exception:
            ast_container = None

    if ast_container is None:
        # fallback: decode text and use text-based replacer
        try:
            text = src_bytes.decode("utf-8")
        except Exception:
            text = src_bytes.decode("utf-8", errors="replace")
        new_text, ops = _fallback_text_split(text)
        # normalize newlines before writing
        new_text = _normalize_newlines(new_text)
        if write_out:
            print("[INFO] (in-memory mode) Boolean obfuscation completed.")
        return new_text, ops

    # AST available -> collect boolean literal nodes
    candidates = _collect_bool_nodes_from_ast_container(ast_container)

    # Build byte-range replacements: note solc src fields are byte offsets
    replacements = []
    for c in candidates:
        src_field = c.get("src")
        parsed = _parse_src(src_field) if isinstance(src_field, str) else None
        if not parsed:
            continue
        start, length, file_idx = parsed
        end = start + length
        # validate against byte length
        if start < 0 or end > len(src_bytes) or start >= end:
            continue
        original_slice_bytes = src_bytes[start:end]
        try:
            original_slice_str = original_slice_bytes.decode("utf-8")
        except Exception:
            original_slice_str = original_slice_bytes.decode("utf-8", errors="replace")
        literal = original_slice_str.strip()
        if literal not in ("true", "false"):
            if c.get("value") in ("true","false"):
                literal = c["value"]
            else:
                # ambiguous; skip
                continue
        replacement_str = _make_true_variant() if literal == "true" else _make_false_variant()
        replacement_bytes = replacement_str.encode("utf-8")
        replacements.append({"start": start, "end": end, "original_bytes": original_slice_bytes, "replacement_bytes": replacement_bytes, "original_str": original_slice_str, "replacement_str": replacement_str})

    # Deduplicate and remove overlaps (sort ascending, keep non-overlap)
    replacements_sorted = sorted(replacements, key=lambda x: (x["start"], -(x["end"] - x["start"])))
    non_overlap = []
    last_end = -1
    for r in replacements_sorted:
        if r["start"] >= last_end:
            non_overlap.append(r)
            last_end = r["end"]

    # Apply replacements at byte level from end -> start
    new_bytes = bytearray(src_bytes)
    ops = []
    for r in sorted(non_overlap, key=lambda x: x["start"], reverse=True):
        new_bytes[r["start"]:r["end"]] = r["replacement_bytes"]
        ops.append({"start": r["start"], "end": r["end"], "original": r["original_str"], "replacement": r["replacement_str"], "strategy": "ast_byte_split"})

    # Decode output as UTF-8 for returning and writing; then normalize newlines
    try:
        new_text = new_bytes.decode("utf-8")
    except Exception:
        new_text = new_bytes.decode("utf-8", errors="replace")
    new_text = _normalize_newlines(new_text)

    if write_out:
        print("[INFO] (in-memory mode) Boolean obfuscation completed — no file written.")

    return new_text, ops

def split_booleans_from_source(source_text: str, file_path_hint: Optional[str] = None, solc_version: str = DEFAULT_SOLC_VERSION) -> Tuple[str, List[Dict]]:
    """
    If file_path_hint exists, prefer AST-based file method; otherwise fallback to text.
    """
    if file_path_hint and os.path.exists(file_path_hint):
        try:
            return split_booleans_file(file_path_hint, solc_version=solc_version)
        except Exception:
            return _fallback_text_split(source_text)
    else:
        return _fallback_text_split(source_text)

def _default_paths_based_on_this_file() -> Tuple[str,str]:
    # match comment_remover pattern: go up 4 levels from this file to project root
    this = os.path.abspath(__file__)
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(this))))
    inp = os.path.join(project_root, "test", "test.sol")
    outp = os.path.join(project_root, "test", "output_boolean.sol")
    return inp, outp

def dump_ast_json(sol_file_path: str, out_json_path: Optional[str] = None, solc_version: str = DEFAULT_SOLC_VERSION) -> Optional[str]:
    """
    Compile Solidity file with solcx and dump AST to JSON.
    Returns written path if success, else None.
    """
    if solcx is None:
        print("[WARN] py-solc-x not installed, cannot dump AST.")
        return None

    try:
        ensure_solc(solc_version)
        result = compile_files([sol_file_path], output_values=["ast"])
    except Exception as e:
        print(f"[ERROR] solc compile failed: {e}")
        return None

    ast_container: Dict[str, dict] = {}
    for k, v in result.items():
        ast_container[k] = v.get("ast", {})

    if not out_json_path:
        out_json_path = os.path.join(os.path.dirname(os.path.abspath(sol_file_path)), "ast_boolean.json")

    try:
        with open(out_json_path, "w", encoding="utf-8") as f:
            json.dump(ast_container, f, ensure_ascii=False, indent=2)
        print(f"[INFO] AST dumped to: {out_json_path}")
        return out_json_path
    except Exception as e:
        print(f"[ERROR] failed to write AST JSON: {e}")
        return None

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Boolean obfuscator (AST-based with py-solc-x fallback). Default: test/test.sol -> test/output_boolean.sol")
    parser.add_argument("input", nargs="?", help="input solidity file (optional). If omitted defaults to PROJECT_ROOT/test/test.sol")
    parser.add_argument("--output", "-o", help="output file path (default: PROJECT_ROOT/test/output_boolean.sol)")
    parser.add_argument("--no-write", action="store_true", help="do not write output file (only print stats)")
    parser.add_argument("--solc", default=DEFAULT_SOLC_VERSION, help="solc version to install/use via py-solc-x")
    args = parser.parse_args()

    if args.input:
        inp = args.input
    else:
        inp, _ = _default_paths_based_on_this_file()

    if args.output:
        outp = args.output
    else:
        _, outp = _default_paths_based_on_this_file()

    write_out_flag = not args.no_write

    print(f"[INFO] Input file: {inp}")
    print(f"[INFO] Output file: {outp} (write_out={write_out_flag})")

    new_src, ops = split_booleans_file(inp, solc_version=args.solc, write_out=write_out_flag, out_path=outp)
    # Dump AST of the input Solidity file to JSON next to output_boolean.sol
    ast_out_path = os.path.join(os.path.dirname(outp), "ast_boolean.json")
    dump_ast_json(inp, out_json_path=ast_out_path, solc_version=args.solc)
    print(f"[INFO] Replacements applied: {len(ops)}")
