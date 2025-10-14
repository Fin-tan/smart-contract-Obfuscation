#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Format Scrambler (Layout obfuscation) for Solidity (BiAn-like)
- Remove comments (optional)
- Normalize pragma to ^0.8.30
- Preserve string literals
- Tokenize non-string parts and rebuild with minimal whitespace so code remains valid but hard to read
Usage:
    python format_scrambler.py input.sol output.sol
"""

import re
import sys
from typing import List, Tuple

# ---------- Utility: classify token ----------
def is_identifier(tok: str) -> bool:
    return bool(re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', tok))

def is_number(tok: str) -> bool:
    return bool(re.match(r'^(0x[0-9A-Fa-f]+|\d+)$', tok))

def is_alnum_token(tok: str) -> bool:
    return is_identifier(tok) or is_number(tok)

# ---------- Step 1: split into string-literal segments (preserve strings) ----------
def split_strings(src: str) -> List[Tuple[bool, str]]:
    """
    Returns list of tuples (is_string, text_segment)
    is_string True means this segment is a quoted string (keep intact)
    is_string False means segment outside strings (we will process)
    Handles single-quote and double-quote strings and escaped quotes.
    """
    i = 0
    n = len(src)
    parts = []
    while i < n:
        if src[i] in ("'", '"'):
            quote = src[i]
            start = i
            i += 1
            while i < n:
                if src[i] == '\\':
                    # escape sequence, skip next char too
                    i += 2
                elif src[i] == quote:
                    i += 1
                    break
                else:
                    i += 1
            parts.append((True, src[start:i]))
        else:
            start = i
            while i < n and src[i] not in ("'", '"'):
                i += 1
            parts.append((False, src[start:i]))
    return parts

# ---------- Step 2: comment removal (on non-string parts) ----------
def remove_comments_from_segment(seg: str) -> str:
    # Remove multi-line comments first (/* ... */)
    seg = re.sub(r'/\*[\s\S]*?\*/', '', seg)
    # Remove single-line comments (//...) - includes /// natspec
    seg = re.sub(r'//[^\n\r]*', '', seg)
    return seg

# ---------- Step 3: normalize pragma ----------
def normalize_pragma(seg: str, solidity_version: str = "^0.8.30") -> str:
    # Replace any pragma solidity ... ; with pragma solidity ^0.8.30;
    seg = re.sub(r'pragma\s+solidity\s+[^;]+;', f'pragma solidity {solidity_version};', seg, flags=re.IGNORECASE)
    return seg

# ---------- Step 4: simple tokenizer for non-string segments ----------
def tokenize_non_string(s: str) -> List[str]:
    tokens: List[str] = []
    i = 0
    n = len(s)
    hexdigits = set("0123456789abcdefABCDEF")
    while i < n:
        c = s[i]
        if c.isspace():
            # collapse continuous whitespace into a single space token to mark separation
            j = i
            while j < n and s[j].isspace():
                j += 1
            tokens.append(' ')
            i = j
        elif c.isalpha() or c == '_':
            j = i + 1
            while j < n and (s[j].isalnum() or s[j] == '_'):
                j += 1
            tokens.append(s[i:j])
            i = j
        elif c.isdigit():
            # number or decimal (we keep simple integer or hex)
            if i + 1 < n and s[i:i+2].lower() == '0x':
                j = i + 2
                while j < n and s[j] in hexdigits:
                    j += 1
                tokens.append(s[i:j])
                i = j
            else:
                j = i + 1
                while j < n and s[j].isdigit():
                    j += 1
                tokens.append(s[i:j])
                i = j
        else:
            # check multi-char operators
            two = s[i:i+2]
            multi_ops = {'==','!=','<=','>=','+=','-=','*=','/=','&&','||','<<','>>','=>','->','::','%='}
            if two in multi_ops:
                tokens.append(two)
                i += 2
            else:
                tokens.append(c)
                i += 1
    return tokens

# ---------- Step 5: rebuild with minimal safe spacing ----------
def rebuild_minimal(tokens: List[str]) -> str:
    out_tokens: List[str] = []
    prev = None
    for tok in tokens:
        if tok == ' ':
            # we treat whitespace marker by deciding explicitly below; skip default handling
            # set a marker that separation exists
            if prev is None:
                # leading whitespace -> ignore
                continue
            else:
                # record marker by a special token; we'll decide to insert a space when needed
                # represent separation by None placeholder
                out_tokens.append(None)
                prev = None  # we reset prev to force next token treated as first after sep
                continue
        # append current token
        if not out_tokens:
            out_tokens.append(tok)
        else:
            # previous actual token (skip None markers)
            # find last token that is not None
            last_actual = None
            for t in reversed(out_tokens):
                if t is not None:
                    last_actual = t
                    break
            need_space = False
            if last_actual is None:
                # previous was only separators -> no forced last token
                need_space = False
            else:
                a = last_actual
                b = tok
                # If both are alnum-like tokens -> need space: "uint public"
                if is_alnum_token(a) and is_alnum_token(b):
                    need_space = True
                # If previous is ')' or '}' and current is alnum -> insert space: ") public"
                elif a in (')','}') and is_alnum_token(b):
                    need_space = True
                # If previous is alnum and current is '(' -> no space (function call/decl)
                elif is_alnum_token(a) and b == '(':
                    need_space = False
                # If prev is identifier and current is identifier-like but separated by punctuation before -> default no
                else:
                    need_space = False
            # If we had a separator marker (None) at end of out_tokens, ensure at least one space
            if out_tokens and out_tokens[-1] is None:
                # remove marker and enforce a single space in output
                out_tokens.pop()
                # decide whether to actually output a space: if last_actual exists and not punctuation requiring no space
                # We'll be conservative: put a space except when last_actual is '(' or last_actual is punctuation that binds without spaces
                if last_actual not in ('(', '{', '[', '.', ',', ';'):
                    out_tokens.append(' ')
            else:
                # when no explicit separator marker, add space only if need_space True
                if need_space:
                    out_tokens.append(' ')
            out_tokens.append(tok)
        prev = tok
    # join out tokens, skipping any remaining None
    return ''.join([t for t in out_tokens if t is not None])

# ---------- Top-level scramble function ----------
def scramble_format(source: str, solidity_version: str = "^0.8.30", remove_comments: bool = True, one_line: bool = True) -> str:
    """
    Main API:
      - source: original solidity code
      - solidity_version: pragma target version (default ^0.8.30)
      - remove_comments: whether to delete comments (default True)
      - one_line: whether output single-line (True) or insert minimal newlines (False)
    """
    parts = split_strings(source)
    processed_parts: List[str] = []
    for is_str, seg in parts:
        if is_str:
            # keep string exactly as-is
            processed_parts.append(seg)
        else:
            # handle comments removal
            working = seg
            if remove_comments:
                working = remove_comments_from_segment(working)
            # normalize pragma
            working = normalize_pragma(working, solidity_version=solidity_version)
            # tokenize and rebuild minimal spacing
            tokens = tokenize_non_string(working)
            rebuilt = rebuild_minimal(tokens)
            processed_parts.append(rebuilt)
    result = ''.join(processed_parts)
    if one_line:
        # collapse all newlines into space and then compress multiple spaces to single
        result = re.sub(r'[\r\n]+', ' ', result)
        result = re.sub(r'\s+', ' ', result).strip()
    else:
        # keep linebreaks where there are semicolons or braces for light readability
        # insert newline after ; and { and before }
        result = re.sub(r';\s*', ';\n', result)
        result = re.sub(r'\{\s*', '{\n', result)
        result = re.sub(r'\s*\}', '\n}', result)
        # compress multiple blank lines
        result = re.sub(r'\n\s*\n+', '\n', result)
    return result

# ---------- CLI ----------
def main():
    if len(sys.argv) < 3:
        print("Usage: python format_scrambler.py input.sol output.sol [--keep-comments] [--multi-line]")
        return
    input_path = sys.argv[1]
    output_path = sys.argv[2]
    keep_comments = '--keep-comments' in sys.argv
    multi_line = '--multi-line' in sys.argv
    with open(input_path, 'r', encoding='utf-8') as f:
        src = f.read()
    out = scramble_format(src, solidity_version="^0.8.30", one_line=not multi_line)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(out)
    print(f"[OK] Scrambled layout written to {output_path}")

if __name__ == "__main__":
    main()
