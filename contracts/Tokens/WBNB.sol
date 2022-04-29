// SPDX-License-Identifier: BUSL-1.1

pragma solidity ^0.8.0;

import "@openzeppelin/contracts/utils/Address.sol";
import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

/**
 * @author Heisenberg
 * @title Buffer WBNB Token
 * @notice The central token to the Buffer ecosystem
 */
contract WBNB is ERC20("WBNB", "WBNB") {
    constructor() {
        uint256 INITIAL_SUPPLY = 100 * 10**6 * 10**decimals();
        _mint(msg.sender, INITIAL_SUPPLY);
    }
}
