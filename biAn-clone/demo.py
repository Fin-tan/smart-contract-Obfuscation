#!/usr/bin/env python3
"""
BiAn Comment Remover Demo
Smart Contract Comment Obfuscation Demo
"""

import os
import sys

# Add the src directory to Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.join(current_dir, 'src', 'obfuscator', 'layout')
sys.path.append(src_dir)

# Import the comment remover
from comment_remover import CommentRemover, run_comment_removal, show_comparison
from format_scrambler import scramble_format
from variable_renamer import VariableRenamer
def run_demo(input_file: str, output_file: str):
    if not os.path.exists(input_file):
        print(f"[ERROR] Input file not found: {input_file}")
        return

    # Đọc code Solidity gốc
    with open(input_file, 'r', encoding='utf-8') as f:
        original_code = f.read()

    print("[INFO] Original Solidity code loaded.")
    print("-" * 80)
    print(original_code[:500], "...") 
    remove=run_comment_removal()
    print("da remove:",remove)
    # Loại comment và format
    scrambled_code = scramble_format(
        source=remove,
        solidity_version="^0.8.30",
        remove_comments=True,   
        one_line=True           
    )
    print("da format",scramble_format)
    # Đổi tên biến
    renamer = VariableRenamer(hash_algorithm='sha1', prefix='OX', hash_length=24, solc_version='0.8.30')
    obfuscated=renamer.obfuscate(scrambled_code,input_file)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(obfuscated)

    print("\n[INFO] Scrambled Solidity code written to:", output_file)
    print("-" * 80)
    print(obfuscated[:500], "...") 

if __name__ == "__main__":
    # Run the complete demo
  
    
    print("\n" + "=" * 80)
    print("DEMO COMPLETED")
    print("=" * 80)
    input_path = 'test/test.sol'
    output_path = 'test/test_output.sol'
    run_demo(input_path, output_path)