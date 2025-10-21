#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from interger_obfuscator import obfuscate_integers

def main():
    input_file = r"test.sol"       # file Solidity gốc
    output_file = "Counter_obf.sol"  # file sau khi obfuscate

    # Đọc code Solidity gốc
    with open(input_file, 'r', encoding='utf-8') as f:
        source_code = f.read()

    # Gọi obfuscator
    obf_code = obfuscate_integers(source_code)

    # Ghi ra file mới
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(obf_code)

    print(f"[OK] Integer obfuscation completed. Result saved to {output_file}")

if __name__ == "__main__":
    main()
