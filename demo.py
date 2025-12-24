#!/usr/bin/env python3
"""
BiAn Comment Remover Demo
Smart Contract Comment Obfuscation Demo
"""

import os
import sys
import re
import shutil
import glob


# Add the src directory to Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
src_base = os.path.join(current_dir, 'src')
layout_dir = os.path.join(src_base, 'obfuscator', 'layout')
dataflow_dir = os.path.join(src_base, 'obfuscator', 'data-flow')
controlflow_dir = os.path.join(src_base, 'obfuscator', 'control-flow')
for p in (layout_dir, dataflow_dir, controlflow_dir):
    if p not in sys.path:
        sys.path.insert(0, p)

# Import the comment remover
from comment_remover import CommentRemover, run_comment_removal, show_comparison
from format_scrambler import scramble_format
from variable_renamer import VariableRenamer
from boolean_obfuscator import split_booleans_from_source
from interger_obfuscator import obfuscate_integers_preserve_pragma
from static_data_obfuscator import transform_static_to_dynamic
from scalar_splitter import split_scalar_variables
from local_state_obfuscator import convert_locals_to_state
from opaque_predicate_obfuscator import OpaquePredicateInserter

# BiAn-style AST regeneration: create fresh AST from current source after each transformation

def _detect_solc_version(source_code: str) -> str:
    """
    Detects the solidity version from the source code pragma.
    Defaults to '0.8.30' if not found or complex range.
    """
    # Simple regex to find "pragma solidity ^0.8.0;" or "pragma solidity 0.8.30;"
    # We will try to extract the first semver-like string.
    # Supported formats:
    # pragma solidity 0.8.30;
    # pragma solidity ^0.8.30;
    # pragma solidity >=0.4.22 <0.9.0; -> We just pick the first one 0.4.22? No, that might be too old.
    # Let's look for the first concrete X.Y.Z
    
    match = re.search(r'pragma\s+solidity\s+([^;]+);', source_code)
    if match:
        version_str = match.group(1).strip()
        # Remove caret or other simple prefixes
        clean_ver = re.sub(r'[\^>=<]', '', version_str).split()[0] # Take first part if range
        
        # Validate if it looks like a version
        if re.match(r'^\d+\.\d+\.\d+$', clean_ver):
            print(f"[INFO] Detected Solidity version: {clean_ver}")
            return clean_ver
            
    print(f"[WARN] Could not auto-detect version from pragma. Defaulting to 0.8.30")
    return "0.8.30"


def _regenerate_ast_from_source(source_code: str, source_file_path: str, ast_output_path: str, solc_version: str) -> bool:

    """
    Regenerate AST from current source code (BiAn approach).
    Write source to temp file, compile to get fresh AST, save AST to output path.
    Returns True if successful, False otherwise.
    """
    try:
        # Lazy import to avoid hard dependency
        from solcx import install_solc, set_solc_version, compile_standard, compile_files, get_installed_solc_versions # Added compile_files, get_installed_solc_versions
        # Ensure specific version is installed
        try:
            install_solc(solc_version)
            set_solc_version(solc_version)
        except Exception as e:
            print(f"[WARN] Failed to install/set solc version {solc_version}: {e}")
        
        # Write current source to snapshot file for this step
        os.makedirs(os.path.dirname(source_file_path), exist_ok=True)
        with open(source_file_path, "w", encoding="utf-8") as f:
            f.write(source_code)
        
        # Compile source to get fresh AST
        std_input = {
            "language": "Solidity",
            "sources": { source_file_path: { "content": source_code } },
            "settings": { "outputSelection": { source_file_path: { "": ["ast"] } } }
        }
        result = compile_standard(std_input, allow_paths=os.path.dirname(source_file_path))
        ast_obj = result["sources"][source_file_path]["ast"]
        
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
def _ensure_initial_ast(sol_file: str, out_json: str, solc_version: str) -> None:
    with open(sol_file, "r", encoding="utf-8") as f:
        source = f.read()

    step0_path = os.path.join('test', 'test_step0.sol')
    if not _regenerate_ast_from_source(source, step0_path, out_json, solc_version):
        print("[WARN] Could not regenerate initial AST; proceeding with previous version if available.")

