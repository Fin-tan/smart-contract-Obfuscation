#!/usr/bin/env python3
"""Promote selected local variables to contract state variables (BiAn-inspired)."""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass
class ContractInfo:
    ast_id: int
    name: str
    insert_pos_bytes: int
    counter: int
    globals: List[Tuple[str, str]]  # list of (type, global_name)


@dataclass
class LocalVarInfo:
    contract_id: int
    global_name: str
    var_type: str
    statement_range: Tuple[int, int]
    init_range: Tuple[int, int]


_SUPPORTED_PRIMITIVES = (
    'uint', 'int', 'bool', 'address', 'bytes', 'string'
)


def _parse_src_range(src: str) -> Tuple[int, int]:
    """Parse solc src string "start:length:file" -> (start, end)."""
    parts = src.split(':')
    start = int(parts[0])
    length = int(parts[1]) if len(parts) > 1 else 0
    return start, start + length


def _extend_statement_end(source_bytes: bytes, start: int, end: int) -> int:
    """Extend a statement range to include trailing semicolons, comments, and newline."""
    length = len(source_bytes)
    idx = end
    if idx < length and source_bytes[idx:idx+1] == b';':
        idx += 1
    while idx < length and source_bytes[idx:idx+1] in (b' ', b'\t'):
        idx += 1
    if idx < length and source_bytes[idx:idx+2] == b'//':
        newline_idx = source_bytes.find(b'\n', idx)
        if newline_idx == -1:
            idx = length
        else:
            idx = newline_idx
    elif idx < length and source_bytes[idx:idx+2] == b'/*':
        comment_end = source_bytes.find(b'*/', idx + 2)
        if comment_end == -1:
            idx = length
        else:
            idx = comment_end + 2
    while idx < length and source_bytes[idx:idx+1] in (b' ', b'\t'):
        idx += 1
    if idx < length and source_bytes[idx:idx+2] == b'\r\n':
        idx += 2
    elif idx < length and source_bytes[idx:idx+1] in (b'\n', b'\r'):
        idx += 1
    return idx


def _sanitize_identifier(name: str) -> str:
    sanitized = re.sub(r'[^0-9a-zA-Z_]', '_', name or 'var')
    if not sanitized or sanitized[0].isdigit():
        sanitized = f'v_{sanitized}'
    return sanitized


def _sanitize_type(type_string: str) -> Optional[str]:
    """Simplify solc typeString for state variable declaration."""
    if not type_string:
        return None
    # reject complex types (structs, mappings, enums, contracts)
    lowered = type_string.lower()
    if any(bad in lowered for bad in ('struct ', 'mapping(', ' contract ', 'enum ', 'function (')):
        return None
    base = type_string
    # remove pointer qualifiers
    base = base.replace(' storage pointer', '')
    base = base.replace(' storage ref', '')
    base = base.replace(' storage', '')
    base = base.replace(' memory', '')
    base = base.replace(' calldata', '')
    base = re.sub(r'\s+', ' ', base).strip()
    # allow arrays and primitive types
    head = base.split('[')[0]
    if not head:
        return None
    primitive_ok = any(head.startswith(t) for t in _SUPPORTED_PRIMITIVES)
    if not primitive_ok:
        return None
    return base


def _gather_contract_info(source_bytes: bytes, contract_node: dict) -> Optional[ContractInfo]:
    contract_id = contract_node.get('id')
    name = contract_node.get('name') or f'Contract_{contract_id}'
    try:
        start, end = _parse_src_range(contract_node['src'])
    except Exception:
        return None
    contract_slice = source_bytes[start:end]
    brace_offset = contract_slice.find(b'{')
    if brace_offset == -1:
        return None
    insert_pos = start + brace_offset + 1
    # move insertion after newline if present
    if source_bytes[insert_pos:insert_pos+2] == b'\r\n':
        insert_pos += 2
    elif source_bytes[insert_pos:insert_pos+1] == b'\n':
        insert_pos += 1
    else:
        newline_idx = source_bytes.find(b'\n', insert_pos)
        if newline_idx != -1:
            insert_pos = newline_idx + 1
        else:
            insert_pos = start + brace_offset + 1
    return ContractInfo(ast_id=contract_id, name=name, insert_pos_bytes=insert_pos, counter=0, globals=[])


