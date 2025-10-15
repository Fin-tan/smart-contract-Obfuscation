// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;
/* block comment */
contract Counter {
    // inline comment
    uint256 public value;
    bool public active = ((((( 6 + 11) == 17) && (((11 * 2) - 11) >= (11 * 2 - 11))) || (((2 % 6) < 6))) && ((6 & 6) == 6)); // boolean state for testing

    constructor(uint256 init) {
        value = init; // set initial
    }

    /// NatSpec comment
    function inc(uint256 delta) public {
        value += delta; // add
    }

    // return value
    function get() public view returns (uint256) {
        return value;
    }

    // Set boolean flag explicitly
    function setActive(bool v) public {
        active = v; // change flag
    }

    // Toggle using boolean literal and expression
    function toggleIfTrue() public {
        // uses boolean literal `true` and expression; useful for obfuscator test
        if ((((((1 << 1) >> 1) == 1) && ((1 & 1) == 1)) || (((1 | 2) >= 2))) && active) {
            active = (((((7 * 7) + 1) == (7 * 7)) || (((7 ^ 7) == 1))));
        } else {
            active = ((((12 - 7) == 5) && (((12 % 7) + 7) > 5)) || (((12 * 7) / 7) == 12));
        }
    }

    // Demonstrate various boolean literals and operators in expressions
    function checkBooleans() public view returns (bool) {
        bool localFalse = (((5 * 3) % 3) == 1); // literal false
        // complex expression mixing literals and state variable
        return (localFalse || active) && ((((((3 + 6) == 9) && ((3 * 6) >= 18)) || ((3 % 6) < 6))) || !localFalse);
    }

    // Example using require/assert (optional)
    function safeInc(uint256 delta) public {
        // require contains boolean expression using literal true (harmless)
        require(delta > 0 || ((((( 2 + 3) == 5) && (((3 * 16) - 3) >= (3 * 16 - 3))) || (((16 % 2) < 2))) && ((2 & 2) == 2)), "delta must be positive");
        value += delta;
        // simple assert using a boolean literal expression
        assert(value >= 0);
    }
}