def run_demo(input_file: str, output_file: str):
    if not os.path.exists(input_file):
        print(f"[ERROR] Input file not found: {input_file}")
        return

    # Read original Solidity code
    with open(input_file, 'r', encoding='utf-8') as f:
        current_source = f.read()

    print("[INFO] Starting BiAn-style progressive obfuscation pipeline...")
    
    # Initialize AST
    # Detect version first
    with open(input_file, 'r', encoding='utf-8') as f:
        initial_source = f.read()
    
    detected_version = _detect_solc_version(initial_source)
    
    # Pre-install to avoid delays later
    try:
        from solcx import install_solc, set_solc_version
        install_solc(detected_version)
        set_solc_version(detected_version)
    except Exception as e:
        print(f"[ERROR] Failed to install/set solc version {detected_version}: {e}")
        return

    print(f"[INFO] Using Solidity Version: {detected_version}")

    # Generate initial AST
    current_ast_path = os.path.join('test', 'test_ast_step0.json')
    print(f"[INFO] Generating initial AST for {input_file}...")
    _ensure_initial_ast(input_file, current_ast_path, solc_version=detected_version)

    step_counter = 0
    static_only = os.getenv("BIAN_STATIC_ONLY", "0") == "1"

    # Helper function for progressive transformation
    def next_step(source_code: str, step_name: str):
        nonlocal step_counter, current_ast_path
        step_counter += 1
        
        # Create temp file for current source
        step_source_path = os.path.join('test', f'test_step{step_counter}.sol')
        new_ast_path = os.path.join('test', f'test_ast_step{step_counter}.json')
        
        # Regenerate AST from current source (BiAn approach)
        if _regenerate_ast_from_source(source_code, step_source_path, new_ast_path, solc_version=detected_version):
            print(f"[AST] Regenerated AST after {step_name} -> {new_ast_path}")
            current_ast_path = new_ast_path
        else:
            print(f"[WARN] AST regeneration failed for {step_name}, using previous AST")
        
        return current_ast_path

    
    
    # Step 0: Pre-processing (Modifier & Internal Function Inlining)
    enable_preprocessing = os.getenv("BIAN_ENABLE_PREPROCESSING", "1") == "1"
    if static_only:
        print("[INFO] Pre-processing skipped (static-only mode).")
    elif not enable_preprocessing:
        print("[INFO] Pre-processing disabled.")
    else:
        try:
            print("[INFO] Running Pre-processing (Inlining)...")
            from preprocessing_obfuscator import PreprocessingObfuscator
            preprocessor = PreprocessingObfuscator(solc_version=detected_version)
            
            # Apply Modifier & Function Inlining
            current_source, count = preprocessor.obfuscate(current_source, current_ast_path)
            current_ast_path = next_step(current_source, "preprocessing")
            print("[OK] Pre-processing done.")
        except Exception as e:
            print(f"[WARN] Pre-processing failed: {e}")
            import traceback
            traceback.print_exc()

    # Step 1: Opaque Predicates (Control Flow)
    enable_cpm = os.getenv("BIAN_ENABLE_CPM", "1") == "1"
    if static_only:
        print("[INFO] Opaque Predicates skipped (static-only mode).")
    elif not enable_cpm:
        print("[INFO] Opaque Predicates disabled (set BIAN_ENABLE_CPM=1 to enable).")
    else:
        try:
            inserter = OpaquePredicateInserter(solc_version=detected_version)
            cpm_code, count = inserter.obfuscate(current_source, current_ast_path)
            if count > 0:
                current_source = cpm_code
                current_ast_path = next_step(current_source, "opaque predicates")
                print("[OK] Opaque Predicates insertion done.")
            else:
                print("[INFO] Opaque Predicates skipped (no injection points).")
        except Exception as e:
            print(f"[WARN] Opaque Predicates insertion failed: {e}")

    # Step 2: Control Flow Flattening
    print(f"[INFO] Running Control Flow Flattening...")
    # enable_flattening = os.getenv("BIAN_ENABLE_FLATTENING", "1") == "1"
    if not static_only:
        try:
            from flattening_obfuscator import FlatteningObfuscator
            flattener = FlatteningObfuscator(solc_version=detected_version)
            flattened_code, count = flattener.obfuscate(current_source, current_ast_path)
            
            if count > 0:
                current_source = flattened_code
                current_ast_path = next_step(current_source, "control flow flattening")
                print("[OK] Control Flow Flattening done.")
            else:
                 print("[INFO] Control Flow Flattening skipped (no suitable functions).")
        except Exception as e:
            print(f"[WARN] Control Flow Flattening failed: {e}")
            import traceback
            traceback.print_exc()

    # Step 3: Local-to-state promotion
    enable_local_state = os.getenv("BIAN_ENABLE_LOCAL_STATE", "1") == "1"
    if enable_local_state:
        try:
            promoted_source, promoted_count = convert_locals_to_state(current_source, current_ast_path)
            if promoted_count > 0:
                current_source = promoted_source
                current_ast_path = next_step(current_source, "local-to-state promotion")
                print(f"[OK] Local-to-state promotion done ({promoted_count} variables).")
            else:
                print("[INFO] Local-to-state promotion skipped (no eligible locals).")
        except Exception as e:
            print(f"[WARN] Local→state promotion failed: {e}")
    else:
        print("[INFO] Local-to-state promotion disabled (set BIAN_ENABLE_LOCAL_STATE=1 to enable).")

    # Step 4: Static data obfuscation
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

    # Step 5: Boolean obfuscation
    if static_only:
        print("[INFO] Boolean obfuscation skipped (static-only mode).")
    else:
        try:
            boolean_obfuscated, ops = split_booleans_from_source(
                source_text=current_source,
                file_path_hint=None,
        # Scalar Splitter now uses AST from JSON, but might need AST regeneration logic in future
        # Currently scalar_splitter does not take Solc Version as init, but `split_scalar_variables` just takes AST path.
        # But wait, scalar splitter relies on existing AST. We already handle AST regen in `next_step` using `detect_version`.
        # So scalar splitter logic itself is fine as long as AST is valid.

            )
            current_source = boolean_obfuscated
            current_ast_path = next_step(current_source, "boolean obfuscation")
            print("[OK] Boolean obfuscation done.")
        except Exception as e:
            print(f"[WARN] Boolean obfuscation failed: {e}")

    # Step 6: Integer obfuscation
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

    # Step 7: Scalar variable splitting
    enable_scalar = os.getenv("BIAN_ENABLE_SCALAR", "1") == "1"
    if static_only:
        print("[INFO] Scalar splitting skipped (static-only mode).")
    elif not enable_scalar:
        print("[INFO] Scalar splitting disabled (set BIAN_ENABLE_SCALAR=1 to enable).")
    else:
        try:
            scalar_obfuscated, scalar_count = split_scalar_variables(current_source, current_ast_path)
            if scalar_count > 0:
                current_source = scalar_obfuscated
                current_ast_path = next_step(current_source, "scalar splitting")
                print(f"[OK] Scalar splitting done ({scalar_count} variables).")
            else:
                print("[INFO] Scalar splitting skipped (no eligible variables).")
        except Exception as e:
            print(f"[WARN] Scalar splitting failed: {e}")

    if static_only:
        # Preserve original formatting: skip comment removal + layout passes
        print("[INFO] Static-only mode: skipped comment removal, formatting, renaming.")
    else:
        # Step 8: Comment removal
        try:
            comment_removed = run_comment_removal(source_text=current_source)
            current_source = comment_removed
            current_ast_path = next_step(current_source, "comment removal")
            print("[OK] Comment removal done.")
        except Exception as e:
            print(f"[WARN] Comment removal failed: {e}")

        # Step 9: Format scrambling
        enable_formatting = os.getenv("BIAN_ENABLE_FORMATTING", "1") == "1"
        if enable_formatting and not static_only:
             # Pass detected version to formatter
             print(f"[INFO] Scrambling format...")
             from format_scrambler import scramble_format
             scrambled_code = scramble_format(
                current_source, 
                solidity_version=f"^{detected_version}", # Use caret for standard
                remove_comments=False, 
                one_line=True
            )
             current_source = scrambled_code
             current_ast_path = next_step(current_source, "format scrambling")
             print("[OK] Format scrambling done.")
        else:
            print("[INFO] Format scrambling disabled (set BIAN_ENABLE_FORMATTING=1 to enable).")

        # Step 10: Variable renaming (uses fresh AST)
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