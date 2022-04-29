pragma solidity ^0.8.0;

// SPDX-License-Identifier: BUSL-1.1

import "./Interfaces/Interfaces.sol";

contract PriceProvider {
    AggregatorV3Interface public priceProvider;

    constructor(AggregatorV3Interface pp) {
        priceProvider = pp;
    }

    // Should return USD price
    function getUsdPrice() external view returns (uint256 _price) {
        (, int256 latestPrice, , , ) = priceProvider.latestRoundData();
        _price = uint256(latestPrice);
    }

    // Should return timestamp of corresponding round
    function getRoundData(uint256 roundID) external view returns (uint80 roundId,uint256 price, uint256 startedAt, uint256 updatedAt,uint80 answeredInRound) {
        int256 _price;
        (roundId, _price, startedAt, updatedAt, answeredInRound) = priceProvider.getRoundData(uint80(roundID));
        price=uint256(_price);
    }

    function latestRoundData() external view returns (uint80 roundId, int256 answer, uint256 startedAt,  uint256 updatedAt, uint80 answeredInRound) {
        (roundId, answer, startedAt, updatedAt, answeredInRound) = priceProvider.latestRoundData();
    }
}

contract FakePriceProvider {
    uint256 public price;
    mapping(uint256 => uint256) public roundIDToExpiry;
    mapping(uint256 => uint256) public roundIDToPrice;

    constructor(uint256 _price) {
        price = _price;
    }

    function getRoundData(uint256 roundID) external view returns (uint80 roundId,uint256 _price, uint256 startedAt, uint256 updatedAt,uint80 answeredInRound) {
        (roundId, _price, startedAt, updatedAt, answeredInRound) = (uint80(roundID), roundIDToPrice[roundID], 0, roundIDToExpiry[roundID], 0);
    }

    function setRoundData(uint256 roundID, uint256 expiry, uint256 _price) external {
        roundIDToExpiry[roundID] = expiry;
        roundIDToPrice[roundID] = _price;
    }

    function setPrice(uint256 _price) external {
        price = _price;
    }

    // Should return USD price
    function getUsdPrice() external view returns (uint256) {
        return price;
    }

}

contract TwapPriceProvider {
    address public token0;
    address public token1;
    ISlidingWindowOracle public twap;

    AggregatorV3Interface public priceProvider;

    constructor(
        address _token0,
        address _token1,
        ISlidingWindowOracle _twap,
        AggregatorV3Interface pp
    ) {
        token0 = _token0;
        token1 = _token1;
        priceProvider = pp;
        twap = _twap;
    }

    // Should return USD price
    function getUsdPrice() external view returns (uint256 _price) {
        (, int256 latestPrice, , , ) = priceProvider.latestRoundData();
        uint256 bnb_price = uint256(latestPrice);
        uint256 token_price = twap.consult(token0, 1e8, token1);
        _price = (token_price * bnb_price) / 1e8;
    }
}
