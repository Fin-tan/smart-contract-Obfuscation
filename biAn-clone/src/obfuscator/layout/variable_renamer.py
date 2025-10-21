#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Variable Renamer for Solidity Smart Contracts (AST-based)
==========================================================

Obfuscate variable names, function names, and contract names
by replacing them with hash values using AST parsing.

Usage:
    python variable_renamer.py input.sol output.sol
    python variable_renamer.py input.sol output.sol --mapping mapping.json
    python variable_renamer.py input.sol output.sol --algorithm sha256

Requirements:
    pip install py-solc-x

Author: Smart Contract Obfuscator Team
Version: 2.0.0 (AST-based)
"""

import sys #thao tac voi he thong: thoat file doc argv
import os #thao tác với file,dường dẫn
import re
import hashlib #hash
import json
import argparse
from typing import Set, Dict, Optional, List, Tuple
from pathlib import Path # xử lí đường dãn dạng đối tượng

# Import Solidity compiler
try:
    import solcx
    from solcx import compile_source, compile_files, install_solc, set_solc_version
except ImportError:
    print("Error: py-solc-x not installed")
    print("Please install: pip install py-solc-x")
    sys.exit(1)


# ============================================
# AST PARSER CLASS
# ============================================

class SolidityASTParser:
    """
    Parse Solidity source code and extract identifiers using AST
    """
    
    def __init__(self, solc_version: str = '0.8.30'):
        """
        Initialize AST Parser
        
        Args:
            solc_version: Solidity compiler version
        """
        self.solc_version = solc_version
        self._setup_compiler()
    
    def _setup_compiler(self):
        """Setup Solidity compiler"""
        try:
            # Check if version is installed
            installed_versions = solcx.get_installed_solc_versions()
            
            if self.solc_version not in [str(v) for v in installed_versions]:
                print(f"Installing Solidity compiler {self.solc_version}...")
                install_solc(self.solc_version)
                print(f"  ✓ Installed")
            
            set_solc_version(self.solc_version)
            
        except Exception as e:
            print(f"Warning: Could not setup Solidity compiler: {e}")
            print("Will attempt to use default compiler")
    
    def compile_to_ast(self, source_code: str, file_path: str = None) -> Dict:
        """
        Compile Solidity source to AST
        
        Args:
            source_code: Solidity source code
            file_path: Optional file path (for better error messages)
            
        Returns:
            AST dictionary
        """
        try:
            if file_path and os.path.exists(file_path):
                # Compile from file
                compiled = compile_files(
                    [file_path],
                    output_values=['ast'],
                    solc_version=self.solc_version
                )
                contract_name = list(compiled.keys())[0]
                ast = compiled[contract_name]['ast']
            else:
                # Compile from source
                compiled = compile_source(
                    source_code,
                    output_values=['ast'],
                    solc_version=self.solc_version
                )
                contract_name = list(compiled.keys())[0]
                ast = compiled[contract_name]['ast']
            
            if file_path:
                ast_output_path=os.path.splitext(file_path)[0] + '_ast.json'
            else:
                ast_output_path='output_ast.json'

            with open(ast_output_path, 'w', encoding='utf-8') as f:
                json.dump(ast, f, indent=2)
            print(f"AST saved to: {ast_output_path}")
            return ast
            
        except Exception as e:
            print(f"Error compiling source code: {e}")
            return None
    
    def extract_identifiers(self, ast: Dict) -> Set[str]:
        """
        Extract all identifiers from AST
        
        Args:
            ast: AST dictionary
            
        Returns:
            Set of identifier names
        """
        if not ast:
            return set()
        
        identifiers = set()
        
        # Traverse AST and collect identifiers
        self._traverse_ast(ast, identifiers)
        
        return identifiers
    
    def _traverse_ast(self, node, identifiers: Set[str]):
        """
        Recursively traverse AST tree
        
        Args:
            node: Current AST node
            identifiers: Set to collect identifiers
        """
        if not isinstance(node, dict):
            return
        
        node_type = node.get('nodeType')
        
        # Extract name from different node types
        if node_type == 'ContractDefinition':
            # Contract name
            name = node.get('name')
            if name:
                identifiers.add(name)
        
        elif node_type == 'FunctionDefinition':
            # Function name
            name = node.get('name')
            if name and name not in ['', 'constructor', 'fallback', 'receive']:
                identifiers.add(name)
        
        elif node_type == 'VariableDeclaration':
            # Variable name
            name = node.get('name')
            if name:
                identifiers.add(name)
        
        elif node_type == 'Identifier':
            # Identifier usage
            name = node.get('name')
            if name:
                identifiers.add(name)
        
        elif node_type == 'ModifierDefinition':
            # Modifier name
            name = node.get('name')
            if name:
                identifiers.add(name)
        
        elif node_type == 'EventDefinition':
            # Event name
            name = node.get('name')
            if name:
                identifiers.add(name)
        
        elif node_type == 'StructDefinition':
            # Struct name
            name = node.get('name')
            if name:
                identifiers.add(name)
        
        elif node_type == 'EnumDefinition':
            # Enum name
            name = node.get('name')
            if name:
                identifiers.add(name)
        
        elif node_type == 'ErrorDefinition':
            # Error name
            name = node.get('name')
            if name:
                identifiers.add(name)
        
        # Recursively traverse children
        for key, value in node.items():
            if isinstance(value, dict):
                self._traverse_ast(value, identifiers)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        self._traverse_ast(item, identifiers)


# ============================================
# VARIABLE RENAMER CLASS
# ============================================

class VariableRenamer:
    """
    Rename variables, functions, and contracts using AST
    """
    
    def __init__(self, 
                 hash_algorithm: str = 'sha1',
                 prefix: str = 'OX',
                 hash_length: int = 38,
                 solc_version: str = '0.8.30'):
        """
        Initialize Variable Renamer
        
        Args:
            hash_algorithm: Hash algorithm ('sha1', 'sha256', 'md5')
            prefix: Prefix for obfuscated names
            hash_length: Length of hash suffix
            solc_version: Solidity compiler version
        """
        self.hash_algorithm = hash_algorithm
        self.prefix = prefix
        self.hash_length = hash_length
        
        # Mapping table
        self.identifier_map: Dict[str, str] = {}
        
        # AST Parser
        self.ast_parser = SolidityASTParser(solc_version)
        
        # Solidity keywords to protect
        self.reserved_keywords = self._get_solidity_keywords()
    
    def _get_solidity_keywords(self) -> Set[str]:
        """
        Get all Solidity reserved keywords
        Khong can doi 
        """
        return {
            # Types
            'int', 'int8', 'int16', 'int24', 'int32', 'int40', 'int48', 'int56', 'int64',
            'int72', 'int80', 'int88', 'int96', 'int104', 'int112', 'int120', 'int128',
            'int136', 'int144', 'int152', 'int160', 'int168', 'int176', 'int184', 'int192',
            'int200', 'int208', 'int216', 'int224', 'int232', 'int240', 'int248', 'int256',
            'uint', 'uint8', 'uint16', 'uint24', 'uint32', 'uint40', 'uint48', 'uint56', 'uint64',
            'uint72', 'uint80', 'uint88', 'uint96', 'uint104', 'uint112', 'uint120', 'uint128',
            'uint136', 'uint144', 'uint152', 'uint160', 'uint168', 'uint176', 'uint184', 'uint192',
            'uint200', 'uint208', 'uint216', 'uint224', 'uint232', 'uint240', 'uint248', 'uint256',
            'address', 'bool', 'string', 
            'bytes', 'bytes1', 'bytes2', 'bytes3', 'bytes4', 'bytes5', 'bytes6', 'bytes7', 'bytes8',
            'bytes9', 'bytes10', 'bytes11', 'bytes12', 'bytes13', 'bytes14', 'bytes15', 'bytes16',
            'bytes17', 'bytes18', 'bytes19', 'bytes20', 'bytes21', 'bytes22', 'bytes23', 'bytes24',
            'bytes25', 'bytes26', 'bytes27', 'bytes28', 'bytes29', 'bytes30', 'bytes31', 'bytes32',
            'mapping', 'struct', 'enum', 'array',
            
            # Keywords
            'contract', 'interface', 'library', 'abstract',
            'function', 'modifier', 'event', 'error',
            'constructor', 'fallback', 'receive',
            'is', 'override', 'virtual',
            
            # Visibility
            'public', 'private', 'internal', 'external',
            
            # State mutability
            'pure', 'view', 'payable', 'constant', 'immutable',
            
            # Storage
            'storage', 'memory', 'calldata',
            
            # Control flow
            'if', 'else', 'for', 'while', 'do', 'break', 'continue', 'return',
            'try', 'catch', 'throw',
            
            # Error handling
            'require', 'assert', 'revert',
            
            # Built-in variables and members
            'msg', 'sender', 'value', 'data', 'sig', 'gas',
            'block', 'blockhash', 'coinbase', 'difficulty', 'gaslimit',
            'number', 'timestamp', 'chainid', 'basefee', 'prevrandao',
            'tx', 'gasprice', 'origin',
            'abi', 'decode', 'encode', 'encodePacked', 'encodeWithSelector',
            'encodeWithSignature', 'encodeCall',
            'this', 'super', 'now', 'selfdestruct', 'suicide',
            
            # Others
            'import', 'pragma', 'using', 'emit', 'delete', 'new', 'var',
            'true', 'false',
            'wei', 'gwei', 'ether', 'finney', 'szabo',  # finney and szabo deprecated
            'seconds', 'minutes', 'hours', 'days', 'weeks',  # weeks deprecated
            
            # Global functions
            'addmod', 'mulmod', 'keccak256', 'sha256', 'ripemd160',
            'ecrecover', 'type',
            
            # Type members
            'length', 'push', 'pop',
            'balance', 'transfer', 'send', 'call', 'delegatecall', 'staticcall',
            'code', 'codehash',
            'name', 'creationCode', 'runtimeCode',
            'interfaceId', 'selector', 'min', 'max',
            
            # Reserved for future use
            'after', 'alias', 'apply', 'auto', 'byte', 'case', 'copyof', 'default',
            'define', 'final', 'implements', 'in', 'inline', 'let', 'macro', 'match',
            'mutable', 'null', 'of', 'partial', 'promise', 'reference', 'relocatable',
            'sealed', 'sizeof', 'static', 'supports', 'switch', 'typedef', 'typeof',
            'unchecked',
        }
    
    def generate_hash_name(self, original_name: str) -> str:
        """
        Generate hash name from original name
        
        Args:
            original_name: Original identifier name
            
        Returns:
            Hashed name with prefix
        """
        # Select hash function
        if self.hash_algorithm == 'sha1':
            hash_obj = hashlib.sha1(original_name.encode('utf-8'))
        elif self.hash_algorithm == 'sha256':
            hash_obj = hashlib.sha256(original_name.encode('utf-8'))
        elif self.hash_algorithm == 'md5':
            hash_obj = hashlib.md5(original_name.encode('utf-8'))
        else:
            raise ValueError(f"Unsupported algorithm: {self.hash_algorithm}")
        
        # Get hex digest and truncate
        hash_hex = hash_obj.hexdigest()
        hash_part = hash_hex[:self.hash_length]
        
        # Add prefix
        return f"{self.prefix}{hash_part}"
    
    def extract_identifiers_from_ast(self, source_code: str, file_path: str = None) -> Set[str]:
        """
        Extract identifiers using AST parsing
        
        Args:
            source_code: Solidity source code
            file_path: Optional file path
            
        Returns:
            Set of identifier names
        """
        # Compile to AST
        ast = self.ast_parser.compile_to_ast(source_code, file_path)
        
        if not ast:
            print("Warning: Failed to parse AST, falling back to regex")
            return self._extract_identifiers_regex(source_code)
        else: 
            print("  ✓ AST parsed successfully")
        # Extract identifiers from AST
        identifiers = self.ast_parser.extract_identifiers(ast)
        
        # Remove reserved keywords
        identifiers -= self.reserved_keywords
        
        # Remove empty strings
        identifiers.discard('')
        identifiers.discard(None)
        
        return identifiers
    
    def _extract_identifiers_regex(self, source_code: str) -> Set[str]:
        """
        Fallback: Extract identifiers using regex (if AST parsing fails)
        
        Args:
            source_code: Solidity source code
            
        Returns:
            Set of identifier names
        """
        pattern = r'\b[a-zA-Z_][a-zA-Z0-9_]*\b'
        matches = re.findall(pattern, source_code)
        identifiers = set(matches)
        
        # Remove keywords
        identifiers -= self.reserved_keywords
        
        return identifiers
    
    def obfuscate(self, source_code: str, file_path: str = None) -> str:
        """
        Obfuscate all identifiers in source code using AST
        
        Args:
            source_code: Original Solidity code
            file_path: Optional file path
            
        Returns:
            Obfuscated code
        """
        print("Parsing source code with AST...")
        
        # Extract identifiers using AST
        identifiers = self.extract_identifiers_from_ast(source_code, file_path)
        
        print(f"Found {len(identifiers)} identifiers to obfuscate")
        
        if len(identifiers) == 0:
            print("Warning: No identifiers found!")
            return source_code
        
        # Generate hash mappings
        for identifier in identifiers:
            if identifier not in self.identifier_map:
                self.identifier_map[identifier] = self.generate_hash_name(identifier)
        
        # Sort by length (longest first) to avoid partial replacements
        sorted_identifiers = sorted(identifiers, key=len, reverse=True)
        
        obfuscated_code = source_code
        total_replacements = 0
        
        # Replace each identifier
        print("Replacing identifiers...")
        for original in sorted_identifiers:
            obfuscated = self.identifier_map[original]
            
            # Use word boundary to match complete words only
            pattern = r'\b' + re.escape(original) + r'\b'
            
            # Count matches
            count = len(re.findall(pattern, obfuscated_code))
            
            if count > 0:
                # Replace
                obfuscated_code = re.sub(pattern, obfuscated, obfuscated_code)
                total_replacements += count
        
        print(f"Made {total_replacements} total replacements")
        
        return obfuscated_code
    
    def get_mapping(self) -> Dict[str, str]:
        """
        Get the identifier mapping table
        
        Returns:
            Dictionary of {original: obfuscated}
        """
        return self.identifier_map.copy()
    
    def save_mapping(self, output_path: str):
        """
        Save mapping to JSON file
        
        Args:
            output_path: Path to output JSON file
        """
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(self.identifier_map, f, indent=2, sort_keys=True)
        
        print(f"Mapping saved to: {output_path}")


# ============================================
# UTILITY FUNCTIONS
# ============================================

def read_file(file_path: str) -> str:
    """Read file content"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        print(f"Error: File not found: {file_path}")
        sys.exit(1)
    except Exception as e:
        print(f"Error reading file: {e}")
        sys.exit(1)


