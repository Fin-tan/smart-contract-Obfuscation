#!/usr/bin/env python3

# -*- coding: utf-8 -*-

"""

Integer obfuscator — BiAn implementation (Corrected for Floating Points).



Updates:

- FIX: Now correctly ignores floating point numbers (e.g., 1.2, 0.8.1).

- Strategy: Identify decimals first and skip them, only obfuscate standalone integers.

"""



import re

import random

from typing import Dict, Tuple



random.seed()



# ---------- Patterns ----------

_PRAGMA_PATTERN = re.compile(r'^\s*pragma\s+solidity\s+[^;]+;', flags=re.IGNORECASE | re.MULTILINE)

_SPDX_PATTERN = re.compile(r'^\s*//\s*SPDX-License-Identifier:[^\r\n]*', flags=re.IGNORECASE | re.MULTILINE)



# Improved Regex Pattern:

# 1. Strings: "..." or '...'

# 2. Decimals/Floats: 1.2, 1., .5 (Matched so we can SKIP them)

# 3. Integers: 123 (Matched to OBFUSCATE)

_TOKEN_PATTERN = re.compile(

    r'("([^"\\]|\\.)*"|\'([^\'\\]|\\.)*\'|(\d+\.\d*|\.\d+)|(\b\d+\b))', 

    re.DOTALL

)



# ---------- BiAn Expression Generator ----------

def _gen_expr_for(n: int) -> str:

    """ Generates complex arithmetic expressions (No division, no float). """

    strategies = ['linear', 'multiplicative', 'compound']

    strat = random.choice(strategies)



    if strat == 'linear': # (a + b + diff)

        a = random.randint(1, 20); b = random.randint(1, 20)

        diff = n - (a + b)

        op = "+" if diff >= 0 else "-"

        return f"({a} + {b} {op} {abs(diff)})"



    elif strat == 'multiplicative': # (a * b + diff)

        a = random.randint(2, 10); b = random.randint(2, 10)

        diff = n - (a * b)

        op = "+" if diff >= 0 else "-"

        return f"({a} * {b} {op} {abs(diff)})"



    elif strat == 'compound': # (a + (b * c) - d)

        a = random.randint(0, 50); b = random.randint(2, 10); c = random.randint(2, 10)

        current = a + (b * c)

        diff = n - current

        op = "+" if diff >= 0 else "-"

        return f"({a} + ({b} * {c}) {op} {abs(diff)})"



    return str(n)



# ---------- Main Logic ----------

def obfuscate_integers_preserve_pragma(source: str) -> str:

    # 1. Extract pragmas to protect them

    placeholders = {}

    counter = 0

    def _mask(m):

        nonlocal counter

        k = f"__PRAGMA_{counter}__"

        placeholders[k] = m.group(0)

        counter += 1

        return k



    body = _SPDX_PATTERN.sub(_mask, source)

    body = _PRAGMA_PATTERN.sub(_mask, body)



    # 2. Process tokens

    def _repl(m):

        tok = m.group(0)

        

        # Group 4 is Decimal/Float -> SKIP (Return as is)

        if m.group(4): 

            return tok

            

        # Group 5 is Integer -> OBFUSCATE

        if m.group(5):

            try:

                n = int(tok)

                return _gen_expr_for(n)

            except ValueError:

                return tok

        

        # Strings or others -> SKIP

        return tok



    obf_body = _TOKEN_PATTERN.sub(_repl, body)



    # 3. Restore pragmas

    for k, v in placeholders.items():

        obf_body = obf_body.replace(k, v)

    

    return obf_body



# CLI Execution

if __name__ == "__main__":

    import sys, os

    if len(sys.argv) < 2:

        print("Usage: python bian_obfuscator.py input.sol [output.sol]")

    else:

        inp = sys.argv[1]

        out = sys.argv[2] if len(sys.argv) >= 3 else (os.path.splitext(inp)[0] + "_obf.sol")

        try:

            with open(inp, 'r', encoding='utf-8') as f: s = f.read()

            res = obfuscate_integers_preserve_pragma(s)

            with open(out, 'w', encoding='utf-8') as f: f.write(res)

            print(f"Obfuscated (Floating-point safe): {out}")

        except FileNotFoundError:

            print(f"Error: {inp} not found.")