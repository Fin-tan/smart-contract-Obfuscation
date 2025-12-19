"""
Chaotic Map Generator for BiAn-style Opaque Predicates.
Generates Solidity code for the chaotic map function (CPM) and helper state variables.
"""

import random

class ChaoticMapGenerator:
    def __init__(self):
        self.state_var_name = f"cpm_x_{random.randint(1000, 9999)}"
        self.helper_func_name = f"calculateCPM_{random.randint(1000, 9999)}"
        self.initial_value = random.randint(12345, 99999)
        # Randomly select a strategy for diversity
        self.variant = random.choice(['positive', 'negative', 'even'])

    def get_state_variable_declaration(self) -> str:
        """Returns the Solidity declaration for the state variable used by CPM."""
        return f"    int256 private {self.state_var_name} = int256({self.initial_value});"

    def get_helper_function_code(self) -> str:
        """Returns the Solidity code for the CPM helper function based on variant."""
        if self.variant == 'positive':
            # Range [20, 119] -> Always > 10
            # Explicit casts to handle StaticDataObfuscator transforming literals to uint
            return f"""
    function {self.helper_func_name}(int256 val) internal pure returns (int256) {{
        // BiAn Chaotic Map (CPM) - Positive Variant
        return int256(uint256(keccak256(abi.encodePacked(val)))) % int256(100) + int256(20);
    }}"""
        elif self.variant == 'negative':
            # Range [-150, -51] -> Always < -10
            return f"""
    function {self.helper_func_name}(int256 val) internal pure returns (int256) {{
        // BiAn Chaotic Map (CPM) - Negative Variant
        return (int256(uint256(keccak256(abi.encodePacked(val)))) % int256(100)) - int256(150);
    }}"""
        else: # 'even'
            # Returns an even number: (x % 50) * 2
            return f"""
    function {self.helper_func_name}(int256 val) internal pure returns (int256) {{
        // BiAn Chaotic Map (CPM) - Even Variant
        return (int256(uint256(keccak256(abi.encodePacked(val)))) % int256(50)) * int256(2);
    }}"""

    def get_predicate_condition(self) -> str:
        """Returns the condition string that evaluates to True."""
        if self.variant == 'positive':
            return f"({self.helper_func_name}({self.state_var_name}) > int256(10))"
        elif self.variant == 'negative':
            return f"({self.helper_func_name}({self.state_var_name}) < -int256(10))"
        else: # 'even'
            return f"({self.helper_func_name}({self.state_var_name}) % int256(2) == int256(0))"
