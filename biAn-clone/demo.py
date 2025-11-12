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
from static_data_obfuscator import transform_static_to_dynamic

# Optional: ensure an AST JSON exists for precise static->dynamic transformation
def _ensure_ast_json(sol_file: str, out_json: str, solc_version: str = "0.8.30") -> None:
    try:
        if os.path.exists(out_json):
            return
        # Lazy import to avoid hard dependency if user skips static transform
        from solcx import install_solc, set_solc_version, compile_standard
        install_solc(solc_version)
        set_solc_version(solc_version)
        with open(sol_file, "r", encoding="utf-8") as f:
            src = f.read()
        std_input = {
            "language": "Solidity",
            "sources": { sol_file: { "content": src } },
            "settings": { "outputSelection": { "*": { "*": [] }, "": ["ast"] } }
        }
        result = compile_standard(std_input, allow_paths=os.path.dirname(sol_file))
        ast_obj = result["sources"][sol_file]["ast"]
        os.makedirs(os.path.dirname(out_json), exist_ok=True)
        import json as _json
        with open(out_json, "w", encoding="utf-8") as out:
            _json.dump(ast_obj, out, ensure_ascii=False, indent=2)
        print(f"[INFO] Generated AST JSON at: {out_json}")
    except Exception as e:
        print(f"[WARN] Could not generate AST JSON automatically: {e}")

def run_demo(input_file: str, output_file: str):
    if not os.path.exists(input_file):
        print(f"[ERROR] Input file not found: {input_file}")
        return

    # Đọc code Solidity gốc
    with open(input_file, 'r', encoding='utf-8') as f:
        original_code = f.read()

    print("[INFO] Original Solidity code loaded.")
    print("-" * 80)
    try:
        print(original_code[:500], "...")
    except UnicodeEncodeError:
        print(original_code[:500].encode('ascii', errors='replace').decode('ascii'), "...") 

    # Static to dynamic - enabled by default, disable by setting BIAN_ENABLE_STATIC=0
    enable_static = os.getenv("BIAN_ENABLE_STATIC", "1") == "1"
    if enable_static:
        try:
            ast_path = os.path.join('test', 'test_ast.json')
            _ensure_ast_json(input_file, ast_path, solc_version="0.8.30")
            static_obfuscated = transform_static_to_dynamic(
                original_code,
                ast_path if os.path.exists(ast_path) else None
            )
            print("[OK] Static data obfuscation done.")
        except Exception as e:
            print(f"[WARN] Static data obfuscation failed: {e}")
            static_obfuscated = original_code
    else:
        static_obfuscated = original_code
        print("[INFO] Static data obfuscation skipped (set BIAN_ENABLE_STATIC=1 to enable).")

    # Boolean (skip if static-only mode requested)
    static_only = os.getenv("BIAN_STATIC_ONLY", "0") == "1"
    if static_only:
        boolean_code = static_obfuscated
        print("[INFO] Boolean obfuscation skipped (static-only mode).")
    else:
        try:
            boolean_code, ops = split_booleans_from_source(
                source_text=static_obfuscated,
                file_path_hint=None,
                solc_version="0.8.30"
            )
            print("[OK] Boolean obfuscation done.")
        except Exception as e:
            print(f"[WARN] Boolean obfuscation failed: {e}")
            boolean_code = static_obfuscated

    # Integer (skip if static-only mode requested)
    if static_only:
        integer_code = boolean_code
        print("[INFO] Integer obfuscation skipped (static-only mode).")
    else:
        try:
            integer_code = obfuscate_integers_preserve_pragma(boolean_code)
            print("[OK] Integer obfuscation done.")
        except Exception as e:
            print(f"[WARN] Integer obfuscation failed: {e}")
            integer_code = boolean_code

    if static_only:
        # Preserve original formatting: skip comment removal + layout passes
        comment_removed = integer_code
        renamed_code = integer_code
        print("[INFO] Static-only mode: skipped comment removal, formatting, renaming.")
    else:
        # Comment removal
        try:
            comment_removed = run_comment_removal(source_text=integer_code)
            print("[OK] Comment removal done.")
        except Exception as e:
            print(f"[WARN] Comment removal failed: {e}")
            comment_removed = integer_code

        # Format
        try:
            scrambled_code = scramble_format(
                source=integer_code,
                solidity_version="^0.8.30",
                remove_comments=True,
                one_line=True
            )
            print("[OK] Format scrambling done.")
        except Exception as e:
            print(f"[WARN] Format scrambling failed: {e}")
            scrambled_code = integer_code

        # Đổi tên biến
        try:
            renamer = VariableRenamer(
                hash_algorithm='sha1',
                prefix='OX',
                hash_length=24,
                solc_version='0.8.30'
            )
            renamed_code = renamer.obfuscate(scrambled_code, input_file)
            print("[OK] Variable renaming done.")
        except Exception as e:
            print(f"[WARN] Variable renaming failed: {e}")
            renamed_code = scrambled_code
    # Choose final output based on mode
    final_code = renamed_code if not static_only else renamed_code
    # Write to output file
    try:
        with open(output_file, 'w', encoding='utf-8') as out:
            out.write(final_code)
        print(f"[OK] Wrote obfuscated output to: {output_file}")
    except Exception as e:
        print(f"[ERROR] Failed to write output file: {e}")

    print("DEMO COMPLETED")
    print("=" * 80)

if __name__ == "__main__":
    input_path = 'test/test.sol'
    output_path = 'test/test_output.sol'
    run_demo(input_path, output_path)