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

# BiAn-style AST regeneration: create fresh AST from current source after each transformation
def _regenerate_ast_from_source(source_code: str, temp_file_path: str, ast_output_path: str, solc_version: str = "0.8.30") -> bool:
    """
    Regenerate AST from current source code (BiAn approach).
    Write source to temp file, compile to get fresh AST, save AST to output path.
    Returns True if successful, False otherwise.
    """
    try:
        # Lazy import to avoid hard dependency
        from solcx import install_solc, set_solc_version, compile_standard
        install_solc(solc_version)
        set_solc_version(solc_version)
        
        # Write current source to temporary file
        os.makedirs(os.path.dirname(temp_file_path), exist_ok=True)
        with open(temp_file_path, "w", encoding="utf-8") as f:
            f.write(source_code)
        
        # Compile source to get fresh AST
        std_input = {
            "language": "Solidity",
            "sources": { temp_file_path: { "content": source_code } },
            "settings": { "outputSelection": { temp_file_path: { "": ["ast"] } } }
        }
        result = compile_standard(std_input, allow_paths=os.path.dirname(temp_file_path))
        ast_obj = result["sources"][temp_file_path]["ast"]
        
        # Save fresh AST
        os.makedirs(os.path.dirname(ast_output_path), exist_ok=True)
        import json as _json
        with open(ast_output_path, "w", encoding="utf-8") as out:
            _json.dump(ast_obj, out, ensure_ascii=False, indent=2)
        
        return True
    except Exception as e:
        print(f"[WARN] Could not regenerate AST: {e}")
        return False

# Initial AST generation (for first step only)
def _ensure_initial_ast(sol_file: str, out_json: str, solc_version: str = "0.8.30") -> None:
    if os.path.exists(out_json):
        return
    
    with open(sol_file, "r", encoding="utf-8") as f:
        source = f.read()
    
    _regenerate_ast_from_source(source, sol_file, out_json, solc_version)

