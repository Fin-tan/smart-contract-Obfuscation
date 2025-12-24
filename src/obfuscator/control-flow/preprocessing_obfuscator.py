"""
Pre-processing Obfuscator for BiAn-style Obfuscation.
Handles:
1. Modifier Inlining: "Unrolls" modifiers into function bodies.
2. Internal Function Inlining: Replaces internal function calls with their body logic.
"""

import re
import os
from typing import List, Dict, Optional, Tuple

try:
    from solcx import compile_files, install_solc, set_solc_version, get_installed_solc_versions
except ImportError:
    pass

DEFAULT_SOLC_VERSION = "0.8.30"

class PreprocessingObfuscator:
    def __init__(self, solc_version="0.8.30"):
        self.solc_version = solc_version
        self._ensure_solc()

    def _ensure_solc(self):
        try:
            installed = get_installed_solc_versions()
            if self.solc_version not in installed:
                install_solc(self.solc_version)
            set_solc_version(self.solc_version)
        except Exception as e:
            print(f"[WARN] solc setup failed: {e}")

    def _get_ast(self, source_code: str) -> Optional[dict]:
        import tempfile
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.sol', delete=False, encoding='utf-8', newline='\n') as tmp:
                tmp.write(source_code)
                temp_path = tmp.name
            
            result = compile_files([temp_path], output_values=["ast"])
            for k, v in result.items():
                if temp_path in k:
                    return v.get("ast")
            if len(result) == 1:
                return list(result.values())[0].get("ast")
            return None
        except Exception as e:
            print(f"[WARN] AST generation failed: {e}")
            return None
        finally:
            if 'temp_path' in locals() and os.path.exists(temp_path):
                os.remove(temp_path)

    def _parse_src(self, src: str) -> Tuple[int, int]:
        parts = src.split(':')
        start = int(parts[0])
        length = int(parts[1])
        return start, start + length

    def _extract_text(self, node: dict, source_bytes: bytes) -> str:
        src = node.get('src')
        if not src: return ""
        start, end = self._parse_src(src)
        return source_bytes[start:end].decode('utf-8')

    def obfuscate(self, source_code: str, ast_path: str = None) -> Tuple[str, int]:
        """
        Unified interface for demo.py
        Returns: (obfuscated_source, change_count)
        """
        # We don't track exact count of inlinings easily without refactoring, 
        # so we return 1 if changed, 0 otherwise for now.
        new_source = self.apply_preprocessing(source_code)
        count = 1 if new_source != source_code else 0
        return new_source, count

    def apply_preprocessing(self, source_code: str) -> str:
        """
        Applies both modifier inlining and function inlining.
        Does multiple passes if necessary or sequential.
        """
        # Pass 1: Modifier Inlining
        source_code = self.inline_modifiers(source_code)
        
        # Pass 2: Internal Function Inlining
        # We might need to regenerate AST between passes if structure changes significantly,
        # but for simple text replacements we might get away with one pass if non-overlapping.
        # However, modifier inlining changes function bodies, so internal calls inside modifiers
        # (or inside the main body) might shift positions.
        # SAFEST approach: Regenerate AST or use an offset tracker. 
        # For this demo, let's just re-parse AST inside each method for simplicity/robustness.
        
        source_code = self.inline_functions(source_code)
        
        return source_code

    def inline_modifiers(self, source_code: str) -> str:
        ast = self._get_ast(source_code)
        if not ast: return source_code
        
        source_bytes = source_code.encode('utf-8')
        modified_source = bytearray(source_bytes)
        
        # 1. Collect all ModifierDefinitions for lookup
        modifiers_db = {}
        self._collect_nodes(ast, 'ModifierDefinition', modifiers_db)
        
        # 2. Collect all FunctionDefinitions that have modifiers
        functions_to_process = []
        self._collect_functions_with_modifiers(ast, functions_to_process)
        
        # 3. Sort functions reverse by src to handle bottom-up replacement
        functions_to_process.sort(key=lambda x: self._parse_src(x['node']['src'])[0], reverse=True)
        
        for item in functions_to_process:
            func_node = item['node']
            func_src = self._parse_src(func_node['src'])
            func_body_node = func_node.get('body')
            
            if not func_body_node: continue 
            
            # Extract Original Body (excluding braces)
            body_start, body_end = self._parse_src(func_body_node['src'])
            # The body src includes braces { }. We want content inside.
            # Assuming standard formatting, but AST gives exact range.
            original_body_content = source_bytes[body_start+1 : body_end-1].decode('utf-8')
            
            current_body = original_body_content
            
            # Process modifiers in REVERSE order of application (e.g. mod1 mod2 -> mod2(body) -> mod1(result))
            # In AST, 'modifiers' list is [mod1, mod2].
            # Execution: mod1_pre -> mod2_pre -> body -> mod2_post -> mod1_post.
            # So we wrap with mod2, then mod1.
            
            func_modifiers = reversed(func_node.get('modifiers', []))
            
            modifiers_to_remove_from_sig = []
            
            for mod_invocation in func_modifiers:
                mod_name = mod_invocation['modifierName']['name']
                ref_id = mod_invocation['modifierName']['referencedDeclaration']
                
                mod_def = modifiers_db.get(ref_id)
                if not mod_def:
                    # Could be inherited or base constructor call? Skip if generic.
                    continue
                    
                # We found a local modifier definition
                modifiers_to_remove_from_sig.append(mod_invocation)
                
                # Extract modifier wrapper logic
                mod_body_node = mod_def.get('body')
                if not mod_body_node: continue
                
                # Find the `_;` placeholder statement
                placeholder = self._find_placeholder(mod_body_node)
                if not placeholder:
                    print(f"[WARN] Modifier {mod_name} has no '_;' placeholder. Skipping.")
                    continue
                    
                # Extract Pre and Post parts
                mod_body_start, mod_body_end = self._parse_src(mod_body_node['src'])
                placeholder_start, placeholder_end = self._parse_src(placeholder['src'])
                
                # Safety check
                if placeholder_start < mod_body_start or placeholder_end > mod_body_end:
                    continue
                    
                # Pre: from start+1 (skip {) to placeholder start
                pre_code = source_bytes[mod_body_start+1 : placeholder_start].decode('utf-8')
                # Post: from placeholder end to end-1 (skip })
                post_code = source_bytes[placeholder_end : mod_body_end-1].decode('utf-8')
                
                # Cleanup: If placeholder 'src' only covered '_', post_code might start with ';'.
                # We want to remove that stray semicolon because it's part of the placeholder statement syntax logic which is gone.
                if post_code.strip().startswith(';'):
                    # precise removal: find the first ';' and remove everything up to it?
                    # simpler: just strip leading whitespace, then check ';'
                    stripped = post_code.lstrip()
                    if stripped.startswith(';'):
                        # Calculate how much was stripped (whitespace) + 1 char
                        idx = post_code.find(';')
                        post_code = post_code[idx+1:]
                
                # TODO: Argument Substitution if modifier has parameters
                # MVP: Simple substitution if no args or simple args.
                # User example has no args. We will implement simple replace.
                
                # Combine: Pre + CurrentBody + Post
                # Clean up extracted parts to avoid excessive newlines
                pre_code_clean = pre_code.rstrip()
                post_code_clean = post_code.lstrip()
                if post_code_clean.startswith(';'): # Safety check for stray semicolon again
                     post_code_clean = post_code_clean[1:]
                
                # We construct the body carefully
                current_body = f"\n        // Inline Modifier: {mod_name}\n{pre_code_clean}\n{current_body}\n{post_code_clean}"
            
            # 4. Apply changes to Source
            
            # 4a. Update Body
            new_body_block = f"{{ {current_body} }}"
            
            modified_source[body_start:body_end] = new_body_block.encode('utf-8')
            
            # 4b. Remove Modifier from Signature
            modifiers_to_remove_from_sig.sort(key=lambda x: self._parse_src(x['src'])[0], reverse=True)
            
            for mod_inv in modifiers_to_remove_from_sig:
                m_start, m_end = self._parse_src(mod_inv['src'])
                
                # Try to remove ONE preceding space if present
                if m_start > 0 and modified_source[m_start-1] == 32: # space in ascii
                    m_start -= 1
                
                modified_source[m_start:m_end] = b""
                
        return modified_source.decode('utf-8')


    def _collect_nodes(self, node: dict, target_type: str, result_map: dict):
        if node.get('nodeType') == target_type:
            result_map[node['id']] = node
        
        for key, value in node.items():
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        self._collect_nodes(item, target_type, result_map)
            elif isinstance(value, dict):
                self._collect_nodes(value, target_type, result_map)

    def _collect_functions_with_modifiers(self, node: dict, results: list):
        if node.get('nodeType') == 'FunctionDefinition':
            if node.get('modifiers'): # If has modifiers
                 results.append({'node': node})
        
        for key, value in node.items():
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        self._collect_functions_with_modifiers(item, results)
            elif isinstance(value, dict):
                self._collect_functions_with_modifiers(value, results)
                
    def _find_placeholder(self, block_node: dict) -> Optional[dict]:
        # BFS/DFS to find PlaceholderStatement ('_')
        statements = block_node.get('statements', [])
        for stmt in statements:
            if stmt.get('nodeType') == 'PlaceholderStatement':
                return stmt
        return None


    def inline_functions(self, source_code: str) -> str:
        ast = self._get_ast(source_code)
        if not ast: return source_code
        
        source_bytes = source_code.encode('utf-8')
        modified_source = bytearray(source_bytes)
        
        # 1. Collect Internal Functions (Definitions)
        # MVP: Only inline 'pure/view' functions with a single 'return' statement.
        internal_funcs = {}
        self._collect_nodes(ast, 'FunctionDefinition', internal_funcs)
        
        target_funcs = {}
        for fid, func in internal_funcs.items():
            if func.get('visibility') == 'internal' and func.get('stateMutability') in ['pure', 'view']:
                # Check body: single return statement?
                body = func.get('body')
                if body and body.get('nodeType') == 'Block':
                    stmts = body.get('statements', [])
                    if len(stmts) == 1 and stmts[0].get('nodeType') == 'Return':
                         target_funcs[fid] = func
                         
        # 2. Find Call Sites
        call_sites = []
        self._collect_call_sites(ast, call_sites, target_funcs)
        
        # 3. Sort reverse by location
        call_sites.sort(key=lambda x: self._parse_src(x['node']['src'])[0], reverse=True)
        
        for site in call_sites:
            call_node = site['node']
            target_id = site['target_id']
            target_func = target_funcs[target_id]
            
            # Prepare substitution map: Param Name -> Argument Text
            # Need parameter names from definition
            params = target_func['parameters']['parameters']
            args = call_node['arguments']
            
            if len(params) != len(args):
                # Variadic? Mismatch? Skip.
                continue
                
            param_map = {}
            for i, param in enumerate(params):
                p_name = param['name']
                # Extract argument text
                arg_text = self._extract_text(args[i], source_bytes)
                
                # Check if arg_text is simple (Identifier or Literal Number)
                # Regex for simple var or number: ^[\w]+$ (alphanumeric + underscore)
                # Or check nodeType of arg? AST is safer.
                arg_node = args[i]
                is_simple = False
                if arg_node.get('nodeType') in ['Identifier', 'Literal']:
                     is_simple = True
                
                if is_simple:
                    param_map[p_name] = arg_text
                else:
                    # MVP: Always wrap complex exprs in parens for safety: (arg)
                    param_map[p_name] = f"({arg_text})"
                
            # Extract Body Expression
            # body statements[0] is Return. return expressions/expression.
            ret_stmt = target_func['body']['statements'][0]
            ret_expr = ret_stmt.get('expression')
            
            if not ret_expr: continue
            
            # We need to replace identifiers in ret_expr matching params.
            # But we can't just text replace on the string, we need locations within the expression.
            # Ideally we parse the expression's AST (which we have!)
            
            # Get expression text range
            expr_start, expr_end = self._parse_src(ret_expr['src'])
            expr_text = source_bytes[expr_start:expr_end].decode('utf-8')
            
            # Find all Identifiers in the return expression that refer to params
            identifiers = []
            self._collect_identifiers(ret_expr, identifiers)
            
            # Filter identifiers that are strictly parameters (scoped to function)
            # Actually, just matching name might be risky if shadowed, 
            # but for MVP of "calcBonus(x) return x*2", name match is usually OK.
            # AST provides 'referencedDeclaration'. We can check if it matches param ID.
            
            param_ids = {p['id']: p['name'] for p in params}
            
            replacements = [] # (start, end, new_text) relative to expression start
            
            for ident in identifiers:
                ref_id = ident.get('referencedDeclaration')
                if ref_id in param_ids:
                    # It's a parameter usage
                    # Calculate relative offset
                    id_start, id_end = self._parse_src(ident['src'])
                    rel_start = id_start - expr_start
                    rel_end = id_end - expr_start
                    
                    p_name = param_ids[ref_id]
                    new_val = param_map[p_name]
                    
                    replacements.append((rel_start, rel_end, new_val))
                    
            # Apply replacements to expression text (reverse order)
            replacements.sort(key=lambda x: x[0], reverse=True)
            
            # If complex expression, we should convert expr_text to bytearray or list
            # Or just slice strings.
            inlined_expr = expr_text
            for start, end, new_val in replacements:
                inlined_expr = inlined_expr[:start] + new_val + inlined_expr[end:]
                
            # Now replace the Call Site with inlined_expr
            call_start, call_end = self._parse_src(call_node['src'])
            
            # Update source (in place)
            modified_source[call_start:call_end] = inlined_expr.encode('utf-8')
            
        return modified_source.decode('utf-8')

    def _collect_call_sites(self, node: dict, results: list, target_funcs: dict):
        if node.get('nodeType') == 'FunctionCall':
            # Check expression -> referencedDeclaration
            expr = node.get('expression')
            if expr:
                ref_id = expr.get('referencedDeclaration')
                if ref_id in target_funcs:
                     results.append({'node': node, 'target_id': ref_id})
                     
        for key, value in node.items():
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        self._collect_call_sites(item, results, target_funcs)
            elif isinstance(value, dict):
                self._collect_call_sites(value, results, target_funcs)

    def _collect_identifiers(self, node: dict, results: list):
        if node.get('nodeType') == 'Identifier':
            results.append(node)
            
        for key, value in node.items():
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        self._collect_identifiers(item, results)
            elif isinstance(value, dict):
                self._collect_identifiers(value, results)