def _collect_contract_infos(node, source_bytes: bytes, out: Dict[int, ContractInfo]) -> None:
    if isinstance(node, dict):
        if node.get('nodeType') == 'ContractDefinition':
            info = _gather_contract_info(source_bytes, node)
            if info:
                out[node['id']] = info
            for child in node.get('nodes', []):
                _collect_contract_infos(child, source_bytes, out)
        else:
            for value in node.values():
                if isinstance(value, (dict, list)):
                    _collect_contract_infos(value, source_bytes, out)
    elif isinstance(node, list):
        for element in node:
            _collect_contract_infos(element, source_bytes, out)


def _traverse(node, contract_stack: List[ContractInfo], local_infos: Dict[int, LocalVarInfo],
              source_bytes: bytes, function_skip_stack: List[bool],
              contract_lookup: Dict[int, ContractInfo]) -> None:
    if isinstance(node, dict):
        node_type = node.get('nodeType')
        if node_type == 'ContractDefinition':
            contract_id = node.get('id')
            info = contract_lookup.get(contract_id)
            if info is None:
                info = _gather_contract_info(source_bytes, node)
                if info:
                    contract_lookup[contract_id] = info
            contract_stack.append(info if info else ContractInfo(ast_id=-1, name='Unknown', insert_pos_bytes=0, counter=0, globals=[]))
            for child in node.get('nodes', []):
                _traverse(child, contract_stack, local_infos, source_bytes, function_skip_stack, contract_lookup)
            contract_stack.pop()
            return
        if node_type == 'FunctionDefinition':
            mutability = (node.get('stateMutability') or '').lower()
            is_skip = mutability in ('pure', 'view')
            function_skip_stack.append(is_skip)
            # traverse body & other children
            for key, value in node.items():
                if isinstance(value, (dict, list)):
                    _traverse(value, contract_stack, local_infos, source_bytes, function_skip_stack, contract_lookup)
            function_skip_stack.pop()
            return
        if node_type == 'VariableDeclarationStatement':
            if not contract_stack:
                return
            if any(function_skip_stack):
                return
            declarations = node.get('declarations') or []
            if len(declarations) != 1:
                return
            declaration = declarations[0]
            if not declaration or declaration.get('stateVariable'):
                return
            if not declaration.get('name'):
                return
            initial = node.get('initialValue')
            if not initial:
                return
            type_string = (declaration.get('typeDescriptions') or {}).get('typeString')
            var_type = _sanitize_type(type_string)
            if not var_type:
                return
            contract_info = contract_stack[-1]
            if contract_info.insert_pos_bytes == 0 and contract_info.name == 'Unknown':
                return
            try:
                stmt_start, stmt_end = _parse_src_range(node['src'])
                stmt_end = _extend_statement_end(source_bytes, stmt_start, stmt_end)
                init_range = _parse_src_range(initial['src'])
            except Exception:
                return
            sanitized_name = _sanitize_identifier(declaration['name'])
            global_name = f"__state_{sanitized_name}_{contract_stack[-1].counter}"
            contract_stack[-1].counter += 1
            contract_stack[-1].globals.append((var_type, global_name))
            decl_id = declaration.get('id')
            if decl_id is None:
                return
            local_infos[decl_id] = LocalVarInfo(
                contract_id=contract_stack[-1].ast_id,
                global_name=global_name,
                var_type=var_type,
                statement_range=(stmt_start, stmt_end),
                init_range=init_range
            )
            # still traverse children for nested identifiers (initial value, etc.)
        # Continue traversal for nested nodes
        for key, value in node.items():
            if isinstance(value, (dict, list)):
                _traverse(value, contract_stack, local_infos, source_bytes, function_skip_stack, contract_lookup)
    elif isinstance(node, list):
        for element in node:
            _traverse(element, contract_stack, local_infos, source_bytes, function_skip_stack, contract_lookup)