def run_demo(input_file: str, output_file: str):
    if not os.path.exists(input_file):
        print(f"[ERROR] Input file not found: {input_file}")
        return

    # Read original Solidity code
    with open(input_file, 'r', encoding='utf-8') as f:
        current_source = f.read()

    print("[INFO] Starting BiAn-style progressive obfuscation pipeline...")
    
    # Initialize AST for first step
    current_ast_path = os.path.join('test', 'test_ast_step0.json')
    _ensure_initial_ast(input_file, current_ast_path, solc_version="0.8.30")
    step_counter = 0

    # Helper function for progressive transformation
    def next_step(source_code: str, step_name: str):
        nonlocal step_counter, current_ast_path
        step_counter += 1
        
        # Create temp file for current source
        temp_source_path = os.path.join('test', f'temp_step{step_counter}.sol')
        new_ast_path = os.path.join('test', f'test_ast_step{step_counter}.json')
        
        # Regenerate AST from current source (BiAn approach)
        if _regenerate_ast_from_source(source_code, temp_source_path, new_ast_path):
            print(f"[AST] Regenerated AST after {step_name} -> {new_ast_path}")
            current_ast_path = new_ast_path
        else:
            print(f"[WARN] AST regeneration failed for {step_name}, using previous AST")
        
        return current_ast_path

    # Step 1: Static data obfuscation
    enable_static = os.getenv("BIAN_ENABLE_STATIC", "1") == "1"
    if enable_static:
        try:
            static_obfuscated = transform_static_to_dynamic(current_source, current_ast_path)
            current_source = static_obfuscated
            current_ast_path = next_step(current_source, "static data obfuscation")
            print("[OK] Static data obfuscation done.")
        except Exception as e:
            print(f"[WARN] Static data obfuscation failed: {e}")
    else:
        print("[INFO] Static data obfuscation skipped (set BIAN_ENABLE_STATIC=1 to enable).")

    # Step 2: Boolean obfuscation (skip if static-only mode requested)
    static_only = os.getenv("BIAN_STATIC_ONLY", "0") == "1"
    if static_only:
        print("[INFO] Boolean obfuscation skipped (static-only mode).")
    else:
        try:
            boolean_obfuscated, ops = split_booleans_from_source(
                source_text=current_source,
                file_path_hint=None,
                solc_version="0.8.30"
            )
            current_source = boolean_obfuscated
            current_ast_path = next_step(current_source, "boolean obfuscation")
            print("[OK] Boolean obfuscation done.")
        except Exception as e:
            print(f"[WARN] Boolean obfuscation failed: {e}")

    # Step 3: Integer obfuscation (skip if static-only mode requested)
    if static_only:
        print("[INFO] Integer obfuscation skipped (static-only mode).")
    else:
        try:
            integer_obfuscated = obfuscate_integers_preserve_pragma(current_source)
            current_source = integer_obfuscated
            current_ast_path = next_step(current_source, "integer obfuscation")
            print("[OK] Integer obfuscation done.")
        except Exception as e:
            print(f"[WARN] Integer obfuscation failed: {e}")

    if static_only:
        # Preserve original formatting: skip comment removal + layout passes
        print("[INFO] Static-only mode: skipped comment removal, formatting, renaming.")
    else:
        # Step 4: Comment removal
        try:
            comment_removed = run_comment_removal(source_text=current_source)
            current_source = comment_removed
            current_ast_path = next_step(current_source, "comment removal")
            print("[OK] Comment removal done.")
        except Exception as e:
            print(f"[WARN] Comment removal failed: {e}")

        # Step 5: Format scrambling
        try:
            scrambled_code = scramble_format(
                source=current_source,
                solidity_version="^0.8.30",
                remove_comments=True,
                one_line=True
            )
            current_source = scrambled_code
            current_ast_path = next_step(current_source, "format scrambling")
            print("[OK] Format scrambling done.")
        except Exception as e:
            print(f"[WARN] Format scrambling failed: {e}")

        # Step 6: Variable renaming (uses fresh AST)
        try:
            renamer = VariableRenamer(
                hash_algorithm='sha1',
                prefix='OX',
                hash_length=24,
                solc_version='0.8.30'
            )
            # Pass current source directly instead of file path
            renamed_code = renamer.obfuscate_from_source(current_source, current_ast_path)
            current_source = renamed_code
            current_ast_path = next_step(current_source, "variable renaming")
            print("[OK] Variable renaming done.")
        except Exception as e:
            print(f"[WARN] Variable renaming failed: {e}")
    # Write final obfuscated code to output file
    try:
        with open(output_file, 'w', encoding='utf-8') as out:
            out.write(current_source)
        print(f"[OK] Wrote obfuscated output to: {output_file}")
    except Exception as e:
        print(f"[ERROR] Failed to write output file: {e}")

    # Copy final AST to main test_ast.json for backward compatibility
    try:
        import shutil
        final_ast_path = os.path.join('test', 'test_ast.json')
        shutil.copy2(current_ast_path, final_ast_path)
        print(f"[AST] Final AST copied to: {final_ast_path}")
    except Exception as e:
        print(f"[WARN] Could not copy final AST: {e}")

    # Optional cleanup: remove temporary files
    cleanup_temps = os.getenv("BIAN_CLEANUP_TEMPS", "1") == "1"
    if cleanup_temps:
        try:
            import glob
            temp_files = glob.glob('test/temp_step*.sol')
            for f in temp_files:
                if os.path.exists(f):
                    os.remove(f)
            print(f"[OK] Cleaned up {len(temp_files)} temporary files")
        except Exception as e:
            print(f"[WARN] Cleanup failed: {e}")

    print(f"\n[OK] BiAn-style obfuscation completed! Final AST: {current_ast_path} -> test_ast.json")

if __name__ == "__main__":
    input_path = 'test/test.sol'
    output_path = 'test/test_output.sol'
    run_demo(input_path, output_path)