def write_file(file_path: str, content: str):
    """Write content to file"""
    try:
        # Create parent directory if needed
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
    except Exception as e:
        print(f"Error writing file: {e}")
        sys.exit(1)


def print_banner():
    """Print banner"""
    banner = """
╔═══════════════════════════════════════════════════════════════════╗
║                                                                   ║
║      SOLIDITY VARIABLE RENAMER / OBFUSCATOR (AST-based)           ║
║                                                                   ║
║  Obfuscate variable names using Abstract Syntax Tree parsing      ║
║  More accurate than regex-based approach                          ║
║                                                                   ║
╚═══════════════════════════════════════════════════════════════════╝
"""
    print(banner)


def print_summary(original_size: int, 
                  obfuscated_size: int, 
                  num_identifiers: int,
                  elapsed_time: float):
    """Print summary statistics"""
    print("\n" + "="*70)
    print("OBFUSCATION SUMMARY")
    print("="*70)
    print(f"Original size:        {original_size:,} characters")
    print(f"Obfuscated size:      {obfuscated_size:,} characters")
    print(f"Size change:          {obfuscated_size - original_size:+,} characters")
    print(f"Identifiers renamed:  {num_identifiers}")
    print(f"Processing time:      {elapsed_time:.3f} seconds")
    print("="*70)


