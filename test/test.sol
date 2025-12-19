// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;

contract HelloWorld {
    address public owner;

    constructor() {
        owner = msg.sender;
    }

    // BiAn sẽ phải "bung" cái require này và nhét vào hàm compute bên dưới.
    modifier onlyOwner() {
        require(msg.sender == owner, "Not owner");
        _;
    }

    // BiAn sẽ copy logic (val * 2 + 3) và dán thẳng vào chỗ gọi.
    function _calculateInternal(uint256 val) internal pure returns (uint256) {
        return val * 2 + 3;
    }

    function sayHello() public pure returns (uint) {
        bool a = true;
        uint sum = 0;

        uint x = 1 ^ 1; 
        if (x == 1) {
            a = true;
        } else {
            a = false;
        }

        if (a) {
            sum = 2;
        }

        return sum; 
    }

    uint256 private storedValue; 

    // Thêm modifier và gọi hàm nội bộ
    function compute(uint256 a) public onlyOwner {
        // Thay vì viết công thức trực tiếp, ta gọi hàm nội bộ
        uint256 tmp = _calculateInternal(a); 
        
        storedValue = tmp; 
    }

    function getStoredValue() public view returns (uint256) {
        return storedValue;
    }
}