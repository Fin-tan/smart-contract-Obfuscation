#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Integer obfuscator — preserve pragma/SPDX, do NOT preserve comments.
- Protects: pragma solidity ...; and single-line SPDX comment form
- Does NOT protect: other comments (// ... or /* ... */) — numbers there may be obfuscated
- Preserves: string literals (no changes inside "..." or '...')
- Replaces integer literals (\b\d+\b) with semantically equivalent expressions
  (add/sub/mul/shift/xor) chosen at random, per BiAn description.
"""

import re
import random
from typing import Dict, Tuple

random.seed()

# ---------- Patterns to protect ----------
# pragma solidity ...;  (case-insensitive)
_PRAGMA_PATTERN = re.compile(r'^\s*pragma\s+solidity\s+[^;]+;', flags=re.IGNORECASE | re.MULTILINE)
# SPDX single-line comment form (common)
_SPDX_PATTERN = re.compile(r'^\s*//\s*SPDX-License-Identifier:[^\r\n]*', flags=re.IGNORECASE | re.MULTILINE)

# token pattern: string literal OR integer literal
# We keep string literals intact; integers outside strings are replaced.
_TOKEN_PATTERN = re.compile(r'("([^"\\]|\\.)*"|\'([^\'\\]|\\.)*\'|\b\d+\b)', re.DOTALL)

# ---------- Expression generator (BiAn-like strategies) ----------
def _gen_expr_for(n: int) -> str:
    strategies = ['add', 'sub', 'mul', 'shift', 'xor']
    strat = random.choice(strategies)

    if strat == 'add':
        r = random.randint(1, 100)
        return f"(({n}+{r})-{r})"
    if strat == 'sub':
        r = random.randint(1, 100)
        return f"(({n}-{r})+{r})"
    if strat == 'mul':
        # choose factor r != 0, small to avoid huge expressions
        r = random.randint(2, 10)
        return f"(({n}*{r})/{r})"
    if strat == 'shift':
        k = random.randint(1, 3)
        return f"(({n}<<{k})>>{k})"
    if strat == 'xor':
        r = random.randint(1, 255)
        return f"(({n}^{r})^{r})"
    return str(n)

# ---------- Helpers to placeholder/restore pragma/SPDX ----------
def _extract_placeholders(source: str) -> Tuple[str, Dict[str,str]]:
    placeholders: Dict[str,str] = {}
    counter = 0

    def _make_repl(m):
        nonlocal counter
        key = f"__PRAGMA_PLACEHOLDER_{counter}__"
        placeholders[key] = m.group(0)
        counter += 1
        return key

    s = source
    # protect SPDX first (single-line form)
    s = _SPDX_PATTERN.sub(_make_repl, s)
    # protect pragma solidity directives
    s = _PRAGMA_PATTERN.sub(_make_repl, s)
    return s, placeholders

def _restore_placeholders(source: str, placeholders: Dict[str,str]) -> str:
    out = source
    for k, v in placeholders.items():
        out = out.replace(k, v)
    return out

# ---------- Main API ----------
def obfuscate_integers_preserve_pragma(source: str) -> str:
    """
    Replace integer literals in `source` while preserving pragma/SPDX.
    Comments are NOT specially protected: numbers inside comments may be changed.
    String literals are preserved.
    """
    # 1) placeholder pragma/SPDX
    body, placeholders = _extract_placeholders(source)

    # 2) replace tokens: if token is string -> keep, else token is integer -> obfuscate
    def _repl(m):
        tok = m.group(0)
        if tok.startswith('"') or tok.startswith("'"):
            return tok
        # integer literal
        try:
            n = int(tok)
        except ValueError:
            return tok
        return _gen_expr_for(n)

    obf_body = _TOKEN_PATTERN.sub(_repl, body)

    # 3) restore pragma/SPDX
    final = _restore_placeholders(obf_body, placeholders)
    return final

# backward-compatible alias
obfuscate_integers = obfuscate_integers_preserve_pragma

# If run as script, do CLI
if __name__ == "__main__":
    import sys, os
    if len(sys.argv) < 2:
        print("Usage: python integer_obfuscator.py input.sol [output.sol]")
        sys.exit(1)
    inp = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) >= 3 else (os.path.splitext(inp)[0] + "_intobf.sol")
    with open(inp, 'r', encoding='utf-8') as f:
        s = f.read()
    res = obfuscate_integers_preserve_pragma(s)
    with open(out, 'w', encoding='utf-8') as f:
        f.write(res)
    print(f"Wrote: {out}")
