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

import "@openzeppelin/contracts/access/Ownable.sol";
import "../../Interfaces/InterfacesV5.sol";

/**
 * @author Heisenberg
 * @title Buffer BNB Bidirectional (Call and Put) Options
 * @notice Buffer BNB Options Contract
 */
contract OptionConfig is Ownable, IOptionsConfig {
    uint256 public impliedVolRate;
    uint256 public optionCollateralizationRatio = 100;
    uint256 public settlementFeePercentage = 1;
    uint256 public stakingFeePercentage = 50;
    uint256 public referralRewardPercentage = 25;
    uint256 public nftSaleRoyaltyPercentage = 5;
    uint256 internal constant PRICE_DECIMALS = 1e8;
    address public settlementFeeRecipient;
    uint256 public utilizationRate = 4 * 10**7;
    uint256 public fixedStrike;
    ILiquidityPoolV5 public pool;
    PermittedTradingType public permittedTradingType;

    constructor(
        address staking,
        uint256 initialImpliedVolRate,
        uint256 initialStrike,
        ILiquidityPoolV5 _pool
    ) {
        settlementFeeRecipient = staking;
        fixedStrike = initialStrike;
        impliedVolRate = initialImpliedVolRate;
        pool = _pool;
    }

    /**
     * @notice Check the validity of the input params
     * @param optionType Call or Put option type
     * @param period Option period in seconds (1 days <= period <= 90 days)
     * @param amount Option amount
     * @param strikeFee strike fee for the option
     * @param totalFee total fee for the option
     * @param msgValue the msg.value given to the Create function
     */
    function checkParams(
        IBufferOptionsV5.OptionType optionType,
        uint256 period,
        uint256 amount,
        uint256 strikeFee,
        uint256 totalFee,
        uint256 msgValue
    ) external pure {
        require(
            optionType == IBufferOptionsV5.OptionType.Call ||
                optionType == IBufferOptionsV5.OptionType.Put,
            "Wrong option type"
        );
        require(period >= 1 days, "Period is too short");
        require(period <= 90 days, "Period is too long");
        require(amount > strikeFee, "Price difference is too large");
        require(msgValue >= totalFee, "Wrong value");
    }

    /**
     * @notice Used for adjusting the options prices while balancing asset's implied volatility rate
     * @param value New IVRate value
     */
    function setImpliedVolRate(uint256 value) external onlyOwner {
        require(value >= 100, "ImpliedVolRate limit is too small");
        impliedVolRate = value;
        emit UpdateImpliedVolatility(value);
    }

    function setTradingPermission(PermittedTradingType permissionType)
        external
        onlyOwner
    {
        permittedTradingType = permissionType;
        emit UpdateTradingPermission(permissionType);
    }

    /**
     * @notice Used for changing strike
     * @param value New fixedStrike value
     */
    function setStrike(uint256 value) external onlyOwner {
        require(
            block.timestamp > pool.getExpiry(),
            "Can't change strike before the expiry ends"
        );
        fixedStrike = value;
        emit UpdateStrike(value);
    }

    /**
     * @notice Used for adjusting the settlement fee percentage
     * @param value New Settlement Fee Percentage
     */
    function setSettlementFeePercentage(uint256 value) external onlyOwner {
        require(value < 20, "SettlementFeePercentage is too high");
        settlementFeePercentage = value;
        emit UpdateSettlementFeePercentage(value);
    }

    /**
     * @notice Used for changing settlementFeeRecipient
     * @param recipient New settlementFee recipient address
     */
    function setSettlementFeeRecipient(address recipient) external onlyOwner {
        require(address(recipient) != address(0));
        settlementFeeRecipient = recipient;
        emit UpdateSettlementFeeRecipient(address(recipient));
    }

    /**
     * @notice Used for adjusting the staking fee percentage
     * @param value New Staking Fee Percentage
     */
    function setStakingFeePercentage(uint256 value) external onlyOwner {
        require(value <= 100, "StakingFeePercentage is too high");
        stakingFeePercentage = value;
        emit UpdateStakingFeePercentage(value);
    }

    /**
     * @notice Used for adjusting the referral reward percentage
     * @param value New Referral Reward Percentage
     */
    function setReferralRewardPercentage(uint256 value) external onlyOwner {
        require(value <= 100, "ReferralRewardPercentage is too high");
        referralRewardPercentage = value;
        emit UpdateReferralRewardPercentage(value);
    }

    /**
     * @notice Used for changing option collateralization ratio
     * @param value New optionCollateralizationRatio value
     */
    function setOptionCollaterizationRatio(uint256 value) external onlyOwner {
        require(50 <= value && value <= 100, "wrong value");
        optionCollateralizationRatio = value;
        emit UpdateOptionCollaterizationRatio(value);
    }

    /**
     * @notice Used for changing nftSaleRoyaltyPercentage
     * @param value New nftSaleRoyaltyPercentage value
     */
    function setNFTSaleRoyaltyPercentage(uint256 value) external onlyOwner {
        require(value <= 10, "wrong value");
        nftSaleRoyaltyPercentage = value;
        emit UpdateNFTSaleRoyaltyPercentage(value);
    }

    /**
     * @notice Used for updating utilizationRate value
     * @param value New utilizationRate value
     **/
    function setUtilizationRate(uint256 value) external onlyOwner {
        utilizationRate = value;
    }
}
