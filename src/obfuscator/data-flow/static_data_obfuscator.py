#!/usr/bin/env python3
import json
import re
from typing import List, Dict, Tuple, Optional

def _parse_src_field(src: str) -> Tuple[int,int]:
    """
    src format usually: "start:length" or "start:length:fileIndex"
    Return (start, end)
    """
    parts = src.split(':')
    start = int(parts[0])
    length = int(parts[1]) if len(parts) > 1 else 0
    return start, start + length

def _rec_find_literals(node, results: List[dict]):
    """
    Recursively traverse AST and collect ONLY literal nodes.
    We support solc's newer AST (nodeType == 'Literal') and older 'attributes'
    layout where attributes.nodeType/attributes.value exist.
    Appends dicts: {'value','kind','src'}.
    """
    if isinstance(node, dict):
        node_type = node.get('nodeType') or node.get('name') or ''
        if node_type == 'Literal':
            src = node.get('src')
            kind = (node.get('kind') or '').lower()
            # value resolution per solc AST
            val = node.get('value')
            if val is None:
                # hex string literal may use hexValue
                val = node.get('hexValue')
            # normalize types
            if isinstance(val, bool):
                val = 'true' if val else 'false'
            if isinstance(val, (int, float)):
                val = str(val)
            if src and val is not None:
                results.append({'value': str(val), 'kind': kind, 'src': src})
        else:
            # Older AST formats may embed literals under 'attributes' with a nodeType hint
            attrs = node.get('attributes')
            if isinstance(attrs, dict) and (attrs.get('nodeType') == 'Literal' or 'literal' in str(attrs.get('nodeType','')).lower()):
                src = node.get('src') or attrs.get('src')
                kind = (attrs.get('kind') or '').lower()
                val = attrs.get('value') or attrs.get('hexValue')
                if isinstance(val, bool):
                    val = 'true' if val else 'false'
                if isinstance(val, (int, float)):
                    val = str(val)
                if src and val is not None:
                    results.append({'value': str(val), 'kind': kind, 'src': src})
        # traverse children
        for v in node.values():
            if isinstance(v, (dict, list)):
                _rec_find_literals(v, results)
    elif isinstance(node, list):
        for item in node:
            _rec_find_literals(item, results)

def _collect_from_ast(ast_json: dict) -> List[dict]:
    found = []
    _rec_find_literals(ast_json, found)
    # filter duplicates that don't have src
    found = [f for f in found if 'src' in f and f['src']]
    return found

def _collect_exclusion_ranges(ast_json: dict) -> List[Tuple[int,int]]:
    """Collect src ranges to exclude (e.g., inside require/assert calls, pragma directives)."""
    excl: List[Tuple[int,int]] = []

    def _parse_src(src: str) -> Optional[Tuple[int,int]]:
        try:
            parts = src.split(':')
            start = int(parts[0]); ln = int(parts[1])
            return start, start + ln
        except Exception:
            return None

    def walk(node):
        if isinstance(node, dict):
            ntype = node.get('nodeType') or node.get('name') or ''
            # Exclude PragmaDirective (pragma solidity ...;)
            if str(ntype).lower() == 'pragmadirective':
                s = node.get('src')
                pr = _parse_src(s) if isinstance(s, str) else None
                if pr:
                    excl.append(pr)
            elif str(ntype).lower().find('functioncall') != -1:
                # Identify require/assert calls via expression.name
                expr = node.get('expression')
                name = None
                if isinstance(expr, dict):
                    name = expr.get('name') or expr.get('identifier') or expr.get('value')
                    # MemberAccess require/assert not expected, but guard
                    if name is None and expr.get('nodeType') == 'Identifier':
                        name = expr.get('name')
                if isinstance(name, str) and name in ('require', 'assert'):
                    s = node.get('src')
                    pr = _parse_src(s) if isinstance(s, str) else None
                    if pr:
                        excl.append(pr)
            for v in node.values():
                if isinstance(v, (dict, list)):
                    walk(v)
        elif isinstance(node, list):
            for it in node:
                walk(it)

    walk(ast_json)
    return excl

