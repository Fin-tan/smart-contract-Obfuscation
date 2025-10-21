// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;

contract HelloWorld {
    function sayHello() public pure returns (uint) {
        bool a = true;
        uint sum = 0;

        // ví dụ: đổi giá trị a dựa trên biểu thức XOR
        uint x = 1 ^ 1; // 1 XOR 1 = 0
        if (x == 1) {
            a = true;
        } else {
            a = false;
        }

        if (a) {
            sum = 2;
        }

        return sum; // kết quả sẽ là 0 (vì 1 ^ 1 = 0)
    }
}