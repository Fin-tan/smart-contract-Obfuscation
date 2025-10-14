#!/usr/bin/env python3
"""
BiAn Comment Remover - Smart Contract Comment Obfuscation
Implementation of comment obfuscation techniques for smart contract protection
Based on: BiAn Smart Contract Source Code Obfuscation Paper
"""

import os
import sys
import random
import re
import time
from typing import List, Dict, Tuple

class CommentObfuscator:
    """Smart Contract Comment Obfuscator with mixed strategy"""
    
    def __init__(self, source: str):
        self.src = source
        
        # Dummy code templates for replacement
        self.dummy_templates = [
            'uint256 dummy_{} = 0x{};',
            'bool flag_{} = true;',
            'bytes32 hash_{} = keccak256("{}");',
            'address addr_{} = address(uint160(0x{}));'
        ]
        
        # Misleading comment templates
        self.misleading_comments = [
            '// WARNING: This function will delete all data',
            '// CRITICAL: This causes integer overflow', 
            '// DANGER: This function is deprecated',
            '// SECURITY: This function has vulnerabilities',
            '// BUG: This function contains critical bugs'
        ]
        
        # Obfuscated comment patterns
        self.obfuscated_patterns = [
            '// {}_obfuscated',
            '// 0x{}',
            '// {}_secure',
            '// {}_encrypted'
        ]

    def generate_dummy_code(self) -> str:
        """Generate dummy code to replace comments"""
        dummy_id = random.randint(1000, 9999)
        hex_value = hex(random.randint(0x10000000, 0xFFFFFFFF))[2:]
        random_string = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz', k=6))
        
        template = random.choice(self.dummy_templates)
        return template.format(dummy_id, hex_value, random_string)

    def generate_misleading_comment(self) -> str:
        """Generate misleading comment to replace original"""
        return random.choice(self.misleading_comments)

    def generate_obfuscated_comment(self) -> str:
        """Generate obfuscated comment content"""
        random_text = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=10))
        hex_value = hex(random.randint(0x10000000, 0xFFFFFFFF))[2:]
        
        pattern = random.choice(self.obfuscated_patterns)
        return pattern.format(random_text, hex_value)

    def obfuscate_comments(self) -> Tuple[str, List[Dict]]:
        """Main obfuscation method with mixed strategy"""
        result = self.src
        operations = []
        
        # Comment patterns to detect
        comment_patterns = [
            (r'//[^\n\r]*', 'single_line'),
            (r'/\*[\s\S]*?\*/', 'multi_line'),
            (r'///[^\n\r]*', 'natspec')
        ]
        
        for pattern, comment_type in comment_patterns:
            for match in re.finditer(pattern, result):
                start, end = match.start(), match.end()
                comment_text = match.group()
                
                # Skip if inside string literal
                if self._is_inside_string(start, result):
                    continue
                
                # Random strategy selection
                strategy = random.choice(['dummy_code', 'misleading', 'obfuscated', 'remove'])
                
                if strategy == 'dummy_code':
                    replacement = self.generate_dummy_code()
                elif strategy == 'misleading':
                    replacement = self.generate_misleading_comment()
                elif strategy == 'obfuscated':
                    replacement = self.generate_obfuscated_comment()
                else:  # remove
                    replacement = ''
                
                operations.append({
                    'start': start,
                    'end': end,
                    'replacement': replacement,
                    'strategy': strategy,
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

def run_comment_obfuscation():
    """Run comment obfuscation on test contract"""
    
    print("=" * 80)
    print("BiAn Comment Obfuscator - Smart Contract Protection")
    print("Based on: BiAn Smart Contract Source Code Obfuscation Paper")
    print("Mixed Strategy: Dummy Code + Misleading + Obfuscation + Removal")
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
        
        # Create obfuscator
        obfuscator = CommentObfuscator(original_code)
        
        # Perform obfuscation
        print("\n[STEP 2] Applying Mixed Strategy Obfuscation...")
        start_time = time.time()
        obfuscated_code, operations = obfuscator.obfuscate_comments()
        end_time = time.time()
        
        print("\n[STEP 3] Obfuscated Smart Contract:")
        print("-" * 50)
        print(obfuscated_code)
        
        # Statistics
        original_chars = len(original_code)
        obfuscated_chars = len(obfuscated_code)
        processing_time = end_time - start_time
        
        print(f"\n[STEP 4] Obfuscation Statistics:")
        print("-" * 50)
        print(f"Processing time: {processing_time:.4f} seconds")
        print(f"Original characters: {original_chars}")
        print(f"Obfuscated characters: {obfuscated_chars}")
        print(f"Character difference: {obfuscated_chars - original_chars}")
        
        # Strategy statistics
        strategy_counts = {}
        for op in operations:
            strategy = op['strategy']
            strategy_counts[strategy] = strategy_counts.get(strategy, 0) + 1
        
        print(f"\n[STEP 5] Strategy Usage:")
        print("-" * 50)
        for strategy, count in strategy_counts.items():
            print(f"  {strategy}: {count} operations")
        
        # Save result
        output_file = os.path.join(current_dir, 'test', 'obfuscated.sol')
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(obfuscated_code)
        
        print(f"\n[STEP 6] Results:")
        print("-" * 50)
        print(f"Obfuscated code saved to: {output_file}")
        
        # Syntax check
        if 'pragma solidity' in obfuscated_code and 'contract' in obfuscated_code:
            print("[PASS] Basic syntax check passed")
        else:
            print("[WARNING] Syntax may be affected")
        
        print(f"\n[SUCCESS] Comment obfuscation completed!")
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
        
        # Read obfuscated file
        obfuscated_file = os.path.join(current_dir, 'test', 'obfuscated.sol')
        if os.path.exists(obfuscated_file):
            with open(obfuscated_file, 'r', encoding='utf-8') as f:
                obfuscated = f.read()
            
            print("BEFORE (Original Smart Contract):")
            print("-" * 50)
            print(original)
            
            print("\nAFTER (Obfuscated Smart Contract):")
            print("-" * 50)
            print(obfuscated)
            
            # Compare comments
            original_comments = len(re.findall(r'//[^\n\r]*|/\*[\s\S]*?\*/|///[^\n\r]*', original))
            obfuscated_comments = len(re.findall(r'//[^\n\r]*|/\*[\s\S]*?\*/|///[^\n\r]*', obfuscated))
            
            print(f"\n[COMPARISON SUMMARY]")
            print(f"Original comments: {original_comments}")
            print(f"Obfuscated comments: {obfuscated_comments}")
            print(f"Comments processed: {original_comments - obfuscated_comments}")
            
            if obfuscated_comments < original_comments:
                print("[PASS] Comments successfully obfuscated")
            else:
                print("[WARNING] Some comments may remain")
        else:
            print("[ERROR] Obfuscated file not found")
            
    except Exception as e:
        print(f"[ERROR] {e}")

if __name__ == "__main__":
    # Run comment obfuscation
    run_comment_obfuscation()
    
    # Show comparison
    show_comparison()
    
    print("\n" + "=" * 80)
    print("COMMENT OBFUSCATION COMPLETED")
    print("=" * 80)