def _fallback_regex_find(source: str) -> List[dict]:
    results = []
    
    # First, find and exclude pragma directive ranges
    pragma_ranges: List[Tuple[int, int]] = []
    for m in re.finditer(r'pragma\s+solidity\s+[^;]+;', source, re.IGNORECASE):
        pragma_ranges.append((m.start(), m.end()))
    
    def _is_in_pragma(pos: int) -> bool:
        for (start, end) in pragma_ranges:
            if start <= pos < end:
                return True
        return False
    
    # find boolean literals
    for m in re.finditer(r'\b(true|false)\b', source):
        if not _is_in_pragma(m.start()):
            results.append({'value': m.group(1), 'kind': 'bool', 'start': m.start(), 'end': m.end()})
    
    # find integer literals (simple integers, not hex) - exclude those in pragma
    for m in re.finditer(r'\b([0-9]+)\b', source):
        if not _is_in_pragma(m.start()):
            results.append({'value': m.group(1), 'kind': 'number', 'start': m.start(), 'end': m.end()})
    
    # find hex literals (0x... or hex"...")
    for m in re.finditer(r'\b(0x[0-9a-fA-F]+|hex"[^"]+")\b', source):
        if not _is_in_pragma(m.start()):
            results.append({'value': m.group(1), 'kind': 'hex', 'start': m.start(), 'end': m.end()})
    
    # find simple string literal double/single quoted
    for m in re.finditer(r'(\"([^\"\\]|\\.)*\"|\'([^\'\\]|\\.)*\')', source):
        if not _is_in_pragma(m.start()):
            raw = m.group(0)
            results.append({'value': raw, 'kind': 'string', 'start': m.start(), 'end': m.end()})
    
    return results

def _build_accessors_with_arrays(ints: List[str], bools: List[str], strings: List[str], hexes: List[str]) -> str:
    """Build array-backed accessor functions, as described in BiAn."""
    parts: List[str] = []
    if ints:
        body = [
            "function __const_ints() internal pure returns (uint256[] memory t) {",
            f"    t = new uint256[]({len(ints)});"
        ]
        for i, v in enumerate(ints):
            body.append(f"    t[{i}] = {v};")
        body.append("}")
        body.append("function __get_int(uint idx) internal pure returns (uint256) { uint256[] memory t = __const_ints(); return t[idx]; }")
        parts.append('\n'.join(body))
    if bools:
        body = [
            "function __const_bools() internal pure returns (bool[] memory t) {",
            f"    t = new bool[]({len(bools)});"
        ]
        for i, v in enumerate(bools):
            vv = 'true' if str(v).lower() in ('true','1') else 'false'
            body.append(f"    t[{i}] = {vv};")
        body.append("}")
        body.append("function __get_bool(uint idx) internal pure returns (bool) { bool[] memory t = __const_bools(); return t[idx]; }")
        parts.append('\n'.join(body))
    if strings:
        body = [
            "function __const_strings() internal pure returns (string[] memory t) {",
            f"    t = new string[]({len(strings)});"
        ]
        for i, v in enumerate(strings):
            lit = v
            if not (lit.startswith('"') or lit.startswith("'")):
                esc = lit.replace('"','\\"')
                lit = f'"{esc}"'
            elif lit.startswith("'") and lit.endswith("'"):
                esc = lit[1:-1].replace('"','\\"')
                lit = f'"{esc}"'
            body.append(f"    t[{i}] = {lit};")
        body.append("}")
        body.append("function __get_string(uint idx) internal pure returns (string memory) { string[] memory t = __const_strings(); return t[idx]; }")
        parts.append('\n'.join(body))
    if hexes:
        body = [
            "function __const_bytes() internal pure returns (bytes[] memory t) {",
            f"    t = new bytes[]({len(hexes)});"
        ]
        for i, hv in enumerate(hexes):
            # Expect hv either like 0xABC... or raw hex without 0x
            lit = hv
            if isinstance(lit, str):
                if lit.startswith('0x') or lit.startswith('0X'):
                    # convert to hex"..." literal without 0x prefix
                    lit = 'hex"' + lit[2:] + '"'
                elif lit.startswith('hex"'):
                    pass
                else:
                    # assume raw hex without 0x
                    lit = 'hex"' + lit + '"'
            body.append(f"    t[{i}] = {lit};")
        body.append("}")
        body.append("function __get_bytes(uint idx) internal pure returns (bytes memory) { bytes[] memory t = __const_bytes(); return t[idx]; }")
        parts.append('\n'.join(body))
    return '\n\n'.join(parts)

