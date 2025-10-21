#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import re
import random

def _generate_integer_expression(n: int) -> str:
    if n == 0:
        return "0"

    strategies = ['add', 'sub', 'mul', 'shift', 'xor']
    strat = random.choice(strategies)

    if strat == 'add':
        r = random.randint(1, 100)
        return f"(({n}+{r})-{r})"
    elif strat == 'sub':
        r = random.randint(1, 100)
        return f"(({n}-{r})+{r})"
    elif strat == 'mul':
        r = random.randint(2, 10)
        return f"(({n}*{r})/{r})"
    elif strat == 'shift':
        k = random.randint(1, 3)
        return f"(({n}<<{k})>>{k})"
    elif strat == 'xor':
        r = random.randint(1, 255)
        return f"(({n}^{r})^{r})"
    else:
        return str(n)

def obfuscate_integers(source: str) -> str:
    pattern = r'(".*?"|\'.*?\'|\b\d+\b)'

    def replacer(m):
        tok = m.group(0)
        if tok.startswith('"') or tok.startswith("'"):
            return tok
        else:
            return _generate_integer_expression(int(tok))

    return re.sub(pattern, replacer, source, flags=re.DOTALL)
