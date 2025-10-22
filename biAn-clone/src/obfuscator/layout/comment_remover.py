#!/usr/bin/env python3
"""
BiAn Comment Remover - Smart Contract Comment Removal
Remove all comments from Solidity source code for distribution.
Based on: BiAn Smart Contract Source Code Obfuscation Paper
"""

import os
import re
import time
from typing import List, Dict, Tuple

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

def run_comment_removal()-> str:
    """Run comment removal on test contract"""
    
    # Get test file path
    current_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    test_file = os.path.join(current_dir, 'test', 'test.sol')
    
    if not os.path.exists(test_file):
        print(f"[ERROR] Test file not found: {test_file}")
        return
    
    try:
        with open(test_file, 'r', encoding='utf-8') as f:
            original_code = f.read()
        
        # Create remover
        remover = CommentRemover(original_code)
        
        # Perform removal
        start_time = time.time()
        removed_code, operations = remover.remove_comments()
        end_time = time.time()
        
        # Save result
        # output_file = os.path.join(current_dir, 'test', 'output_comment.sol')
        # with open(output_file, 'w', encoding='utf-8') as f:
        #     f.write(removed_code)
        
        return removed_code
    except Exception as e:
        print(f"[ERROR] {e}")
        import traceback
        traceback.print_exc()

def show_comparison():
    """Display before/after comparison"""
    try:
        # Read original file
        current_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        original_file = os.path.join(current_dir, 'test', 'test.sol')
        with open(original_file, 'r', encoding='utf-8') as f:
            original = f.read()
        
        # Read comment-removed file
        removed_file = os.path.join(current_dir, 'test', 'output_comment.sol')
        if os.path.exists(removed_file):
            with open(removed_file, 'r', encoding='utf-8') as f:
                obfuscated = f.read()
            # Compare comments
            original_comments = len(re.findall(r'//[^\n\r]*|/\*[\s\S]*?\*/|///[^\n\r]*', original))
            obfuscated_comments = len(re.findall(r'//[^\n\r]*|/\*[\s\S]*?\*/|///[^\n\r]*', obfuscated))
        else:
            print("[ERROR] Comment-removed file not found")
    except Exception as e:
        print(f"[ERROR] {e}")

if __name__ == "__main__":
    # Run comment removal
    run_comment_removal()
    
    # Show comparison
    show_comparison()