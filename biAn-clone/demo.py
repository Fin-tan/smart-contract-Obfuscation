#!/usr/bin/env python3
"""
BiAn Comment Remover Demo
Smart Contract Comment Obfuscation Demo
"""

import os
import sys


# Add the src directory to Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
src_base = os.path.join(current_dir, 'src')
layout_dir = os.path.join(src_base, 'obfuscator', 'layout')
dataflow_dir = os.path.join(src_base, 'obfuscator', 'data-flow')
for p in (layout_dir, dataflow_dir):
    if p not in sys.path:
        sys.path.insert(0, p)

# Import the comment remover
from comment_remover import CommentRemover, run_comment_removal, show_comparison
from format_scrambler import scramble_format
from variable_renamer import VariableRenamer
from boolean_obfuscator import split_booleans_from_source
from interger_obfuscator import obfuscate_integers_preserve_pragma

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
    remove = run_comment_removal()
    print("da remove:", remove)
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
    renamed_code=renamer.obfuscate(scrambled_code,input_file)
    
    # Boolean
    try:
        boolean_code, ops = split_booleans_from_source(
            source_text=renamed_code,
            file_path_hint=None,          # không dùng AST từ file
            solc_version="0.8.30"
        )
        print(f"[INFO] Boolean obfuscation applied (in-memory). Replacements: {len(ops)}")
    except Exception as e:
        print(f"[WARN] Boolean obfuscation failed: {e}")
        boolean_code = renamed_code

    # === 6️⃣ Write final output ===
    with open(output_file, 'w', encoding='utf-8', newline='\n') as f:
        f.write(boolean_code)

    print("\n[INFO] ✅ Final obfuscated Solidity code written to:", output_file)
    print("-" * 80)
    interger_ob=obfuscate_integers_preserve_pragma(boolean_code)
    print(interger_ob)
    print(interger_ob[:500], "...\n") 
    with open(output_file, 'w', encoding='utf-8', newline='\n') as f:
        f.write(interger_ob)
if __name__ == "__main__":
    # Run the complete demo
  
    
    print("\n" + "=" * 80)
    print("DEMO COMPLETED")
    print("=" * 80)
    input_path = 'test/test.sol'
    output_path = 'test/test_output.sol'
    run_demo(input_path, output_path)