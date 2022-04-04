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

import "./OptionsCore.sol";

/**
 * @author Heisenberg
 * @title Buffer TokenX Bidirectional (Call and Put) Options
 * @notice Buffer TokenX Options Contract
 */
contract BufferTokenXOptionsV5Test is OptionsCore {
    address public token0;
    address public token1;
    ISlidingWindowOracle public twap;
    ERC20 public immutable tokenX;
    mapping(uint256 => string) private _tokenURIs;

    OptionType public fixedOptionType = OptionType.Call;

    constructor(
        ERC20 _tokenX,
        BufferIBFRPoolV5 _pool,
        address _token0,
        address _token1,
        ISlidingWindowOracle _twap,
        OptionConfig _config
    ) ERC721("Buffer", "BFR") {
        tokenX = _tokenX;
        pool = _pool;
        contractCreationTimestamp = block.timestamp;
        token0 = _token0;
        token1 = _token1;
        twap = _twap;
        config = _config;
        _setupRole(DEFAULT_ADMIN_ROLE, msg.sender);
    }

    /**
     * @notice Used for getting the tokenX's price
     */
    function getCurrentPrice() public view returns (uint256 _price) {
        _price = 40000000000;
    }

    // function setMaxUnits(uint256 value) external onlyOwner {
    //     maxUnits = value;
    //     emit UpdateUnits(value);
    // }

    /**
     * @notice Creates a new option
     * @param amount Option amount in tokenX
     * @return optionID Created option's ID
     */
    function create(
        uint256 amount,
        address referrer,
        string memory metadata
    ) external nonReentrant returns (uint256 optionID) {
        require(
            pool.getExpiry() > block.timestamp,
            "Option creation is not allowed currently"
        );
        uint256 period = pool.getExpiry() - block.timestamp;
        (uint256 totalFee, uint256 settlementFee, uint256 premium) = fees(
            period,
            amount,
            config.fixedStrike(),
            fixedOptionType
        );

        require(totalFee > amount / 1000, "The option's price is too low");

        // User has to approve first inorder to execute this function
        bool success = tokenX.transferFrom(msg.sender, address(this), totalFee);
        require(success, "The Fee Transfer didn't go through");

        uint256 lockedAmount = (amount *
            config.optionCollateralizationRatio()) / 100;

        Option memory option = Option(
            State.Active,
            config.fixedStrike(),
            amount,
            lockedAmount,
            premium,
            block.timestamp + period,
            fixedOptionType
        );
        optionID = _generateTokenId();
        _setOption(optionID, option);
        _setOptionBlock(optionID);
        createOptionFor(msg.sender, metadata, optionID);
        uint256 stakingAmount = distributeSettlementFee(
            settlementFee,
            referrer
        );

        tokenX.approve(address(pool), option.premium);
        pool.lock(optionID, option.lockedAmount, option.premium);

        // Set User's Auto Close Status to True by default
        // Check if this is the user's first option from this contract
        if (!hasUserBoughtFirstOption[msg.sender]) {
            // if yes then set the auto close for the user to True
            if (!autoExerciseStatus[msg.sender]) {
                autoExerciseStatus[msg.sender] = true;
                emit AutoExerciseStatusChange(msg.sender, true);
            }
            hasUserBoughtFirstOption[msg.sender] = true;
        }

        emit Create(optionID, msg.sender, stakingAmount, totalFee, metadata);
    }

    function approve_token(address receipent, uint256 amount) public override {
        tokenX.approve(receipent, amount);
    }

    // /**
    //  * @notice Unlock funds locked in the expired options
    //  * @param optionID ID of the option
    //  */
    function unlock(uint256 optionID) public override {
        Option storage option = options[optionID];
        require(
            option.expiration < block.timestamp,
            "Option has not expired yet"
        );
        require(option.state == State.Active, "Option is not active");
        option.state = State.Expired;
        pool.unlock(optionID);

        // Burn the option
        _burn(optionID);

        emit Expire(optionID, option.premium);
    }

    /**
     * @notice Sends profits in TokenX from the TokenX pool to an option holder's address
     * @param optionID A specific option contract id
     */
    function payProfit(uint256 optionID)
        internal
        override
        returns (uint256 profit)
    {
        Option memory option = options[optionID];
        uint256 currentPrice = getCurrentPrice();
        if (option.optionType == OptionType.Call) {
            require(option.strike <= currentPrice, "Current price is too low");
            profit =
                ((currentPrice - option.strike) * option.amount) /
                currentPrice;
        } else {
            require(option.strike >= currentPrice, "Current price is too high");
            profit =
                ((option.strike - currentPrice) * option.amount) /
                currentPrice;
        }
        if (profit > option.lockedAmount) profit = option.lockedAmount;
        pool.send(optionID, ownerOf(optionID), profit);
    }

    function distributeSettlementFee(uint256 settlementFee, address referrer)
        internal
        override
        returns (uint256 stakingAmount)
    {
        stakingAmount = ((settlementFee * config.stakingFeePercentage()) / 100);

        // Incase the stakingAmount is 0
        if (stakingAmount > 0) {
            tokenX.transfer(config.settlementFeeRecipient(), stakingAmount);
        }

        uint256 adminFee = settlementFee - stakingAmount;

        if (adminFee > 0) {
            if (
                config.referralRewardPercentage() > 0 &&
                referrer != owner() &&
                referrer != msg.sender
            ) {
                uint256 referralReward = (adminFee *
                    config.referralRewardPercentage()) / 100;
                adminFee = adminFee - referralReward;
                tokenX.transfer(referrer, referralReward);
                emit PayReferralFee(referrer, referralReward);
            }
            tokenX.transfer(owner(), adminFee);
            emit PayAdminFee(owner(), adminFee);
        }
    }

    function getNewUtilisation(uint256 amount)
        public
        view
        returns (uint256 utilization)
    {
        uint256 poolBalance = pool.totalTokenXBalance();
        require(poolBalance > 0, "Pool Error: The pool is empty");

        uint256 lockedAmount = pool.getLockedAmount() + amount;
        utilization = (lockedAmount * 100e8) / poolBalance;
    }

    function currentImpliedVolatility(uint256 amount)
        public
        view
        returns (uint256 iv)
    {
        iv = config.impliedVolRate();
        uint256 utilization = getNewUtilisation(amount);
        if (utilization > 40e8) {
            iv +=
                (iv * (utilization - 40e8) * config.utilizationRate()) /
                40e16;
        }
    }

    /**
     * @notice Used for getting the actual options prices
     * @param period Option period in seconds (1 days <= period <= 4 weeks)
     * @param amount Option amount
     * @param strike Strike price of the option
     * @return total Total price to be paid
     * @return settlementFee Amount to be distributed to the Buffer token holders
     * @return premium Amount that covers the price difference in the ITM options
     */
    function fees(
        uint256 period,
        uint256 amount,
        uint256 strike,
        OptionType optionType
    )
        public
        view
        override
        returns (
            uint256 total,
            uint256 settlementFee,
            uint256 premium
        )
    {
        uint256 currentPrice = getCurrentPrice();

        // usdPremium is USD Price of the option in 1e8
        uint256 usdPremiumPerAmount = OptionMath.blackScholesPrice(
            currentImpliedVolatility(amount),
            strike,
            currentPrice,
            period,
            optionType == OptionType.Call
        );
        premium = (usdPremiumPerAmount * amount) / currentPrice;
        settlementFee = getSettlementFee(amount);
        total = settlementFee + premium;
    }

    // /**
    //  * @notice Used for getting the actual options prices
    //  * @param amount Option amount
    //  * @return _breakEvenPrice The price of the asset to break even
    //  */
    // function breakEvenPrice(uint256 amount)
    //     public
    //     view
    //     returns (uint256 _breakEvenPrice)
    // {
    //     uint256 currentPrice = getCurrentPrice();
    //     (uint256 _fee, , ) = fees(
    //         pool.getExpiry() - block.timestamp,
    //         amount,
    //         config.fixedStrike(),
    //         OptionType.Call
    //     );
    //     _breakEvenPrice = config.fixedStrike() + (_fee * currentPrice) / amount;
    // }

    /**
     * @dev See EIP-165: ERC-165 Standard Interface Detection
     * https://eips.ethereum.org/EIPS/eip-165
     **/
    function createOptionFor(
        address holder,
        string memory metadata,
        uint256 optionID
    ) internal {
        uint256 slot = BufferNFTCore.createSlot(optionID);
        _mint(optionID, holder, slot);
        _setTokenURI(optionID, metadata);
    }

    function _mint(
        uint256 optionID,
        address minter_,
        uint256 slot_
    ) internal virtual override {
        BufferNFTCore._mint(optionID, minter_, slot_);
    }

    function burn(uint256 optionID) external virtual {
        require(_msgSender() == ownerOf(optionID), "only owner");
        _burnToken(optionID);
    }

    function _burnToken(uint256 optionID) internal virtual {
        delete optionSlotMapping[optionID];
        ERC721._burn(optionID);
    }

    function _generateTokenId() internal virtual override returns (uint256) {
        return nextTokenId++;
    }

    function _getOption(uint256 optionID)
        internal
        view
        virtual
        override
        returns (Option memory)
    {
        return options[optionID];
    }

    function _setOption(uint256 optionID, Option memory option)
        internal
        virtual
        override
    {
        options[optionID] = option;
    }

    function _setOptionBlock(uint256 optionID) internal virtual override {
        optionBlocks[optionID] = block.number;
    }
}
