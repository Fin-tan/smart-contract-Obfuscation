"""
Opaque Predicate Inserter for BiAn-style Control Flow Obfuscation.
Injects 'always-true' conditions into 'if' and 'while' statements using a Chaotic Map (CPM).
"""

import re
import os
import sys
from typing import Tuple, List, Dict, Optional
from chaotic_map_generator import ChaoticMapGenerator

# Try imports similar to boolean_obfuscator.py
try:
    import solcx
    from solcx import install_solc, set_solc_version, compile_files, get_installed_solc_versions
except Exception:
    solcx = None

DEFAULT_SOLC_VERSION = "0.8.30"

class OpaquePredicateInserter:
    def __init__(self, solc_version=DEFAULT_SOLC_VERSION):
        self.cpm_gen = ChaoticMapGenerator()
        self.solc_version = solc_version

    def _ensure_solc(self) -> bool:
        if solcx is None:
            return False
        try:
            installed = get_installed_solc_versions()
            if self.solc_version in installed:
                set_solc_version(self.solc_version)
                return True
            install_solc(self.solc_version)
            set_solc_version(self.solc_version)
            return True
        except Exception:
            return False

    def _get_ast(self, file_path_param: str = None, source_code: str = None) -> Optional[dict]:
        """
        Get AST from file path or source code string using solcx.
        If source_code is provided, writes to a temp file first.
        """
        if solcx is None:
            return None
        
        self._ensure_solc()
        
        temp_path = None
        target_path = file_path_param

        try:
            if source_code:
                # Create a temp file to compile
                import tempfile
                with tempfile.NamedTemporaryFile(mode='w', suffix='.sol', delete=False, encoding='utf-8') as tmp:
                    tmp.write(source_code)
                    temp_path = tmp.name
                    target_path = temp_path
            
            if not target_path or not os.path.exists(target_path):
                return None

            result = compile_files([target_path], output_values=["ast"])
            
            # Find the AST for the target file
            for k, v in result.items():
                # k is usually the absolute path
                if source_code:
                     if temp_path in k:
                         return v.get("ast")
                else:
                    return v.get("ast")
            
            # Fallback if key match fails but only one result
            if len(result) == 1:
                return list(result.values())[0].get("ast")
                
            return None

        except Exception as e:
            print(f"[WARN] AST generation failed: {e}")
            return None
        finally:
            if temp_path and os.path.exists(temp_path):
                os.remove(temp_path)

    def _find_injection_points(self, ast_node: dict, points: List[Dict]):
        """
        Recursively find 'if' and 'while' statements in the AST.
        """
        if not isinstance(ast_node, dict):
            return

        node_type = ast_node.get("nodeType") or ast_node.get("name")

        if node_type == "IfStatement":
            # In old AST/new AST, structure might differ slightly, but usually has 'condition'
            condition = ast_node.get("condition")
            if condition:
                points.append({
                    "type": "IfStatement",
                    "src": condition.get("src")
                })
        
        elif node_type == "WhileStatement":
            condition = ast_node.get("condition")
            if condition:
                points.append({
                    "type": "WhileStatement",
                    "src": condition.get("src")
                })
        
        # Recurse
        for key, value in ast_node.items():
            if isinstance(value, list):
                for item in value:
                    self._find_injection_points(item, points)
            elif isinstance(value, dict):
                self._find_injection_points(value, points)

    def _parse_src_to_range(self, src_str: str) -> Optional[Tuple[int, int]]:
        try:
            parts = src_str.split(':')
            start = int(parts[0])
            length = int(parts[1])
            return start, start + length
        except:
            return None

    def insert_opaque_predicates(self, source_code: str, file_path_hint: str = None) -> str:
        """
        Injects Opaque Predicates into the source code.
        1. Parse AST to find If/While conditions.
        2. Inject '&& (calculateCPM(...) > 0)' into conditions.
        3. Inject verify state var and helper function at contract level.
        """
        
        # 1. Get AST
        ast = self._get_ast(file_path_param=file_path_hint, source_code=source_code)
        
        if not ast:
            print("[WARN] Could not generate AST for Opaque Predicates. Skipping injection.")
            return source_code

        # 2. Find points
        points = []
        self._find_injection_points(ast, points)
        
        if not points:
            print("[INFO] No suitable branching points found for Opaque Predicates.")
            return source_code

        # 3. Sort points by start index descending to modify safely
        parsed_points = []
        for p in points:
            src = p["src"]
            rng = self._parse_src_to_range(src)
            if rng:
                parsed_points.append({"range": rng, "type": p["type"]})
        
        parsed_points.sort(key=lambda x: x["range"][0], reverse=True)

        # 4. Perform replacements
        try:
            source_bytes = source_code.encode('utf-8')
        except:
            source_bytes = bytearray(source_code, 'utf-8')

        cpm_condition = self.cpm_gen.get_predicate_condition()
        
        inserted_count = 0
        new_bytes = bytearray(source_bytes)
        
        # Track which functions (byte ranges) we've touched to remove 'pure' later
        # But wait, simply doing a global replace of "pure" -> "view" in the whole file is risky?
        # Better: identify the function scope from AST and remove 'pure' locally.
        
        # Simpler approach: 
        # Since we use regex for function signature modification or just simple string replacement
        # Let's perform the condition replacement first.
        
        for p in parsed_points:
            start, end = p["range"]
            
            if start < 0 or end > len(source_bytes):
                continue
                
            original_cond_bytes = source_bytes[start:end]
            original_cond_str = original_cond_bytes.decode('utf-8')
            
            if self.cpm_gen.helper_func_name in original_cond_str:
                continue

            new_cond_str = f"({original_cond_str}) && {cpm_condition}"
            new_cond_bytes = new_cond_str.encode('utf-8')
            new_bytes[start:end] = new_cond_bytes
            inserted_count += 1

        source_code_mod = new_bytes.decode('utf-8')

        if inserted_count == 0:
            return source_code

        # 5. Handle 'pure' -> 'view'
        # BiAn paper mentions "remove obvious dependencies". 
        # Here we just strictly need to fix compilation.
        # Quick fix: replace " pure " with " view " or " " in functions that contain the CPM helper call?
        # Or just universally replace " pure " -> " view " in the contract? 
        # That's safe for compilation (view > pure).
        # We'll use regex to perform safe replacement of 'pure' keyword in function signatures.
        # Be careful not to replace strings or comments containing 'pure'.
        
        # Regex to find 'function ... (...) ... pure ...'
        # This is complex to match exactly only modified functions.
        # GLOBAL STRATEGY: Replace ' pure ' with ' view ' everywhere.
        # Pros: Guarantees no 'pure' error. Cons: Might change non-target functions. 
        # Acceptable for obfuscation context.
        
        source_code_mod = re.sub(r'\bpure\b', 'view', source_code_mod)

        # 6. Inject Helper Function and State Variable
        match = re.search(r'contract\s+\w+.*\{', source_code_mod)
        if match:
            insert_pos = match.end()
            components = f"\n{self.cpm_gen.get_state_variable_declaration()}\n{self.cpm_gen.get_helper_function_code()}\n"
            source_code_mod = source_code_mod[:insert_pos] + components + source_code_mod[insert_pos:]
            print(f"[INFO] Injected Opaque Predicates into {inserted_count} branches and added CPM components (converted pure->view).")
        else:
            print("[WARN] Could not find contract definition to insert CPM helper. Code might be broken.")
            
        return source_code_mod

