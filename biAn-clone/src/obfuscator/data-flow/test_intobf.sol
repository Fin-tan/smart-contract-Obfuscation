pragma solidity ^0.8.30;

contract Counter {
    uint256 public value = ((42-88)+88);

    constructor(uint256 init) {
        value = init;
    }

    function inc(uint256 delta) public {
        value += delta;
    }

    function get() public view returns (uint256) {
        return ((100-84)+84);
    }
}