def _token_stream_obfuscate(source_text: str) -> str:
    """Format-preserving literal replacement: keep original line order & spacing, only swap literal tokens.
    Skips pragma/SPDX, require/assert argument bodies.
    """
    lines = source_text.splitlines(keepends=True)
    text = source_text

    # Build a mask over the entire text for comments (//, /* */) and string literals to avoid replacing inside them
    mask = [False] * len(text)
    def mark(a: int, b: int):
        a = max(a, 0); b = min(b, len(mask))
        for i in range(a, b):
            mask[i] = True

    # Block comments
    for m in re.finditer(r'/\*[\s\S]*?\*/', text):
        mark(m.start(), m.end())
    # Line comments
    for m in re.finditer(r'//[^\n\r]*', text):
        mark(m.start(), m.end())
    # String literals (single and double quoted, with escapes)
    for m in re.finditer(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'', text):
        mark(m.start(), m.end())

    # Gather exclusion ranges for require/assert parentheses to avoid altering semantics
    excl: List[Tuple[int,int]] = []
    for m in re.finditer(r'\b(require|assert)\s*\(', text):
        start = m.end() - 1
        depth = 0
        i = start
        while i < len(text):
            c = text[i]
            if c == '(':
                depth += 1
            elif c == ')':
                depth -= 1
                if depth == 0:
                    excl.append((start, i+1))
                    break
            i += 1
    def in_excl(pos: int) -> bool:
        for a,b in excl:
            if a <= pos < b:
                return True
        return False

    # First pass: collect unique bool/int literals in order (exclude pragma & SPDX lines, and masked regions)
    bool_vals: List[str] = []
    int_vals: List[str] = []
    def add_bool(v: str):
        if v not in bool_vals:
            bool_vals.append(v)
    def add_int(v: str):
        if v not in int_vals:
            int_vals.append(v)

    offset = 0
    for ln in lines:
        if ln.lstrip().startswith('pragma solidity') or ln.lstrip().startswith('// SPDX-License-Identifier'):
            offset += len(ln); continue
        for m in re.finditer(r'\b(true|false|\d+)\b', ln):
            abs_pos = offset + m.start()
            if in_excl(abs_pos) or mask[abs_pos]:
                continue
            val = m.group(1)
            if val in ('true','false'):
                add_bool(val)
            else:
                add_int(val)
        offset += len(ln)

    # Second pass: replace per line using indexes, preserving spacing
    def bool_idx(v: str) -> int: return bool_vals.index(v)
    def int_idx(v: str) -> int: return int_vals.index(v)

    out_lines: List[str] = []
    offset = 0
    for ln in lines:
        if ln.lstrip().startswith('pragma solidity') or ln.lstrip().startswith('// SPDX-License-Identifier'):
            out_lines.append(ln); offset += len(ln); continue
        def repl(m: re.Match) -> str:
            abs_pos = offset + m.start()
            if in_excl(abs_pos) or mask[abs_pos]:
                return m.group(0)
            tok = m.group(1)
            if tok in ('true','false'):
                return f'__get_bool({bool_idx(tok)})'
            else:
                return f'__get_int({int_idx(tok)})'
        new_ln = re.sub(r'\b(true|false|\d+)\b', repl, ln)
        out_lines.append(new_ln)
        offset += len(ln)
    out = ''.join(out_lines)

    # Accessor block
    acc_parts: List[str] = []
    if int_vals:
        acc_parts.append('function __const_ints() internal pure returns (uint256[] memory t) {')
        acc_parts.append(f'    t = new uint256[]({len(int_vals)});')
        for i,v in enumerate(int_vals):
            acc_parts.append(f'    t[{i}] = {v};')
        acc_parts.append('}')
        acc_parts.append('function __get_int(uint idx) internal pure returns (uint256) {')
        acc_parts.append('    uint256[] memory t = __const_ints();')
        acc_parts.append('    return t[idx];')
        acc_parts.append('}')
    if bool_vals:
        acc_parts.append('function __const_bools() internal pure returns (bool[] memory t) {')
        acc_parts.append(f'    t = new bool[]({len(bool_vals)});')
        for i,v in enumerate(bool_vals):
            acc_parts.append(f'    t[{i}] = {v};')
        acc_parts.append('}')
        acc_parts.append('function __get_bool(uint idx) internal pure returns (bool) {')
        acc_parts.append('    bool[] memory t = __const_bools();')
        acc_parts.append('    return t[idx];')
        acc_parts.append('}')

    if acc_parts:
        block = '\n    // === static data accessors inserted by static_data_obfuscator ===\n' + '\n'.join('    '+l for l in acc_parts) + '\n'
        cpos = out.find('contract ')
        if cpos != -1:
            bpos = out.find('{', cpos)
            if bpos != -1:
                out = out[:bpos+1] + '\n' + block + out[bpos+1:]

    # Beautify: collapse excessive blank lines (>2 -> 1)
    # Preserve Windows newlines by detecting dominant style
    use_crlf = '\r\n' in out
    nl = '\r\n' if use_crlf else '\n'
    # Normalize to LF temporarily for regex ease
    temp = out.replace('\r\n', '\n')
    temp = re.sub(r'\n{3,}', '\n\n', temp)  # collapse runs >=3
    out = temp.replace('\n', nl)
    return out

