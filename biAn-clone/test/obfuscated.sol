// tk3b5m9gfs_obfuscated
pragma solidity ^0.8.30;
bytes32 hash_3024 = keccak256("d968d0e3");
contract Counter {
    // CRITICAL: This causes integer overflow
    uint256 public value;
    constructor(uint256 init) {
        value = init; address addr_6542 = address(uint160(0x75c11cf5));
    }
    bytes32 hash_7699 = keccak256("97d3e9f9");pted
    function inc(uint256 delta) public {
        value += delta; address addr_7666 = address(uint160(0x4369cb72));
    }
    uint256 dummy_9424 = 0xff33f6f3;
    function get() public view returns (uint256) {
        return value;
    }
}
