#!/usr/bin/env python3
"""Simplified scalar splitting pass: wrap scalar state variables with vector-backed getters/setters."""
from __future__ import annotations

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
    name: str
    sanitized: str
    type_string: str
    contract_id: int


_SUPPORTED_TYPES = {"uint256", "uint"}
_ALLOWED_VISIBILITIES = {"private", "internal"}
_DECLARATION_PREFIXES = ("uint", "int", "bool", "address", "bytes", "string")


def _parse_src_range(src: str) -> Tuple[int, int]:
    parts = src.split(":")
    start = int(parts[0])
    length = int(parts[1]) if len(parts) > 1 else 0
    return start, start + length


def _sanitize_identifier(name: str) -> str:
    sanitized = re.sub(r"[^0-9a-zA-Z_]", "_", name or "var")
    if not sanitized or sanitized[0].isdigit():
        sanitized = f"v_{sanitized}"
    return sanitized


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
                contract_slice = source_bytes[start:end]
                brace_offset = contract_slice.find(b"{")
                if brace_offset != -1:
                    insert_pos = start + brace_offset + 1
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
                    if visibility in _ALLOWED_VISIBILITIES and type_desc in _SUPPORTED_TYPES:
                        if node.get("value") is None:
                            name = node.get("name")
                            if name and not name.startswith("__scalar_"):
                                var_id = node.get("id")
                                if var_id is not None:
                                    vars_found[var_id] = ScalarVarInfo(
                                        var_id=var_id,
                                        name=name,
                                        sanitized=_sanitize_identifier(name),
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


def _replace_scalar_reads(text: str, info_map: Dict[str, ScalarVarInfo]) -> str:
    if not info_map:
        return text

    names_pattern = "|".join(rf"\b{re.escape(name)}\b" for name in info_map.keys())
    pattern = re.compile(names_pattern)

    def replacer(match: re.Match[str]) -> str:
        name = match.group(0)
        info = info_map[name]
        start = match.start()
        prefix = match.string[max(0, start - 12):start]
        if "__scalar_" in prefix:
            return name
        line_start = match.string.rfind("\n", 0, start) + 1
        line_end = match.string.find("\n", match.end())
        if line_end == -1:
            line_end = len(match.string)
        line = match.string[line_start:line_end]
        stripped = line.lstrip()
        for decl_prefix in _DECLARATION_PREFIXES:
            if stripped.startswith(decl_prefix):
                return name
        return f"__scalar_get_{info.sanitized}()"

    return pattern.sub(replacer, text)


def _rewrite_assignments_for_var(source: str, info: ScalarVarInfo, info_map: Dict[str, ScalarVarInfo]) -> str:
    pattern = re.compile(
        rf"(^\s*){re.escape(info.name)}\s*=\s*(.+?);([^\n]*)(\r?\n|$)",
        flags=re.MULTILINE
    )

    def repl(match: re.Match[str]) -> str:
        indent, rhs, trailing, newline = match.groups()
        rhs_transformed = _replace_scalar_reads(rhs.strip(), info_map)
        new_stmt = f"{indent}__scalar_set_{info.sanitized}({rhs_transformed});"
        if trailing:
            new_stmt += trailing
        return new_stmt + newline

    return pattern.sub(repl, source)


def _insert_helper_blocks(source: str, contract_infos: Dict[int, ContractInfo],
                          vars_by_contract: Dict[int, List[ScalarVarInfo]]) -> str:
    if not vars_by_contract:
        return source
    inserts: List[Tuple[int, str]] = []
    for contract_id, vars_in_contract in vars_by_contract.items():
        contract_info = contract_infos.get(contract_id)
        if not contract_info:
            continue
        lines: List[str] = []
        lines.append("    // === scalar splitting helpers ===")
        for idx, var_info in enumerate(vars_in_contract):
            if idx > 0:
                lines.append("")
            lines.append(f"    uint256[2] private __scalar_{var_info.sanitized};")
            lines.append(f"    function __scalar_get_{var_info.sanitized}() internal view returns ({var_info.type_string}) {{")
            lines.append(f"        return {var_info.type_string}(__scalar_{var_info.sanitized}[0] ^ __scalar_{var_info.sanitized}[1]);")
            lines.append("    }")
            lines.append("")
            lines.append(f"    function __scalar_set_{var_info.sanitized}({var_info.type_string} value) internal {{")
            lines.append(f"        uint256 noise = uint256(keccak256(abi.encode(value, address(this))));")
            lines.append(f"        __scalar_{var_info.sanitized}[0] = noise;")
            lines.append(f"        __scalar_{var_info.sanitized}[1] = noise ^ uint256(value);")
            lines.append(f"        {var_info.name} = noise;")
            lines.append("    }")
        lines.append("")
        block = "\n".join(lines)
        inserts.append((contract_info.insert_pos, block + "\n"))

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

    vars_by_contract: Dict[int, List[ScalarVarInfo]] = {}
    for info in scalar_vars.values():
        vars_by_contract.setdefault(info.contract_id, []).append(info)

    current_source = source_text
    info_map = {info.name: info for info in scalar_vars.values()}

    for info in scalar_vars.values():
        current_source = _rewrite_assignments_for_var(current_source, info, info_map)

    current_source = _replace_scalar_reads(current_source, info_map)
    current_source = _insert_helper_blocks(current_source, contract_infos, vars_by_contract)

    return current_source, len(scalar_vars)


__all__ = ["split_scalar_variables"]
