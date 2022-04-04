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
import "@openzeppelin/contracts/security/ReentrancyGuard.sol";
import {OptionMath} from "../../Libraries/OptionMath.sol";
import "./BufferNFTCore.sol";
import "./OptionsConfig.sol";

/**
 * @author Heisenberg
 * @title Buffer BNB Bidirectional (Call and Put) Options
 * @notice Buffer BNB Options Contract
 */
abstract contract OptionsCore is
    IBufferOptionsV5,
    Ownable,
    ReentrancyGuard,
    BufferNFTCore
{
    uint256 public nextTokenId = 0;
    OptionConfig public config;
    address public settlementFeeRecipient;
    mapping(uint256 => Option) public options;
    mapping(uint256 => uint256) public optionBlocks;

    uint256 internal contractCreationTimestamp;

    bytes32 public constant AUTO_CLOSER_ROLE = keccak256("AUTO_CLOSER_ROLE");

    /**
     * @notice Check if the sender can exercise an active option
     * @param optionID ID of your option
     */
    function canExercise(uint256 optionID) internal view returns (bool) {
        require(
            _exists(optionID),
            "ERC721: operator query for nonexistent token"
        );
        require(
            optionBlocks[optionID] != block.number,
            "Block number not permitted"
        );

        address tokenOwner = ERC721.ownerOf(optionID);
        bool isAutoExerciseTrue = autoExerciseStatus[tokenOwner] &&
            hasRole(AUTO_CLOSER_ROLE, msg.sender);

        Option storage option = options[optionID];
        bool isWithinLastHalfHourOfExpiry = block.timestamp >
            (option.expiration - 30 minutes);

        return
            (tokenOwner == msg.sender) ||
            (isAutoExerciseTrue && isWithinLastHalfHourOfExpiry);
    }

    /**
     * @notice Exercises an active option
     * @param optionID ID of your option
     */
    function exercise(uint256 optionID) external {
        require(
            canExercise(optionID),
            "msg.sender is not eligible to exercise the option"
        );

        Option storage option = options[optionID];

        require(option.expiration >= block.timestamp, "Option has expired");
        require(option.state == State.Active, "Wrong state");

        option.state = State.Exercised;
        uint256 profit = payProfit(optionID);

        // Burn the option
        _burn(optionID);

        emit Exercise(optionID, profit);
    }

    // /**
    //  * @notice Unlocks an array of options
    //  * @param optionIDs array of options
    //  */
    // function unlockAll(uint256[] calldata optionIDs) external {
    //     uint256 arrayLength = optionIDs.length;
    //     for (uint256 i = 0; i < arrayLength; i++) {
    //         unlock(optionIDs[i]);
    //     }
    // }

    /**
     * @notice Unlock funds locked in the expired options
     * @param optionID ID of the option
     */
    function unlock(uint256 optionID) public virtual {}

    /**
     * @notice Sends profits in BNB from the BNB pool to an option holder's address
     * @param optionID A specific option contract id
     */
    function payProfit(uint256 optionID)
        internal
        virtual
        returns (uint256 profit)
    {}

    function distributeSettlementFee(uint256 settlementFee, address referrer)
        internal
        virtual
        returns (uint256 stakingAmount)
    {}

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
        virtual
        returns (
            uint256 total,
            uint256 settlementFee,
            uint256 premium
        )
    {}

    /**
     * @notice Calculates settlementFee
     * @param amount Option amount
     * @return fee Settlement fee amount
     */
    function getSettlementFee(uint256 amount)
        internal
        view
        returns (uint256 fee)
    {
        return (amount * config.settlementFeePercentage()) / 100;
    }

    /**
     * @notice Calculates strikeFee
     * @param amount Option amount
     * @param strike Strike price of the option
     * @param currentPrice Current price of BNB
     * @return fee Strike fee amount
     */
    function getStrikeFee(
        uint256 amount,
        uint256 strike,
        uint256 currentPrice,
        OptionType optionType
    ) internal pure returns (uint256 fee) {
        if (strike > currentPrice && optionType == OptionType.Put)
            return ((strike - currentPrice) * amount) / currentPrice;
        if (strike < currentPrice && optionType == OptionType.Call)
            return ((currentPrice - strike) * amount) / currentPrice;
        return 0;
    }

    // The following functions are overrides required by Solidity.

    /**
     * @return result Square root of the number
     */
    function sqrt(uint256 x) internal pure returns (uint256 result) {
        result = x;
        uint256 k = (x / 2) + 1;
        while (k < result) (result, k) = (k, ((x / k) + k) / 2);
    }

    /**
     * Exercise Approval
     */

    // Mapping from owner to exerciser approvals
    mapping(address => bool) public autoExerciseStatus;
    mapping(address => bool) public hasUserBoughtFirstOption;

    // function setAutoExerciseStatus(bool status) public {
    //     autoExerciseStatus[msg.sender] = status;
    //     emit AutoExerciseStatusChange(msg.sender, status);
    // }
}