def obfuscate_static_data(source_text: str, ast_json_path: Optional[str]=None) -> str:
    """Public API selecting the robust token replacement path.
    (Legacy AST logic kept below but currently bypassed.)"""
    return _token_stream_obfuscate(source_text)
    # Legacy AST path (disabled)
    literals = []
    use_ranges = False
    excl_ranges: List[Tuple[int,int]] = []
    try:
        if ast_json_path:
            with open(ast_json_path, 'r', encoding='utf-8') as f:
                ast = json.load(f)
            literals = _collect_from_ast(ast)
            excl_ranges = _collect_exclusion_ranges(ast)
            # parse src to start,end for those entries
            parsed = []
            for item in literals:
                try:
                    start,end = _parse_src_field(item['src'])
                    parsed.append({'value': item['value'], 'kind': item.get('kind',''), 'start': start, 'end': end})
                except Exception:
                    # ignore nodes we can't parse
                    continue
            literals = parsed
            if literals:
                use_ranges = True
    except Exception:
        # AST parsing failed — fallback later
        literals = []

    # (AST-based path retained below but currently bypassed by early return above.)
    if not use_ranges:
        literals = _fallback_regex_find(source_text)

    # Normalize kinds and make lists of unique values preserving order
    int_vals: List[str] = []
    bool_vals: List[str] = []
    str_vals: List[str] = []
    hex_vals: List[str] = []

    # For AST-case we have dicts with start,end (byte offsets). For fallback, start/end are char offsets.
    # Build mapping from (start,end) -> replacement text
    replacements: Dict[Tuple[int,int], str] = {}

    # Deduplicate value lists and provide indices
    def _index_of(lst, val):
        try:
            return lst.index(val)
        except ValueError:
            lst.append(val)
            return len(lst)-1

    def _is_excluded(pos: int) -> bool:
        for (a,b) in excl_ranges:
            if a <= pos < b:
                return True
        return False

    for item in literals:
        val = item['value']
        kind = item.get('kind','').lower()
        st = item.get('start')
        if isinstance(st, int) and _is_excluded(st):
            # skip literals within require/assert call ranges
            continue
        # Heuristic to classify
        if kind and 'bool' in str(kind):
            idx = _index_of(bool_vals, val)
            rep = f"__get_bool({idx})"
        elif kind and ('string' in str(kind) or (isinstance(val, str) and (val.startswith('"') or val.startswith("'")))):
            # keep raw quotes if present
            literal = val
            if literal.startswith("'") and literal.endswith("'"):
                # convert to double quotes for Solidity strings
                literal = '"' + literal[1:-1].replace('"','\\"') + '"'
            idx = _index_of(str_vals, literal)
            rep = f"__get_string({idx})"
        elif 'hex' in kind or re.fullmatch(r'0x[0-9a-fA-F]+', str(val) or ''):
            # hex string literal -> bytes[]
            literal = str(val)
            idx = _index_of(hex_vals, literal)
            rep = f"__get_bytes({idx})"
        else:
            # try numeric / boolean detection
            if re.fullmatch(r'\d+', val):
                idx = _index_of(int_vals, val)
                rep = f"__get_int({idx})"
            elif val.lower() in ('true','false'):
                idx = _index_of(bool_vals, val.lower())
                rep = f"__get_bool({idx})"
            else:
                # fallback treat as string
                literal = val
                if not (literal.startswith('"') or literal.startswith("'")):
                    literal = '"' + literal.replace('"','\\"') + '"'
                idx = _index_of(str_vals, literal)
                rep = f"__get_string({idx})"

        # attach replacement
        if 'start' in item and 'end' in item:
            replacements[(item['start'], item['end'])] = rep
        else:
            # maybe AST used different fields; skip
            pass

    if not replacements:
        # Nothing to replace
        return source_text

    # Apply replacements. If we have AST byte offsets (use_ranges True), operate on UTF-8 bytes.
    if use_ranges:
        s_bytes = source_text.encode('utf-8')
        # Strict guard: only replace when the slice text actually matches the literal shape
        def _looks_like(kind: str, raw: str) -> bool:
            k = (kind or '').lower()
            t = raw.strip()
            if 'bool' in k:
                return t in ('true','false')
            if 'number' in k:
                return bool(re.fullmatch(r'\d+', t))
            if 'string' in k:
                return (t.startswith('"') and t.endswith('"')) or (t.startswith("'") and t.endswith("'"))
            if 'hex' in k or t.startswith('0x') or t.startswith('0X') or t.startswith('hex"'):
                return True
            # fallback: very conservative
            return False
        # Filter replacements by validating the current slice text
        valid: Dict[Tuple[int,int], str] = {}
        for (a,b), rep in replacements.items():
            if a < 0 or b > len(s_bytes) or a >= b:
                continue
            raw = s_bytes[a:b].decode('utf-8', errors='ignore')
            # find the original kind from literals list
            # Build a small map for quick lookup
        
        kind_map: Dict[Tuple[int,int], str] = {}
        for it in literals:
            st = it.get('start'); ed = it.get('end');
            if isinstance(st, int) and isinstance(ed, int):
                kind_map[(st,ed)] = it.get('kind','')
        for (a,b), rep in replacements.items():
            if a < 0 or b > len(s_bytes) or a >= b:
                continue
            raw = s_bytes[a:b].decode('utf-8', errors='ignore')
            k = kind_map.get((a,b), '')
            if _looks_like(k, raw):
                valid[(a,b)] = rep
        replacements = valid
        # Remove overlaps by sorting, then keeping non-overlapping slices
        ranges_sorted = sorted(replacements.keys(), key=lambda x: (x[0], x[1]))
        non_overlap: List[Tuple[int,int]] = []
        last_end = -1
        for a,b in ranges_sorted:
            if a >= last_end:
                non_overlap.append((a,b))
                last_end = b
        # Apply from end to start on bytes
        buf = bytearray(s_bytes)
        for a,b in sorted(non_overlap, key=lambda x: x[0], reverse=True):
            rep_bytes = replacements[(a,b)].encode('utf-8')
            if a < 0 or b > len(buf) or a >= b:
                continue
            buf[a:b] = rep_bytes
        s = buf.decode('utf-8')
    else:
        # Fallback path operates on str character offsets
        sorted_ranges = sorted(replacements.keys(), key=lambda x: x[0], reverse=True)
        s = source_text
        for (st, ed) in sorted_ranges:
            rep = replacements[(st, ed)]
            if st < 0 or ed > len(s) or st >= ed:
                continue
            s = s[:st] + rep + s[ed:]

    # Build accessor functions
    accessor_code = _build_accessors_with_arrays(int_vals, bool_vals, str_vals, hex_vals)
    if not accessor_code:
        return s

    # Insert accessor code inside first contract body (after first '{' following 'contract ')
    contract_pos = s.find('contract ')
    insert_at = None
    if contract_pos != -1:
        # find the first '{' after contract keyword
        brace_pos = s.find('{', contract_pos)
        if brace_pos != -1:
            # insert after the brace and a newline
            insert_at = brace_pos + 1
            # prepare indentation: 4 spaces
            accessor_block = "\n\n    // === static data accessors inserted by static_data_obfuscator ===\n"
            accessor_block += '\n'.join('    ' + line if line else '' for line in accessor_code.split('\n'))
            accessor_block += '\n\n'
            s = s[:insert_at] + accessor_block + s[insert_at:]
    else:
        # fallback: insert after pragma solidity line
        m = re.search(r'pragma\s+solidity\s+[^\n;]+;?', s)
        if m:
            insert_at = m.end()
            accessor_block = "\n\n// === static data accessors inserted by static_data_obfuscator ===\n"
            accessor_block += accessor_code + "\n\n"
            s = s[:insert_at] + accessor_block + s[insert_at:]
        else:
            # as last resort, prepend
            s = "// === static data accessors inserted by static_data_obfuscator ===\n" + accessor_code + "\n\n" + s

    return s

# For convenience, expose a single function name used by demo
def transform_static_to_dynamic(source: str, ast_path: Optional[str]=None) -> str:
    return obfuscate_static_data(source, ast_path)
