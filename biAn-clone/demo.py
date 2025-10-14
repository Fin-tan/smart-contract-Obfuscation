#!/usr/bin/env python3
"""
BiAn Comment Remover Demo
Smart Contract Comment Obfuscation Demo
"""

import os
import sys

# Add the src directory to Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.join(current_dir, 'src', 'obfuscator', 'layout')
sys.path.append(src_dir)

# Import the comment obfuscator
from comment_remover import CommentObfuscator, run_comment_obfuscation, show_comparison

if __name__ == "__main__":
    # Run the complete demo
    run_comment_obfuscation()
    show_comparison()
    
    print("\n" + "=" * 80)
    print("DEMO COMPLETED")
    print("=" * 80)
