#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
demo.py
- Đọc một file .sol (đã/không có comment)
- Chạy integer obfuscator (preserve pragma/SPDX, do NOT preserve comments)
- Ghi ra file output (mặc định: <input>_intobf.sol) hoặc overwrite nếu --overwrite
Usage:
    python demo.py input.sol [output.sol] [--overwrite]
"""

import os
import sys
import argparse
import traceback

# Import hàm obfuscator; tên hàm trong module là obfuscate_integers_preserve_pragma
try:
    from interger_obfuscator import obfuscate_integers_preserve_pragma as obfuscate_integers
except Exception as e:
    print("[ERROR] Không thể import integer_obfuscator. Kiểm tra file integer_obfuscator.py nằm cùng thư mục.")
    print("Import error:", e)
    traceback.print_exc()
    sys.exit(1)


def run_once(input_path: str, output_path: str, overwrite: bool = False) -> None:
    input_abs = os.path.abspath(input_path)
    if not os.path.isfile(input_abs):
        print(f"[ERROR] Input file không tồn tại: {input_abs}")
        return

    # chuẩn hoá đường dẫn output
    output_abs = os.path.abspath(output_path) if output_path else (os.path.splitext(input_abs)[0] + "_intobf.sol")
    if overwrite:
        output_abs = input_abs

    print(f"[INFO] Đọc: {input_abs}")
    try:
        with open(input_abs, 'r', encoding='utf-8') as f:
            src = f.read()
    except Exception as e:
        print(f"[ERROR] Lỗi khi đọc file: {e}")
        return

    print(f"[INFO] Kích thước input: {len(src)} ký tự. Bắt đầu obfuscation integer...")
    try:
        out = obfuscate_integers(src)
    except Exception as e:
        print(f"[ERROR] Hàm obfuscate_integers phát sinh exception: {e}")
        traceback.print_exc()
        return

    try:
        with open(output_abs, 'w', encoding='utf-8') as f:
            f.write(out)
    except Exception as e:
        print(f"[ERROR] Lỗi khi ghi file output: {e}")
        traceback.print_exc()
        return

    print(f"[OK] Hoàn tất. Ghi ra: {output_abs}")
    print(f"[INFO] Kích thước output: {len(out)} ký tự")
    # show small preview
    print("\n--- preview (200 chars) ---")
    print(out[:200])
    print("--- end preview ---\n")


def main():
    p = argparse.ArgumentParser(description="Demo integer obfuscation (preserve pragma/SPDX, do not protect comments)")
    p.add_argument("input", help="Input Solidity file (.sol)")
    p.add_argument("output", nargs="?", default=None, help="Output file path (default: <input>_intobf.sol)")
    p.add_argument("--overwrite", action="store_true", help="Ghi đè lên file input (không khuyến nghị nếu chưa backup)")
    args = p.parse_args()

    run_once(args.input, args.output, args.overwrite)


if __name__ == "__main__":
    main()
