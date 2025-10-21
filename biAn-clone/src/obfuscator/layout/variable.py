import sys
import os
from pathlib import Path
import solcx
import json
from solcx import compile_source, compile_files,set_solc_version
class SolconverAst:
    def __init__(self,solc_version: str='0.8.30'):
        self.solc_version=solc_version

    def compile_to_ast(self,file_path: str=None) -> dict:
        try:
            if file_path and os.path.exists(file_path):
                compiled=compile_files(
                    [file_path],
                    output_values=['ast'],
                    solc_version=self.solc_version
                )
                print(compiled)
                contract_name=list(compiled.keys())[0]
                ast=compiled[contract_name]['ast']
                print(ast.keys())
        except Exception as e: 
            print (f"sai:{e}")
            return None
        
        if file_path:
            ast_ouput_path=os.path.splitext(file_path)[0]+'_ast.json'
        
        with open(ast_ouput_path,'w') as f:
            json.dump(ast,f,indent=2)
        return ast
if __name__== "__main__":
    vd=SolconverAst('0.8.30')
    ast=vd.compile_to_ast("test.sol")



