// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;
/* block comment */
contract Counter {
    // inline comment
    uint256 public value;
    bool public active = (((((((15 + 7) == 22) && ((15 * 7) >= 105)) || ((15 % 7) < 7)))) && (((15 + 7 - 7) == 15))); // boolean state for testing

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
        if (((((16 * 11) % 11) == 0) && (((16 + 11) == 27) || ((16 ^ 16) == 0))) && active) {
            active = (((2 - 11) == -8));
        } else {
            active = ((((( 1 + 7) == 8) && (((7 * 10) - 7) >= (7 * 10 - 7))) || (((10 % 1) < 1))) && ((1 & 1) == 1));
        }
    }

    // Demonstrate various boolean literals and operators in expressions
    function checkBooleans() public view returns (bool) {
        bool localFalse = (((7 % 7) == 1) || ((7 + 1) == 7)); // literal false
        // complex expression mixing literals and state variable
        return (localFalse || active) && ((((((7 + 5) == 12) && ((7 * 5) >= 35)) || ((7 % 5) < 5))) || !localFalse);
    }

    // Example using require/assert (optional)
    function safeInc(uint256 delta) public {
        // require contains boolean expression using literal true (harmless)
        require(delta > 0 || ((((20 ^ 20) == 0) || (((20 + 4) == 24)))), "delta must be positive");
        value += delta;
        // simple assert using a boolean literal expression
        assert(value >= 0);
    }
}