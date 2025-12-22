"""
Control Flow Flattening Obfuscator for BiAn-style Obfuscation.
Flattens the control flow graph by splitting basic blocks and wrapping them in a dispatcher.
"""

import re
import os
import random
from typing import List, Dict, Optional, Tuple

try:
    from solcx import compile_files, install_solc, set_solc_version, get_installed_solc_versions
except ImportError:
    pass

class FlatteningObfuscator:
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

    def flatten_control_flow(self, source_code: str) -> str:
        ast = self._get_ast(source_code)
        if not ast:
            return source_code

        # Encode source for byte-level extraction
        source_bytes = source_code.encode('utf-8')
        
        # We need to identify FunctionDefinitions that have a body
        functions_to_flatten = []
        self._find_functions(ast, functions_to_flatten)
        
        # Sort functions reverse by location to modify bottom-up
        functions_to_flatten.sort(key=lambda x: x['range'][0], reverse=True)
        
        modified_source = bytearray(source_bytes)
        
        count = 0
        for func in functions_to_flatten:
            # We only flatten functions that have significant logic (e.g., IfStatement, Loops)
            # For simplicity in this demo, we flatten ANY function that has a block body > 1 statement
            # OR contains control flow.
            
            body_node = func['body']
            statements = body_node.get('statements', [])
            
            if not statements:
                continue
                
            # Check complexity: do we need flattening?
            # If it's just linear variable decls, maybe skip?
            # User wants to see the structure change. Let's flatten if > 2 statements or has branching.
            if len(statements) < 2 and not self._has_branching(body_node):
                continue
                
            # Extract original body content (excluding braces ideally, or we replace the whole block)
            body_range = self._parse_src(body_node['src'])
            # body_range includes { } usually for a Block
            
            # 1. Split into Basic Blocks
            blocks, hoisted_vars = self._create_basic_blocks(statements, source_bytes)
            
            # 2. Create Dispatcher Code
            flattened_body = self._generate_dispatcher(blocks, hoisted_vars)
            
            # 3. Replace in source
            # We replace everything inside the function braces.
            # The body_range usually covers `{ ... }`.
            # We need to preserve the braces or re-add them.
            
            # AST 'Block' src includes braces.
            new_block_bytes = flattened_body.encode('utf-8')
            
            start, end = body_range
            modified_source[start:end] = new_block_bytes
            count += 1
            
        print(f"[INFO] Flattened control flow for {count} functions.")
        return modified_source.decode('utf-8')

    def _find_functions(self, node: dict, results: list):
        if node.get('nodeType') == 'FunctionDefinition':
            if node.get('implemented') and node.get('body'):
                src = node['body'].get('src')
                if src:
                    rng = self._parse_src(src)
                    results.append({'node': node, 'body': node['body'], 'range': rng})
        
        # Recurse
        for key, value in node.items():
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        self._find_functions(item, results)
            elif isinstance(value, dict):
                self._find_functions(value, results)

    def _has_branching(self, node: dict) -> bool:
        # Simple recursive check for If/While/For
        t = node.get('nodeType', '')
        if t in ['IfStatement', 'WhileStatement', 'ForStatement', 'DoWhileStatement']:
            return True
        for key, value in node.items():
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict) and self._has_branching(item):
                        return True
            elif isinstance(value, dict) and self._has_branching(value):
                return True
        return False

    def _extract_text(self, node: dict, source_bytes: bytes) -> str:
        src = node.get('src')
        if not src: return ""
        start, end = self._parse_src(src)
        return source_bytes[start:end].decode('utf-8')

    def _get_default_value_for_type(self, type_str: str) -> str:
        t = type_str.strip()
        if t.startswith('bool'): return 'false'
        if t.startswith('string'): return '""'
        if t.startswith('bytes'): return '""'
        if t.startswith('address'): return 'address(0)'
        # For ints/uints or anything else, default to 0
        return '0'

    def _create_basic_blocks(self, statements: list, source_bytes: bytes) -> Tuple[List[Dict], List[str]]:
        """
        Splits a list of AST statements into a CFG-like structure.
        Returns: (blocks, hoisted_vars)
        """
        blocks = []
        hoisted_vars = []
        current_id = 1
        
        # Naively: 1 statement = 1 block? Too granular.
        # Better: Group linear statements. Split at branching.
        
        current_block_content = []
        
        for stmt in statements:
            stmt_type = stmt.get('nodeType')
            
            if stmt_type == 'IfStatement':
                # End current linear block if exists
                if current_block_content:
                    blocks.append({
                        'id': current_id,
                        'content': "\n".join(current_block_content),
                        'next': current_id + 1
                    })
                    current_id += 1
                    current_block_content = []
                
                # Handle IF as a separate block structure
                condition_text = self._extract_text(stmt['condition'], source_bytes)
                
                true_body = stmt.get('trueBody', {})
                true_text = self._extract_text(true_body, source_bytes)
                if true_body.get('nodeType') == 'Block':
                    true_text = true_text.strip()[1:-1]
                
                false_body = stmt.get('falseBody')
                false_text = ""
                if false_body:
                    false_text = self._extract_text(false_body, source_bytes)
                    if false_body.get('nodeType') == 'Block':
                        false_text = false_text.strip()[1:-1]
                
                next_block_id_after_if = current_id + 3 if false_body else current_id + 2
                true_block_id = current_id + 1
                false_block_id = current_id + 2 if false_body else next_block_id_after_if
                
                # Branching Block - Use Block Style
                # if (cond) {
                #     state = true_id;
                # } else {
                #     state = false_id;
                # }
                # Use standard 4-space indentation which textwrap.dedent will handle nicely
                content = f"if ({condition_text}) {{\n"
                content += f"    state = {true_block_id};\n"
                content += f"}} else {{\n"
                content += f"    state = {false_block_id};\n"
                content += f"}}"
                
                blocks.append({
                    'id': current_id,
                    'content': content,
                    'next': None
                })
                
                
                # True Block
                blocks.append({
                    'id': true_block_id,
                    'content': true_text.strip() if true_text.strip() else "// empty true block",
                    'next': next_block_id_after_if
                })
                
                # False Block
                if false_body:
                    blocks.append({
                        'id': false_block_id,
                        'content': false_text.strip() if false_text.strip() else "// empty false block",
                        'next': next_block_id_after_if
                    })
                
                current_id = next_block_id_after_if

            elif stmt_type == 'VariableDeclarationStatement':
                # Hoist variable declarations
                # "uint x = 1;" -> "x = 1;" (and "uint x;" moved to top)
                
                decls = stmt.get('declarations', [])
                init_val = stmt.get('initialValue')
                
                assignment_parts = []
                
                for i, decl in enumerate(decls):
                    if not decl: continue # tuple gap
                    
                    var_name = decl.get('name')
                    type_name_node = decl.get('typeName')
                    type_text = self._extract_text(type_name_node, source_bytes)
                    
                    # Store for hoisting with proper indentation
                    hoisted_vars.append(f"        {type_text} {var_name};")
                    
                    # Build assignment LHS
                
                # If there is an initial value, we need to keep the assignment
                if init_val:
                    # To handle tuple assignment correctly: (a, b) = (1, 2)
                    full_text = self._extract_text(stmt, source_bytes)
                    full_text = full_text.strip()
                    if full_text.endswith(';'): full_text = full_text[:-1]
                    
                    lhs = ""
                    if len(decls) == 1:
                        lhs = decls[0]['name']
                    else:
                        names = [d['name'] if d else '' for d in decls]
                        lhs = f"({','.join(names)})"
                        
                    rhs_text = self._extract_text(init_val, source_bytes)
                    current_block_content.append(f"{lhs} = {rhs_text};")
                else:
                    # No init value (e.g., "uint a;").
                    # Crucial: Since we hoist declarations to the top, we extend their scope.
                    # To preserve semantics (especially inside loops), we MUST reset them 
                    # to their default values in place!
                    for i, decl in enumerate(decls):
                        if not decl: continue
                        var_name = decl.get('name')
                        type_name_node = decl.get('typeName')
                        if type_name_node:
                            t_text = self._extract_text(type_name_node, source_bytes)
                            default_val = self._get_default_value_for_type(t_text)
                            current_block_content.append(f"{var_name} = {default_val};")

 
            else:
                # Linear statement
                text = self._extract_text(stmt, source_bytes)
                text = text.strip()
                
                # Heuristic: Fix missing semicolons for simple statements
                if stmt_type in ['Return', 'ReturnStatement', 'ExpressionStatement', 'EmitStatement', 'RevertStatement']:
                    if not text.endswith(';'):
                        text += ';'
                        
                current_block_content.append(text)
        
        # Flush remaining
        if current_block_content:
            # Check if the block ends with a terminal statement
            last_text = current_block_content[-1]
            is_terminal = False
            if last_text.startswith('return ') or last_text.startswith('revert(') or last_text.startswith('revert '):
                 is_terminal = True
            
            blocks.append({
                'id': current_id,
                'content': "\n".join(current_block_content),
                'next': 0 if not is_terminal else None
            })
        else:
            pass
            
        return blocks, hoisted_vars

    def _generate_dispatcher(self, blocks: List[Dict], hoisted_vars: List[str]) -> str:
        """
        Generates dispatcher code with hoisted variables.
        """
        import textwrap
        
        dispatcher = "{\n"
        
        # Inject hoisted variables (Grouped nicely)
        if hoisted_vars:
            dispatcher += "        // --- Hoisted Local Variables ---\n"
            for var_decl in hoisted_vars:
                 # Already indented when appending
                dispatcher += f"{var_decl}\n"
            dispatcher += "        // -------------------------------\n\n"
            
        dispatcher += "        uint256 state = 1;\n        while (state != 0) {\n"
        
        # Filter blocks that are actually reachable
        valid_blocks = [b for b in blocks if b['content'].strip() != ""]
        if not valid_blocks:
            valid_blocks = blocks
            
        # Shuffle presentation order
        presentation_blocks = list(blocks)
        random.shuffle(presentation_blocks)
        
        first = True
        for b in presentation_blocks:
            prefix = "if" if first else "else if"
            first = False
            
            bid = b['id']
            content = b['content']
            next_id = b.get('next')
            
            block_code = f"            {prefix} (state == {bid}) {{\n"
            
            # Smart Indentation: Dedent first to remove common prefix, then indent to dispatcher level
            dedented = textwrap.dedent(content)
            # We want 16 spaces (4 * 4)
            indented_content = textwrap.indent(dedented.strip(), "                ")
            
            block_code += f"{indented_content}\n"
            if next_id is not None:
                block_code += f"                state = {next_id};\n"
            block_code += "            }\n"
            
            dispatcher += block_code
            
        dispatcher += "        }\n    }"
        return dispatcher
