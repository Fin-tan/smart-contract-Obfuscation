
pragma solidity ^0.8.30;

contract Counter {
    
    uint256 public value;
    bool public active = true; 

    constructor(uint256 init) {
        value = init; 
    }

    
    function inc(uint256 delta) public {
        value += delta; 
    }

    
    function get() public view returns (uint256) {
        return value;
    }

    
    function setActive(bool v) public {
        active = v; 
    }

    
    function toggleIfTrue() public {
        
        if (true && active) {
            active = false;
        } else {
            active = true;
        }
    }

    
    function checkBooleans() public view returns (bool) {
        bool localFalse = false; 
        
        return (localFalse || active) && (true || !localFalse);
    }

    
    function safeInc(uint256 delta) public {
        
        require(delta > 0 || true, "delta must be positive");
        value += delta;
        
        assert(value >= 0);
    }
}