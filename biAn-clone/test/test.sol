// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;
/* block comment */
contract Counter {
    // inline comment
    uint256 public value;
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
}