def print_mapping_preview(mapping: Dict[str, str], max_items: int = 10):
    """Print preview of mapping table"""
    print("\n" + "="*70)
    print("MAPPING TABLE (Preview)")
    print("="*70)
    print(f"{'Original':<25} → {'Obfuscated'}")
    print("-"*70)
    
    items = list(mapping.items())
    for i, (original, obfuscated) in enumerate(sorted(items)):
        if i >= max_items:
            print(f"... and {len(items) - max_items} more")
            break
        print(f"{original:<25} → {obfuscated}")
    
    print("="*70)


def check_dependencies():
    """Check if required dependencies are installed"""
    try:
        import solcx
        return True
    except ImportError:
        print("\n" + "="*70)
        print("ERROR: Missing Required Dependency")
        print("="*70)
        print("\nThis script requires 'py-solc-x' to be installed.")
        print("\nPlease install it using:")
        print("  pip install py-solc-x")
        print("\nOr install all requirements:")
        print("  pip install py-solc-x")
        print("\n" + "="*70)
        return False


# ============================================
# MAIN FUNCTION
# ============================================

def main():
    """Main entry point"""
    import time
    
    # Check dependencies first
    if not check_dependencies():
        sys.exit(1)
    
    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description='Obfuscate Solidity smart contract variable names using AST',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python variable_renamer.py input.sol output.sol
  python variable_renamer.py input.sol output.sol --mapping mapping.json
  python variable_renamer.py input.sol output.sol --algorithm sha256
  python variable_renamer.py input.sol output.sol --prefix VAR --length 32
  python variable_renamer.py input.sol output.sol --solc-version 0.8.20

