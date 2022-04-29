#!/usr/bin/python3

import time
from enum import IntEnum

import pytest

ONE_DAY = 86400


class OptionType(IntEnum):
    ALL = 0
    PUT = 1
    CALL = 2
    NONE = 3


@pytest.fixture(scope="function", autouse=True)
def isolate(fn_isolation):
    # perform a chain rewind after completing each test, to ensure proper isolation
    # https://eth-brownie.readthedocs.io/en/v1.10.3/tests-pytest-intro.html#isolation-fixtures
    pass


@pytest.fixture(scope="module")
def contracts(
    IBFR,
    FakePriceProvider,
    OptionMath,
    ABDKMath64x64,
    accounts,
    BufferIBFRPoolV2,
    OptionConfig,
    BufferUSDCTokenXOptions,
    FeeCalculator,
    WNEAR,
    BufferEuropeanUSDCTokenXOptions,
):
    fixedStrike = int(395e8)
    fixedExpiry = int(time.time()) + ONE_DAY * 7

    ibfr_contract = IBFR.deploy({"from": accounts[0]})

    wnear_contract = WNEAR.deploy({"from": accounts[0]})
    usdc_contract = wnear_contract
    token_contract = ibfr_contract
    tokenX = token_contract

    ibfr_pool = BufferIBFRPoolV2.deploy(
        token_contract.address, fixedExpiry, {"from": accounts[0]}
    )

    pp = FakePriceProvider.deploy(int(400e8), {"from": accounts[0]})
    bufferPp = pp

    # Deploy libraries
    ABDKMath64x64.deploy({"from": accounts[0]})
    OptionMath.deploy({"from": accounts[0]})
    FeeCalculator.deploy({"from": accounts[0]})
    OPTION_ISSUER_ROLE = ibfr_pool.OPTION_ISSUER_ROLE()

    iv = 110e2
    options_config = OptionConfig.deploy(
        accounts[7],
        iv,
        fixedStrike,
        ibfr_pool.address,
        {"from": accounts[0]},
    )

    usdc_options = BufferUSDCTokenXOptions.deploy(
        token_contract.address,
        bufferPp.address,
        ibfr_pool.address,
        options_config.address,
        usdc_contract.address,
        {"from": accounts[0]},
    )
    OPTION_ISSUER_ROLE = ibfr_pool.OPTION_ISSUER_ROLE()
    ibfr_pool.grantRole(
        OPTION_ISSUER_ROLE,
        usdc_options.address,
        {"from": accounts[0]},
    )

    european_usdc_options = BufferEuropeanUSDCTokenXOptions.deploy(
        token_contract.address,
        bufferPp.address,
        ibfr_pool.address,
        options_config.address,
        usdc_contract.address,
        {"from": accounts[0]},
    )
    OPTION_ISSUER_ROLE = ibfr_pool.OPTION_ISSUER_ROLE()
    ibfr_pool.grantRole(
        OPTION_ISSUER_ROLE,
        european_usdc_options.address,
        {"from": accounts[0]},
    )

    return (
        token_contract,
        pp,
        tokenX,
        options_config,
        ibfr_pool,
        usdc_options,
        usdc_contract,
        bufferPp,
        european_usdc_options,
    )
