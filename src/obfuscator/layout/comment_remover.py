#!/usr/bin/env python3
"""
BiAn Comment Remover - Smart Contract Comment Removal
Remove all comments from Solidity source code for distribution.
Based on: BiAn Smart Contract Source Code Obfuscation Paper
"""

import os
import re
import time
from typing import List, Dict, Tuple, Optional

class CommentRemover:
    """Remove comments from smart contract source code"""
    
    def __init__(self, source: str):
        self.src = source

    def remove_comments(self) -> Tuple[str, List[Dict]]:
        """Remove all comments (line, natspec, block) from the source code.

        Performs a single-pass scan over the source to avoid double-processing
        the same regions (e.g., `///` being matched by both `///` and `//`).
        """
        result = self.src
        operations: List[Dict] = []

        # Combined comment pattern. Order matters: match natspec before //.
        combined_pattern = r'/\*[\s\S]*?\*/|///[^\n\r]*|//[^\n\r]*'

        for match in re.finditer(combined_pattern, result):
            start, end = match.start(), match.end()
            comment_text = match.group()

            # Skip if inside string literal
            if self._is_inside_string(start, result):
                continue

            operations.append({
                'start': start,
                'end': end,
                'replacement': '',  # removal only
                'strategy': 'remove',
                'original': comment_text
            })

        # Apply operations in reverse order to maintain positions
        for op in sorted(operations, key=lambda x: x['start'], reverse=True):
            result = result[:op['start']] + op['replacement'] + result[op['end']:]

        return result, operations

    def _is_inside_string(self, position: int, text: str) -> bool:
        """Check if position is inside a string literal"""
        text_before = text[:position]
        
        # Count unescaped double quotes
        dquote_count = 0
        i = 0
        while i < len(text_before):
            if text_before[i] == '"' and (i == 0 or text_before[i-1] != '\\'):
                dquote_count += 1
            i += 1
        
        return dquote_count % 2 == 1

def run_comment_removal(source_text: Optional[str] = None, file_path: Optional[str] = None) -> str:
    """Run comment removal on test contract"""
    
    if not source_text and not file_path:
        raise ValueError("Must provide either source_text or file_path to run_comment_removal().")

    # Load source
    if source_text is None:
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Source file not found: {file_path}")
        with open(file_path, 'r', encoding='utf-8') as f:
            source_text = f.read()

    # Perform removal
    remover = CommentRemover(source_text)
    start_time = time.time()
    removed_code, operations = remover.remove_comments()
    duration = time.time() - start_time

    # Comment removal completed silently
    return removed_code

def show_comparison(original_code: str, processed_code: str) -> None:
    """Display before/after comment counts for quick sanity check."""
    pattern = r'//[^\n\r]*|/\*[\s\S]*?\*/|///[^\n\r]*'
    orig_comments = len(re.findall(pattern, original_code))
    new_comments = len(re.findall(pattern, processed_code))
    print(f"[INFO] Comments before: {orig_comments}, after removal: {new_comments}")

if __name__ == "__main__":
    test_path = os.path.join(os.path.dirname(__file__), '..', '..', '..', '..', 'test', 'test.sol')
    with open(test_path, 'r', encoding='utf-8') as f:
        code = f.read()
    cleaned = run_comment_removal(source_text=code)
    show_comparison(code, cleaned)