Note: This version uses AST (Abstract Syntax Tree) parsing for more accurate
      identifier extraction compared to regex-based approaches.
        """
    )
    
    parser.add_argument(
        'input',
        help='Input Solidity file (.sol)'
    )
    
    parser.add_argument(
        'output',
        help='Output file path for obfuscated code'
    )
    
    parser.add_argument(
        '--mapping',
        '-m',
        help='Output path for mapping JSON file (optional)',
        default=None
    )
    
    parser.add_argument(
        '--algorithm',
        '-a',
        choices=['sha1', 'sha256', 'md5'],
        default='sha1',
        help='Hash algorithm to use (default: sha1)'
    )
    
    parser.add_argument(
        '--prefix',
        '-p',
        default='OX',
        help='Prefix for obfuscated names (default: OX)'
    )
    
    parser.add_argument(
        '--length',
        '-l',
        type=int,
        default=38,
        help='Length of hash suffix (default: 38)'
    )
    
    parser.add_argument(
        '--solc-version',
        '-s',
        default='0.8.30',
        help='Solidity compiler version (default: 0.8.30)'
    )
    
    parser.add_argument(
        '--quiet',
        '-q',
        action='store_true',
        help='Suppress verbose output'
    )
    
    args = parser.parse_args()
    
    # Print banner
    if not args.quiet:
        print_banner()
    
    # Validate input file
    if not os.path.exists(args.input):
        print(f"Error: Input file not found: {args.input}")
        sys.exit(1)
    
    if not args.input.endswith('.sol'):
        print(f"Warning: Input file doesn't have .sol extension")
    
    # Print configuration
    if not args.quiet:
        print("CONFIGURATION:")
        print(f"  Input file:      {args.input}")
        print(f"  Output file:     {args.output}")
        print(f"  Mapping file:    {args.mapping or 'Not specified'}")
        print(f"  Hash algorithm:  {args.algorithm}")
        print(f"  Prefix:          {args.prefix}")
        print(f"  Hash length:     {args.length}")
        print(f"  Solc version:    {args.solc_version}")
        print(f"  Method:          AST parsing")
        print()
    
    # Start timing
    start_time = time.time()
    
    # Read input file
    if not args.quiet:
        print(f"Reading input file: {args.input}")
    
    source_code = read_file(args.input)
    original_size = len(source_code)
    
    if not args.quiet:
        print(f"  ✓ Read {original_size:,} characters")
        print()
    
    # Create renamer
    if not args.quiet:
        print("Initializing obfuscator (AST-based)...")
    
    try:
        renamer = VariableRenamer(
            hash_algorithm=args.algorithm,
            prefix=args.prefix,
            hash_length=args.length,
            solc_version=args.solc_version
        )
    except Exception as e:
        print(f"Error initializing renamer: {e}")
        sys.exit(1)
    
    if not args.quiet:
        print(f"  ✓ Protected {len(renamer.reserved_keywords)} Solidity keywords")
        print()
    
    # Obfuscate
    if not args.quiet:
        print("Obfuscating code using AST...")
        print()
    
    try:
        obfuscated_code = renamer.obfuscate(source_code, args.input)
    except Exception as e:
        print(f"Error during obfuscation: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    obfuscated_size = len(obfuscated_code)
    
    if not args.quiet:
        print()
        print(f"  ✓ Generated {obfuscated_size:,} characters")
        print()
    
    # Write output file
    if not args.quiet:
        print(f"Writing output file: {args.output}")
    
    write_file(args.output, obfuscated_code)
    
    if not args.quiet:
        print(f"  ✓ Obfuscated code saved")
        print()
    
    # Save mapping if requested
    if args.mapping:
        if not args.quiet:
            print(f"Saving mapping file: {args.mapping}")
        
        renamer.save_mapping(args.mapping)
        
        if not args.quiet:
            print(f"  ✓ Mapping saved")
            print()
    
    # End timing
    elapsed_time = time.time() - start_time
    
    # Print summary
    if not args.quiet:
        mapping = renamer.get_mapping()
        print_summary(original_size, obfuscated_size, len(mapping), elapsed_time)
        print_mapping_preview(mapping, max_items=15)
        
        print("\n✓ OBFUSCATION COMPLETED SUCCESSFULLY!\n")


# ============================================
# ENTRY POINT
# ============================================

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n✗ Interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)