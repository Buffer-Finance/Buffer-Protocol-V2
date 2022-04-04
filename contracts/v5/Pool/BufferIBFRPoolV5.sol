pragma solidity ^0.8.0;

/**
 * SPDX-License-Identifier: GPL-3.0-or-later
 * Buffer
 * Copyright (C) 2020 Buffer Protocol
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <http://www.gnu.org/licenses/>.
 */

import "../../Interfaces/InterfacesV5.sol";
import "@openzeppelin/contracts/access/AccessControl.sol";
import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

/**
 * @author Heisenberg
 * @title Buffer TokenX Liquidity Pool
 * @notice Accumulates liquidity in TokenX from LPs and distributes P&L in TokenX
 */
contract BufferIBFRPoolV5 is
    ERC20("Buffer LP Token", "rBFR"),
    AccessControl,
    ILiquidityPoolV5
{
    string private _name;
    string private _symbol;
    uint256 public constant ACCURACY = 1e3;
    uint256 public constant INITIAL_RATE = 1e3;
    uint256 public lockupPeriod = 2 weeks;
    uint256 public lockedAmount;
    uint256 public lockedPremium;
    uint256 public maxLiquidity = 200e18;
    uint256 public requestCount = 0;
    uint256 public fixedExpiry;

    mapping(address => bool) public _revertTransfersInLockUpPeriod;
    mapping(address => LockedLiquidity[]) public lockedLiquidity;

    bytes32 public constant OPTION_ISSUER_ROLE =
        keccak256("OPTION_ISSUER_ROLE");

    ERC20 public immutable tokenX;
    event UpdateMaxLiquidity(uint256 indexed maxLiquidity);
    event UpdateExpiry(uint256 expiry);

    struct WithdrawRequest {
        uint256 withdraw_amount;
        address account;
    }

    WithdrawRequest[] public WithdrawRequestQueue;
    event AddedWithdrawRequest(uint256 tokenXAmount, address account);

    constructor(ERC20 _tokenX, uint256 initialExpiry) {
        _name = string(
            bytes.concat(
                "Buffer Generic ",
                bytes(_tokenX.symbol()),
                " LP Token"
            )
        );
        _symbol = string(bytes.concat("r", bytes(_tokenX.symbol())));
        tokenX = _tokenX;
        fixedExpiry = initialExpiry;

        _setupRole(DEFAULT_ADMIN_ROLE, msg.sender);
    }

    /**
     * @dev Returns the name of the token.
     */
    function name() public view virtual override returns (string memory) {
        return _name;
    }

    /**
     * @dev Returns the symbol of the token, usually a shorter version of the
     * name.
     */
    function symbol() public view virtual override returns (string memory) {
        return _symbol;
    }

    /**
     * @notice Used for changing expiry
     * @param value New fixedExpiry value
     */
    function setExpiry(uint256 value) external {
        require(
            hasRole(DEFAULT_ADMIN_ROLE, msg.sender),
            "msg.sender is not allowed to set expiry"
        );
        require(
            block.timestamp > fixedExpiry,
            "Can't change expiry before the expiry ends"
        );
        fixedExpiry = value;
        emit UpdateExpiry(value);
    }

    function getExpiry() external view override returns (uint256) {
        return fixedExpiry;
    }

    function getLockedAmount() external view override returns (uint256) {
        return lockedAmount;
    }

    /**

     * @notice Used for resetting the request queue
     */
    function resetWithdrawRequestQueue() external {
        require(
            hasRole(DEFAULT_ADMIN_ROLE, msg.sender),
            "msg.sender is not allowed to reset"
        );
        require(
            block.timestamp > fixedExpiry,
            "Can't change expiry before the expiry ends"
        );
        delete WithdrawRequestQueue;
        requestCount = 0;
    }

    /**
     * @notice Used for adjusting the max limit of the pool
     * @param _maxLiquidity New limit
     */
    function setMaxLiquidity(uint256 _maxLiquidity) external {
        require(
            hasRole(DEFAULT_ADMIN_ROLE, msg.sender),
            "msg.sender is not allowed to adjust the limit"
        );
        maxLiquidity = _maxLiquidity;
        emit UpdateMaxLiquidity(_maxLiquidity);
    }

    /*
     * @nonce A provider supplies tokenX to the pool and receives rBFR-X tokens
     * @param minMint Minimum amount of tokens that should be received by a provider.
                      Calling the provide function will require the minimum amount of tokens to be minted.
                      The actual amount that will be minted could vary but can only be higher (not lower) than the minimum value.
     * @return mint Amount of tokens to be received
     */
    function provide(uint256 tokenXAmount, uint256 minMint)
        external
        returns (uint256 mint)
    {
        uint256 supply = totalSupply();

        uint256 balance = totalTokenXBalance();
        require(
            balance + tokenXAmount <= maxLiquidity,
            "Pool has already reached it's max limit"
        );

        if (supply > 0 && balance > 0)
            mint = (tokenXAmount * supply) / (balance);
        else mint = tokenXAmount * INITIAL_RATE;

        require(mint >= minMint, "Pool: Mint limit is too large");
        require(mint > 0, "Pool: Amount is too small");

        bool success = tokenX.transferFrom(
            msg.sender,
            address(this),
            tokenXAmount
        );
        require(success, "The Provide transfer didn't go through");

        _mint(msg.sender, mint);

        emit Provide(msg.sender, tokenXAmount, mint);
    }

    /*
     * @nonce Provider burns rBFR-X and receives X from the pool
     * @param amount Amount of X to receive
     * @return burn Amount of tokens to be burnt
     */
    function withdraw(uint256 tokenXAmount, address account)
        public
        returns (uint256 burn)
    {
        if (block.timestamp <= fixedExpiry) {
            WithdrawRequestQueue.push(WithdrawRequest(tokenXAmount, account));
            requestCount++;
            emit AddedWithdrawRequest(tokenXAmount, account);
            return 0;
        }

        require(
            tokenXAmount <= availableBalance(),
            "Pool Error: Not enough funds on the pool contract. Please lower the amount."
        );

        burn = divCeil((tokenXAmount * totalSupply()), totalTokenXBalance());

        require(burn <= balanceOf(account), "Pool: Amount is too large");
        require(burn > 0, "Pool: Amount is too small");

        _burn(account, burn);
        emit Withdraw(account, tokenXAmount, burn);

        bool success = tokenX.transfer(account, tokenXAmount);
        require(success, "The Withdrawal didn't go through");
    }

    /*
     * @nonce Provider burns rBFR-X and receives X from the pool
     * @param amount Amount of X to receive
     * @return burn Amount of tokens to be burnt
     */
    function processWithdrawRequests(uint256 requestIndex) external {
        require(
            block.timestamp > fixedExpiry,
            "Withdraw requests can't be processed before expiry"
        );
        WithdrawRequest storage withdrawRequest = WithdrawRequestQueue[
            requestIndex
        ];
        withdraw(withdrawRequest.withdraw_amount, withdrawRequest.account);
        delete WithdrawRequestQueue[requestIndex];
        requestCount--;
    }

    /*
     * @nonce calls by BufferCallOptions to lock the funds
     * @param tokenXAmount Amount of funds that should be locked in an option
     */
    function lock(
        uint256 id,
        uint256 tokenXAmount,
        uint256 premium
    ) external override {
        require(
            hasRole(OPTION_ISSUER_ROLE, msg.sender),
            "msg.sender is not allowed to excute the option contract"
        );
        require(id == lockedLiquidity[msg.sender].length, "Wrong id");
        require(totalTokenXBalance() >= tokenXAmount, "Insufficient balance");

        require(
            (lockedAmount + tokenXAmount) <= (totalTokenXBalance() * 8) / 10,
            "Pool Error: Amount is too large."
        );

        bool success = tokenX.transferFrom(msg.sender, address(this), premium);
        require(success, "The Premium transfer didn't go through");

        lockedLiquidity[msg.sender].push(
            LockedLiquidity(tokenXAmount, premium, true)
        );
        lockedPremium = lockedPremium + premium;
        lockedAmount = lockedAmount + tokenXAmount;
    }

    /*
     * @nonce calls by BufferCallOptions to lock the funds
     * @param tokenXAmount Amount of funds that should be locked in an option
     */
    function lockChange(
        uint256 id,
        uint256 tokenXAmount,
        uint256 premium
    ) public override {
        require(
            hasRole(OPTION_ISSUER_ROLE, msg.sender),
            "msg.sender is not allowed to excute the option contract"
        );
        LockedLiquidity storage ll = lockedLiquidity[msg.sender][id];
        require(ll.locked, "LockedLiquidity with such id has already unlocked");
        if (ll.premium > premium) {
            tokenX.transfer(msg.sender, ll.premium - premium);
        }
        ll.premium = premium;
        ll.amount = tokenXAmount;
        lockedPremium = lockedPremium - ll.premium + premium;
        lockedAmount = lockedAmount - ll.amount + tokenXAmount;
    }

    /*
     * @nonce calls by BufferOptions to unlock the funds
     * @param id Id of LockedLiquidity that should be unlocked
     */
    function _unlock(uint256 id) internal returns (uint256 premium) {
        require(
            hasRole(OPTION_ISSUER_ROLE, msg.sender),
            "msg.sender is not allowed to excute the option contract"
        );
        LockedLiquidity storage ll = lockedLiquidity[msg.sender][id];
        require(ll.locked, "LockedLiquidity with such id has already unlocked");
        ll.locked = false;

        lockedPremium = lockedPremium - ll.premium;
        lockedAmount = lockedAmount - ll.amount;
        premium = ll.premium;
    }

    /*
     * @nonce calls by BufferOptions to unlock the funds
     * @param id Id of LockedLiquidity that should be unlocked
     */
    function unlock(uint256 id) external override {
        uint256 premium = _unlock(id);

        emit Profit(id, premium);
    }

    /*
     * @nonce calls by BufferOptions to unlock the funds
     * @param id Id of LockedLiquidity that should be unlocked
     */
    function unlockWithoutProfit(uint256 id) external {
        _unlock(id);
    }

    /*
     * @nonce calls by BufferCallOptions to send funds to liquidity providers after an option's expiration
     * @param to Provider
     * @param tokenXAmount Funds that should be sent
     */
    function send(
        uint256 id,
        address to,
        uint256 tokenXAmount
    ) external override {
        require(
            hasRole(OPTION_ISSUER_ROLE, msg.sender),
            "msg.sender is not allowed to excute the option contract"
        );
        LockedLiquidity storage ll = lockedLiquidity[msg.sender][id];
        require(ll.locked, "LockedLiquidity with such id has already unlocked");
        require(to != address(0));

        ll.locked = false;
        lockedPremium = lockedPremium - ll.premium;
        lockedAmount = lockedAmount - ll.amount;

        uint256 transferTokenXAmount = tokenXAmount > ll.amount
            ? ll.amount
            : tokenXAmount;

        bool success = tokenX.transfer(to, transferTokenXAmount);
        require(success, "The Payout transfer didn't go through");

        if (transferTokenXAmount <= ll.premium)
            emit Profit(id, ll.premium - transferTokenXAmount);
        else emit Loss(id, transferTokenXAmount - ll.premium);
    }

    /*
     * @nonce Returns provider's share in X
     * @param account Provider's address
     * @return Provider's share in X
     */
    function shareOf(address account) external view returns (uint256 share) {
        if (totalSupply() > 0)
            share = (totalTokenXBalance() * balanceOf(account)) / totalSupply();
        else share = 0;
    }

    /*
     * @nonce Returns the amount of X available for withdrawals
     * @return balance Unlocked amount
     */
    function availableBalance() public view returns (uint256 balance) {
        return totalTokenXBalance() - lockedAmount;
    }

    /*
     * @nonce Returns the total balance of X provided to the pool
     * @return balance Pool balance
     */
    function totalTokenXBalance()
        public
        view
        override
        returns (uint256 balance)
    {
        return tokenX.balanceOf(address(this)) - lockedPremium;
    }

    function divCeil(uint256 a, uint256 b) internal pure returns (uint256) {
        require(b > 0);
        uint256 c = a / b;
        if (a % b != 0) c = c + 1;
        return c;
    }
}
