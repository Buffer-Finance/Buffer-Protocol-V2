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
    PancakePair,
    OptionMath,
    ABDKMath64x64,
    accounts,
    BufferTokenXOptionsV5Test,
    BufferIBFRPoolV5,
    OptionConfig,
):
    fixedStrike = int(395e8)
    fixedExpiry = int(time.time()) + ONE_DAY * 7

    token_contract = IBFR.deploy({"from": accounts[0]})

    ibfr_pool = BufferIBFRPoolV5.deploy(
        token_contract.address, fixedExpiry, {"from": accounts[0]}
    )
    tokenX = token_contract

    # Deploy libraries
    ABDKMath64x64.deploy({"from": accounts[0]})
    OptionMath.deploy({"from": accounts[0]})

    OPTION_ISSUER_ROLE = ibfr_pool.OPTION_ISSUER_ROLE()

    # Deploy tokenX options
    pancakePair = PancakePair.deploy({"from": accounts[0]})
    pancakePair.setReserves(40000e8, 8, 1645196730)

    twap = accounts[0]
    tokenX_address = token_contract.address
    token0 = token_contract.address
    token1 = token_contract.address

    options_config = OptionConfig.deploy(
        accounts[7],
        int(110e2),
        fixedStrike,
        ibfr_pool.address,
        {"from": accounts[0]},
    )
    tokenX_options_v5 = BufferTokenXOptionsV5Test.deploy(
        tokenX_address,
        ibfr_pool.address,
        token0,
        token1,
        twap,
        options_config,
        {"from": accounts[0]},
    )
    ibfr_pool.grantRole(
        OPTION_ISSUER_ROLE, tokenX_options_v5.address, {"from": accounts[0]}
    )

    return (
        tokenX,
        tokenX_options_v5,
        ibfr_pool,
        options_config,
    )
