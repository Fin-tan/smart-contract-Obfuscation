#!/usr/bin/env python3
"""
Scalar-to-Vector (Struct Grouping) pass:
Collectively declare scalar state variables in a structure and call them through the structure.
Based on Algorithm 5 of the BiAn paper.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass
class ContractInfo:
    contract_id: int
    insert_pos: int


@dataclass
class ScalarVarInfo:
    var_id: int
    name: str          # Original Name (e.g., 'salary')
    member_name: str   # Hashed Member Name (e.g., 'm_f0eb29...')
    type_string: str   # Type (e.g., 'uint256')
    contract_id: int


_SUPPORTED_TYPES = {"uint256", "uint", "bool", "address", "string", "bytes"}
# Expanded visibility support slightly, but mostly private/internal are safe candidates
_ALLOWED_VISIBILITIES = {"private", "internal", "public"} 
_DECLARATION_PREFIXES = ("uint", "int", "bool", "address", "bytes", "string")


def _parse_src_range(src: str) -> Tuple[int, int]:
    parts = src.split(":")
    start = int(parts[0])
    length = int(parts[1]) if len(parts) > 1 else 0
    return start, start + length


def _generate_member_name(original_name: str) -> str:
    """
    Generate a hashed member name using SHA-1 as described in the paper.
    Ex: 'gasConsumption' -> 'f0eb29...'
    We prefix with 'm_' to ensure valid Solidity identifier.
    """
    sha1 = hashlib.sha1(original_name.encode('utf-8')).hexdigest()
    # Take first 16 chars for brevity, ensuring it looks "cryptographic" but not too long
    return f"m_{sha1[:16]}"


def _collect_contract_infos(ast: dict, source_bytes: bytes) -> Dict[int, ContractInfo]:
    infos: Dict[int, ContractInfo] = {}

    def visit(node):
        if isinstance(node, dict):
            if node.get("nodeType") == "ContractDefinition":
                contract_id = node.get("id")
                try:
                    start, end = _parse_src_range(node.get("src", "0:0"))
                except Exception:
                    start = end = 0
                
                # Find insertion point (opening brace)
                contract_slice = source_bytes[start:end]
                brace_offset = contract_slice.find(b"{")
                if brace_offset != -1:
                    insert_pos = start + brace_offset + 1
                    # Handle newline adjustments
                    if source_bytes[insert_pos:insert_pos+2] == b"\r\n":
                        insert_pos += 2
                    elif source_bytes[insert_pos:insert_pos+1] == b"\n":
                        insert_pos += 1
                    else:
                        newline_idx = source_bytes.find(b"\n", insert_pos)
                        insert_pos = newline_idx + 1 if newline_idx != -1 else insert_pos
                    
                    infos[contract_id] = ContractInfo(contract_id=contract_id, insert_pos=insert_pos)
                
                for child in node.get("nodes", []):
                    visit(child)
            else:
                for value in node.values():
                    if isinstance(value, (dict, list)):
                        visit(value)
        elif isinstance(node, list):
            for element in node:
                visit(element)

    visit(ast)
    return infos


def _collect_scalar_vars(ast: dict, contract_infos: Dict[int, ContractInfo]) -> Dict[int, ScalarVarInfo]:
    vars_found: Dict[int, ScalarVarInfo] = {}

    def visit(node, current_contract: Optional[int] = None):
        if isinstance(node, dict):
            node_type = node.get("nodeType")
            if node_type == "ContractDefinition":
                current_contract = node.get("id")
            elif node_type == "VariableDeclaration" and current_contract in contract_infos:
                if node.get("stateVariable") and not node.get("constant"):
                    visibility = node.get("visibility") or ""
                    type_desc = (node.get("typeDescriptions") or {}).get("typeString") or ""
                    
                    # Check compatibility
                    is_compatible_type = False
                    for t in _SUPPORTED_TYPES:
                        if type_desc.startswith(t): 
                             is_compatible_type = True
                             break
                    
                    if is_compatible_type:
                        # Only handle variables without inline initialization to avoid complexity
                        if node.get("value") is None:
                            name = node.get("name")
                            # Avoid reprocessing already obfuscated variables
                            if name and not name.startswith("__scalar_") and not name.startswith("m_"):
                                var_id = node.get("id")
                                if var_id is not None:
                                    member_name = _generate_member_name(name)
                                    vars_found[var_id] = ScalarVarInfo(
                                        var_id=var_id,
                                        name=name,
                                        member_name=member_name,
                                        type_string=type_desc,
                                        contract_id=current_contract,
                                    )
            for value in node.values():
                if isinstance(value, (dict, list)):
                    visit(value, current_contract)
        elif isinstance(node, list):
            for element in node:
                visit(element, current_contract)

    visit(ast, None)
    return vars_found


def _remove_original_declarations(source_bytes: bytes, scalar_vars: Dict[int, ScalarVarInfo], ast: dict) -> bytes:
    """
    Remove the original declaration lines: `uint private x;`
    """
    # Collect ranges to remove
    ranges_to_remove = []

    def visit(node):
        if isinstance(node, dict):
            if node.get("nodeType") == "VariableDeclaration":
                var_id = node.get("id")
                if var_id in scalar_vars:
                   # This declaration must be removed (or commented out)
                   # But typically it's inside a VariableDeclarationStatement?
                   # Actually AST usually has VariableDeclaration for state vars directly in ContractDefinition nodes
                   pass
            
            # Since state variables are direct children of ContractDefinition, we can look for them
            if node.get("nodeType") == "VariableDeclaration" and node.get("id") in scalar_vars:
                 try:
                     start, end = _parse_src_range(node.get("src", "0:0"))
                     # Try to extend to semicolon
                     context = source_bytes[end:end+20].decode('utf-8', errors='ignore')
                     semi_idx = context.find(';')
                     if semi_idx != -1:
                         end += semi_idx + 1
                     ranges_to_remove.append((start, end))
                 except:
                     pass

            for value in node.values():
                if isinstance(value, (dict, list)):
                    visit(value)
        elif isinstance(node, list):
            for element in node:
                visit(element)

    visit(ast)
    
    # Sort reverse to remove safely
    ranges_to_remove.sort(key=lambda x: x[0], reverse=True)
    
    out_bytes = bytearray(source_bytes)
    for start, end in ranges_to_remove:
        # Check integrity (bounds)
        if start < len(out_bytes) and end <= len(out_bytes):
             # Replace with whitespace to preserve offsets for other steps if possible, 
             # but here we are modifying heavily... actually usually better to remove content.
             # But if we remove content, previous offsets map become invalid.
             # However, we are doing a full pass rewrite.
             # Ideally validation logic should be robust.
             # Let's verify if we need to completely remove or comment out.
             # Commenting out is safer:
             # out_bytes[start:end] = b' ' * (end - start) 
             # No, that leaves empty lines. Let's delete it.
             del out_bytes[start:end]
    
    return bytes(out_bytes)


def _replace_usages(text: str, info_map: Dict[str, ScalarVarInfo], struct_instance_name: str) -> str:
    """
    Replace `varName` with `structName.memberName`.
    """
    if not info_map:
        return text

    # Regex for whole word match
    names_pattern = "|".join(rf"\b{re.escape(name)}\b" for name in info_map.keys())
    pattern = re.compile(names_pattern)

    def replacer(match: re.Match[str]) -> str:
        name = match.group(0)
        info = info_map[name]
        
        # Heuristic: verify it's not a declaration being added (though we removed originals)
        # Check context? No, just replace usage.
        
        return f"{struct_instance_name}.{info.member_name}"

    return pattern.sub(replacer, text)


def _insert_struct_definitions(source: str, contract_infos: Dict[int, ContractInfo],
                               vars_by_contract: Dict[int, List[ScalarVarInfo]],
                               struct_name: str, instance_name: str) -> str:
    if not vars_by_contract:
        return source

    inserts: List[Tuple[int, str]] = []
    
    for contract_id, vars_in_contract in vars_by_contract.items():
        contract_info = contract_infos.get(contract_id)
        if not contract_info:
            continue
        
        lines: List[str] = []
        lines.append(f"    struct {struct_name} {{")
        
        for var_info in vars_in_contract:
            # members: type memberName;
            lines.append(f"        {var_info.type_string} {var_info.member_name};")
        
        lines.append("    }")
        lines.append(f"    {struct_name} private {instance_name};")
        lines.append("")
        
        block = "\n".join(lines)
        inserts.append((contract_info.insert_pos, block))

    # Apply inserts (reverse order)
    inserts.sort(key=lambda item: item[0], reverse=True)
    new_source = source
    for pos, text in inserts:
        new_source = new_source[:pos] + text + new_source[pos:]
    
    return new_source


def split_scalar_variables(source_text: str, ast_json_path: Optional[str] = None) -> Tuple[str, int]:
    if not ast_json_path or not os.path.exists(ast_json_path):
        return source_text, 0

    try:
        with open(ast_json_path, "r", encoding="utf-8") as f:
            ast = json.load(f)
    except Exception as exc:
        print(f"[WARN] Failed to load AST for scalar split: {exc}")
        return source_text, 0

    source_bytes = source_text.encode("utf-8")
    contract_infos = _collect_contract_infos(ast, source_bytes)
    scalar_vars = _collect_scalar_vars(ast, contract_infos)
    
    if not scalar_vars:
        return source_text, 0

    # Group vars by contract
    vars_by_contract: Dict[int, List[ScalarVarInfo]] = {}
    for info in scalar_vars.values():
        vars_by_contract.setdefault(info.contract_id, []).append(info)

    # 1. Remove Original Declarations
    # We do this first on bytes to be accurate with AST offsets
    # Note: `_remove_original_declarations` logic needs to be robust. 
    # Because we are processing based on AST offsets, removing text INVALIDATES subsequent offsets if we are not careful.
    # However, since `_remove_original_declarations` collects ALL removals first (based on initial AST), then deletes them in reverse order, it is safe.
    
    # Wait, `source_bytes` is the basis for offsets.
    source_bytes_cleaned = _remove_original_declarations(source_bytes, scalar_vars, ast)
    current_source = source_bytes_cleaned.decode('utf-8')

    # 2. Setup Naming
    STRUCT_DEF_NAME = "__BiAnScalars"
    STRUCT_INST_NAME = "__scalar_vectors"

    info_map = {info.name: info for info in scalar_vars.values()}

    # 3. Replace Usages
    # Since we removed declarations, we don't have to worry about replacing the declaration name.
    # We just replace any remaining occurrence of the name.
    current_source = _replace_usages(current_source, info_map, STRUCT_INST_NAME)

    # 4. Insert Struct Definitions
    # We need to re-find contract insertion points because text length changed!
    # Or, we can blindly try to reuse known insertion points? No, offsets shifted.
    # We should re-scan for contract definitions to find insertion points.
    
    # Quick regex re-scan for Contract start to be safe?
    # Or simpler: Just prepend the struct to the contract body... 
    # Actually, `demopy` regenerates AST after steps. So we can't easily regenerate AST *inside* this step.
    # But since we only removed text, maybe we can track the delta? 
    # Or... we can switch the order?
    
    # STRATEGY CHANGE:
    # 1. Insert Structs (using original AST offsets) -> Text GROWS.
    # 2. Replace Usages (Regex) -> Text changes length.
    # 3. Remove Original Declarations (using original AST offsets + Delta adjustment?) -> Hard.
    
    # Alternative Strategy:
    # 1. Collect all Ops (Insert Struct, Remove Decl, Replace Usage).
    # 2. `Insert Struct` at pos X.
    # 3. `Remove Decl` at [Start, End].
    # 4. `Replace` is regex based.
    
    # Let's stick to the simpler Re-Parse Strategy for offsets if possible? No, we don't have compiler here.
    
    # Let's try "Replace Decl with Empty" to keep offsets? No, ugly.
    
    # Best Strategy for single pass without re-parsing:
    # 1. Calculate all "Replacements" needed.
    #    - Removal of Decl: Replace [Start, End] with ""
    #    - Insertion of Struct: Replace [InsertionPos, InsertionPos] with "Struct..."
    # 2. Usages? Usages are hard because we don't have their offsets from AST easily (AST only gives definition).
    #    Reference id search `_collect_identifier_occurrences` (like in local_state_obfuscator) is safer!
    
    # Let's reuse the `_collect_identifier_occurrences` logic from `local_state_obfuscator.py`!
    # It scans AST for Identifier nodes referencing the target ID.
    
    # ... But `scalar_splitter` didn't have that before.
    # I will adapt the structure to be similar to `convert_locals_to_state` which is robust with offsets.
    
    pass # Re-implementing correctly below

def _collect_identifier_occurrences(node, target_ids: set, occurrences: List[Tuple[int, int, str]]):
    if isinstance(node, dict):
        if node.get('nodeType') == 'Identifier':
            ref_id = node.get('referencedDeclaration')
            if ref_id in target_ids:
                try:
                    start, end = _parse_src_range(node['src'])
                     # We store just the range to replace
                    occurrences.append((start, end, str(ref_id))) 
                except:
                    pass
        for value in node.values():
            if isinstance(value, (dict, list)):
                _collect_identifier_occurrences(value, target_ids, occurrences)
    elif isinstance(node, list):
        for element in node:
            _collect_identifier_occurrences(element, target_ids, occurrences)

# Re-structure the main flow to be Offset-safe
def split_scalar_variables_robust(source_text: str, ast_json_path: Optional[str] = None) -> Tuple[str, int]:
    if not ast_json_path or not os.path.exists(ast_json_path):
        return source_text, 0

    try:
        with open(ast_json_path, "r", encoding="utf-8") as f:
            ast = json.load(f)
    except Exception as exc:
        print(f"[WARN] Failed to load AST: {exc}")
        return source_text, 0

    source_bytes = source_text.encode("utf-8")
    contract_infos = _collect_contract_infos(ast, source_bytes)
    scalar_vars = _collect_scalar_vars(ast, contract_infos)
    
    if not scalar_vars:
        return source_text, 0

    STRUCT_DEF_NAME = "__BiAnScalars"
    STRUCT_INST_NAME = "__scalar_vectors"

    replacements: List[Tuple[int, int, bytes]] = []

    # 1. Declaration Removal
    # We iterate AST again to find declaration nodes of targets
    def collect_decls(node):
        if isinstance(node, dict):
            if node.get("nodeType") == "VariableDeclaration":
                var_id = node.get("id")
                if var_id in scalar_vars:
                    try:
                        start, end = _parse_src_range(node.get("src", "0:0"))
                        # Try to extend to semicolon
                        # (Similar logic as local_state)
                        idx = end
                        while idx < len(source_bytes) and source_bytes[idx:idx+1] in (b' ', b'\t'):
                            idx += 1
                        if idx < len(source_bytes) and source_bytes[idx:idx+1] == b';':
                             idx += 1
                        
                        replacements.append((start, idx, b"")) # Delete it
                    except:
                        pass
            for v in node.values():
                if isinstance(v, (dict, list)):
                    collect_decls(v)
        elif isinstance(node, list):
            for e in node:
                collect_decls(e)
    
    collect_decls(ast)

    # 2. Usage Replacement
    target_ids = set(scalar_vars.keys())
    occurrences = []
    _collect_identifier_occurrences(ast, target_ids, occurrences)
    
    for start, end, ref_id_str in occurrences:
        var_id = int(ref_id_str)
        info = scalar_vars[var_id]
        
        # New text: structInstance.memberName
        new_text = f"{STRUCT_INST_NAME}.{info.member_name}".encode('utf-8')
        replacements.append((start, end, new_text))

    # 3. Struct Insertion
    vars_by_contract: Dict[int, List[ScalarVarInfo]] = {}
    for info in scalar_vars.values():
        vars_by_contract.setdefault(info.contract_id, []).append(info)

    for contract_id, vars_in_contract in vars_by_contract.items():
        contract_info = contract_infos.get(contract_id)
        if not contract_info: continue
        
        lines = []
        lines.append(f"    struct {STRUCT_DEF_NAME} {{")
        for var_info in vars_in_contract:
            lines.append(f"        {var_info.type_string} {var_info.member_name};")
        lines.append("    }")
        lines.append(f"    {STRUCT_DEF_NAME} private {STRUCT_INST_NAME};")
        lines.append("")
        
        block = "\n".join(lines).encode('utf-8')
        replacements.append((contract_info.insert_pos, contract_info.insert_pos, block))

    # Exec replacements sorted
    replacements.sort(key=lambda x: x[0], reverse=True)
    
    out_bytes = bytearray(source_bytes)
    for start, end, text in replacements:
        # Range check
        if start > len(out_bytes): continue 
        # For pure insertions (start==end), simple slice
        # For replacements, delete [start:end] then insert
        del out_bytes[start:end]
        out_bytes[start:start] = text

    return out_bytes.decode('utf-8'), len(scalar_vars)

split_scalar_variables = split_scalar_variables_robust
__all__ = ["split_scalar_variables"]
