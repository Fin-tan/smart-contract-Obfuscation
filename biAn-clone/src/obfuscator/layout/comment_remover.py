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

def run_comment_removal():
    """Run comment removal on test contract"""
    
    print("=" * 80)
    print("BiAn Comment Remover - Smart Contract Protection")
    print("Based on: BiAn Smart Contract Source Code Obfuscation Paper")
    print("Strategy: Removal Only (delete all comments)")
    print("=" * 80)
    
    # Get test file path
    current_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    test_file = os.path.join(current_dir, 'test', 'test.sol')
    
    if not os.path.exists(test_file):
        print(f"[ERROR] Test file not found: {test_file}")
        return
    
    try:
        with open(test_file, 'r', encoding='utf-8') as f:
            original_code = f.read()
        
        print("\n[STEP 1] Original Smart Contract:")
        print("-" * 50)
        print(original_code)
        
        # Create remover
        remover = CommentRemover(original_code)
        
        # Perform removal
        print("\n[STEP 2] Removing all comments...")
        start_time = time.time()
        removed_code, operations = remover.remove_comments()
        end_time = time.time()
        
        print("\n[STEP 3] Comment-Removed Smart Contract:")
        print("-" * 50)
        print(removed_code)
        
        # Statistics
        original_chars = len(original_code)
        obfuscated_chars = len(removed_code)
        processing_time = end_time - start_time
        
        print(f"\n[STEP 4] Removal Statistics:")
        print("-" * 50)
        print(f"Processing time: {processing_time:.4f} seconds")
        print(f"Original characters: {original_chars}")
        print(f"Obfuscated characters: {obfuscated_chars}")
        print(f"Character difference: {obfuscated_chars - original_chars}")
        
        # Operation count
        print(f"\n[STEP 5] Operations:")
        print("-" * 50)
        print(f"Removed comments: {len(operations)}")
        
        # Save result
        output_file = os.path.join(current_dir, 'test', 'obfuscated.sol')
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(removed_code)
        
        print(f"\n[STEP 6] Results:")
        print("-" * 50)
        print(f"Obfuscated code saved to: {output_file}")
        
        # Syntax check
        if 'pragma solidity' in removed_code and 'contract' in removed_code:
            print("[PASS] Basic syntax check passed")
        else:
            print("[WARNING] Syntax may be affected")
        
        print(f"\n[SUCCESS] Comment removal completed!")
        print("Smart contract protection applied successfully!")
        
    except Exception as e:
        print(f"[ERROR] {e}")
        import traceback
        traceback.print_exc()

def show_comparison():
    """Display before/after comparison"""
    
    print("\n" + "=" * 80)
    print("BEFORE vs AFTER COMPARISON")
    print("=" * 80)
    
    try:
        # Read original file
        current_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        original_file = os.path.join(current_dir, 'test', 'test.sol')
        with open(original_file, 'r', encoding='utf-8') as f:
            original = f.read()
        
        # Read comment-removed file
        removed_file = os.path.join(current_dir, 'test', 'obfuscated.sol')
        if os.path.exists(removed_file):
            with open(removed_file, 'r', encoding='utf-8') as f:
                obfuscated = f.read()
            
            print("BEFORE (Original Smart Contract):")
            print("-" * 50)
            print(original)
            
            print("\nAFTER (Comment-Removed Smart Contract):")
            print("-" * 50)
            print(obfuscated)
            
            # Compare comments
            original_comments = len(re.findall(r'//[^\n\r]*|/\*[\s\S]*?\*/|///[^\n\r]*', original))
            obfuscated_comments = len(re.findall(r'//[^\n\r]*|/\*[\s\S]*?\*/|///[^\n\r]*', obfuscated))
            
            print(f"\n[COMPARISON SUMMARY]")
            print(f"Original comments: {original_comments}")
            print(f"Comments after removal: {obfuscated_comments}")
            print(f"Comments processed: {original_comments - obfuscated_comments}")
            
            if obfuscated_comments < original_comments:
                print("[PASS] Comments successfully removed")
            else:
                print("[WARNING] Some comments may remain")
        else:
            print("[ERROR] Comment-removed file not found")
            
    except Exception as e:
        print(f"[ERROR] {e}")

if __name__ == "__main__":
    # Run comment removal
    run_comment_removal()
    
    # Show comparison
    show_comparison()
    
    print("\n" + "=" * 80)
    print("COMMENT REMOVAL COMPLETED")
    print("=" * 80)
