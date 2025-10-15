// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;
/* block comment */
contract Counter {
    // inline comment
    uint256 public value;
    bool public active = (true || (1 == 0)); // boolean state for testing

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
        if ((true || (1 == 0)) && active) {
            active = (false || (1 == 0));
        } else {
            active = (true || (1 == 0));
        }
    }

    // Demonstrate various boolean literals and operators in expressions
    function checkBooleans() public view returns (bool) {
        bool localFalse = (false && (1 == 1)); // literal false
        // complex expression mixing literals and state variable
        return (localFalse || active) && ((true || (1 == 0)) || !localFalse);
    }

    // Example using require/assert (optional)
    function safeInc(uint256 delta) public {
        // require contains boolean expression using literal true (harmless)
        require(delta > 0 || (true && (1 == 1)), "delta must be positive");
        value += delta;
        // simple assert using a boolean literal expression
        assert(value >= 0);
    }
}