def _collect_identifier_occurrences(node, target_ids: Dict[int, LocalVarInfo], occurrences: List[Tuple[int, int, str]],
                                     statement_ranges: List[Tuple[int, int]]) -> None:
    if isinstance(node, dict):
        if node.get('nodeType') == 'Identifier':
            ref_id = node.get('referencedDeclaration')
            if ref_id in target_ids:
                try:
                    start, end = _parse_src_range(node['src'])
                except Exception:
                    start = end = -1
                if start >= 0:
                    # Skip identifiers inside the original declaration statement (they will be replaced wholesale)
                    if any(stmt_start <= start and end <= stmt_end for stmt_start, stmt_end in statement_ranges):
                        pass
                    else:
                        occurrences.append((start, end, target_ids[ref_id].global_name))
        for value in node.values():
            if isinstance(value, (dict, list)):
                _collect_identifier_occurrences(value, target_ids, occurrences, statement_ranges)
    elif isinstance(node, list):
        for element in node:
            _collect_identifier_occurrences(element, target_ids, occurrences, statement_ranges)


def convert_locals_to_state(source_text: str, ast_json_path: Optional[str] = None) -> Tuple[str, int]:
    """Promote selected local variables to contract state variables."""
    if not ast_json_path or not os.path.exists(ast_json_path):
        return source_text, 0

    try:
        with open(ast_json_path, 'r', encoding='utf-8') as f:
            ast = json.load(f)
    except Exception as exc:
        print(f"[WARN] Failed to load AST for local-to-state conversion: {exc}")
        return source_text, 0

    source_bytes = source_text.encode('utf-8')

    contract_lookup: Dict[int, ContractInfo] = {}
    _collect_contract_infos(ast, source_bytes, contract_lookup)

    contract_stack: List[ContractInfo] = []
    local_infos: Dict[int, LocalVarInfo] = {}

    _traverse(ast, contract_stack, local_infos, source_bytes, function_skip_stack=[], contract_lookup=contract_lookup)

    if not local_infos:
        return source_text, 0

    # Gather identifier occurrences referencing promoted locals
    occurrences: List[Tuple[int, int, str]] = []
    statement_ranges = [info.statement_range for info in local_infos.values()]
    _collect_identifier_occurrences(ast, local_infos, occurrences, statement_ranges)

    # Prepare replacements for declaration statements
    replacements: List[Tuple[int, int, bytes]] = []
    for info in local_infos.values():
        start, end = info.statement_range
        init_start, init_end = info.init_range
        stmt_bytes = source_bytes[start:end]
        init_expr = source_bytes[init_start:init_end].decode('utf-8').strip()
        stmt_text = stmt_bytes.decode('utf-8')
        leading_ws = re.match(r'\s*', stmt_text).group(0)
        semicolon_idx = stmt_text.find(';')
        if semicolon_idx == -1:
            semicolon_idx = len(stmt_text)
        after_semicolon = stmt_text[semicolon_idx+1:]
        new_stmt = f"{leading_ws}{info.global_name} = {init_expr};{after_semicolon}"
        replacements.append((start, end, new_stmt.encode('utf-8')))

    # Combine identifier replacements
    for start, end, global_name in occurrences:
        replacements.append((start, end, global_name.encode('utf-8')))

    # Insert global declarations per contract
    for contract_info in contract_lookup.values():
        if not contract_info.globals:
            continue
        block_lines = ["", "    // === local-to-state promoted variables ==="]
        for var_type, global_name in contract_info.globals:
            block_lines.append(f"    {var_type} private {global_name};")
        block_lines.append("")
        block = "\n".join(block_lines).encode('utf-8')
        replacements.append((contract_info.insert_pos_bytes, contract_info.insert_pos_bytes, block))

    # Apply replacements (sorted descending to keep offsets stable)
    replacements.sort(key=lambda x: x[0], reverse=True)
    out_bytes = source_bytes
    for start, end, text in replacements:
        out_bytes = out_bytes[:start] + text + out_bytes[end:]

    return out_bytes.decode('utf-8'), len(local_infos)


__all__ = ["convert_locals_to_state"]
