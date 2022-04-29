// SPDX-License-Identifier: BUSL-1.1

pragma solidity ^0.8.0;

/**
 * Smart contract library of mathematical functions operating with signed
 * 64.64-bit fixed point numbers.  Signed 64.64-bit fixed point number is
 * basically a simple fraction whose numerator is signed 128-bit integer and
 * denominator is 2^64.  As long as denominator is always the same, there is no
 * need to store it, thus in Solidity signed 64.64-bit fixed point numbers are
 * represented by int128 type holding only the numerator.
 */
import "../Libraries/OptionMath.sol";
import "../Options/OptionConfig.sol";
import "../Interfaces/Interfaces.sol";
import "../Pool/BufferIBFRPoolV2.sol";

library FeeCalculator {
    function getNewUtilisation(uint256 amount, BufferIBFRPoolV2 pool)
        public
        view
        returns (uint256 utilization)
    {
        uint256 poolBalance = pool.totalTokenXBalance();
        require(poolBalance > 0, "O8");

        utilization = ((pool.lockedAmount() + amount) * 100e8) / poolBalance;
    }

    /**
     * @notice Calculate the Utilisation adjusted ImpliedVol for the pool according to https://www.desmos.com/calculator/xdmhn97opd
     * @param amount Option amount
     * @param pool The pool selling the option
     * @param config The configuration params
     * @return iv The adjusted ImpliedVol
     */
    function currentImpliedVolatility(
        uint256 amount,
        BufferIBFRPoolV2 pool,
        OptionConfig config
    ) public view returns (uint256 iv) {
        iv = config.impliedVolRate();
        uint256 utilization = getNewUtilisation(amount, pool);
        if (utilization > 40e8) {
            iv += (iv * (utilization - 40e8)) / config.utilizationRate();
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
        IBufferOptions.OptionType optionType,
        uint256 currentPrice,
        OptionConfig config,
        BufferIBFRPoolV2 pool
    )
        public
        view
        returns (
            uint256 total,
            uint256 settlementFee,
            uint256 premium
        )
    {
        // usdPremium per amount is USD Price of the option in 1e8
        uint256 usdPremium = OptionMath.blackScholesPrice(
            currentImpliedVolatility(amount, pool, config),
            strike,
            currentPrice,
            period,
            optionType == IBufferOptions.OptionType.Call
        );
        premium = (usdPremium * amount) / currentPrice;
        settlementFee = getSettlementFee(amount, config);
        total = settlementFee + premium;
    }

    /**
     * @notice Calculates settlementFee
     * @param amount Option amount
     * @return fee Settlement fee amount
     */
    function getSettlementFee(uint256 amount, OptionConfig config)
        internal
        view
        returns (uint256 fee)
    {
        return (amount * config.settlementFeePercentage()) / 100;
    }
}
