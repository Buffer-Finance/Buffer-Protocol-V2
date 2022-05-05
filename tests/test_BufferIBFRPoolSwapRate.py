import math
from math import isclose

import brownie


def test_ibfr_pool(contracts, accounts, chain):

    (
        token_contract,
        pp,
        tokenX,
        options_config,
        ibfr_pool,
        usdc_options,
        usdc_contract,
        bufferPp,
        european_usdc_options,
    ) = contracts
    owner = accounts[0]
    user_1 = accounts[1]
    user_2 = accounts[2]
    user_3 = accounts[3]
    user_4 = accounts[4]
    user_5 = accounts[5]
    tokenX_contract = tokenX.address
    tokenX_amount_1 = int(7 * 1e18) // 100
    tokenX_amount_2 = int(2 * 1e18) // 1000
    tokenX_amount_3 = int(1 * 1e18) // 1000
    MAX_INTEGER = 2 ** 256 - 1
    ONE_DAY = 86400
    ADDRESS_0 = "0x0000000000000000000000000000000000000000"

    # Should verify the roles assigned by constructor
    OPTION_ISSUER_ROLE = ibfr_pool.OPTION_ISSUER_ROLE()
    ibfr_pool.grantRole(OPTION_ISSUER_ROLE, user_2, {"from": owner})
    assert (
        ibfr_pool.hasRole(OPTION_ISSUER_ROLE, user_2) == True
    ), "Option Issuer Role verified"

    # Should assign the expiry in the constructor
    fixedExpiry = ibfr_pool.fixedExpiry()

    # Should verify setting project owner
    with brownie.reverts():  # Wrong role
        ibfr_pool.setProjectOwner(accounts[7], {"from": user_1})
    ibfr_pool.setProjectOwner(accounts[7], {"from": owner})
    assert ibfr_pool.projectOwner() == accounts[7], "wrong project owner"

    users = [user_1, user_2, user_3, user_4, user_5]
    amounts = [
        tokenX_amount_1,
        tokenX_amount_1 + 10,
        tokenX_amount_1 * 2,
        tokenX_amount_1,
        tokenX_amount_1,
    ]
    withdraw_requests = []

    def mint(user):
        with brownie.reverts("ERC20: transfer amount exceeds balance"):
            ibfr_pool.provide(tokenX_amount_1, 0, {"from": user})

        tokenX.transfer(user, tokenX_amount_1, {"from": owner})
        tokenX.approve(ibfr_pool.address, tokenX_amount_1, {"from": user})

        initial_tokenX_balance_user = tokenX.balanceOf(user)
        initial_tokenX_balance_lp = tokenX.balanceOf(ibfr_pool.address)
        initial_rbfr_balance_user = ibfr_pool.balanceOf(user)
        initial_rbfr_balance_owner = ibfr_pool.balanceOf(ibfr_pool.owner())
        _supply = ibfr_pool.totalSupply()

        ibfr_pool.provide(tokenX_amount_1, 0, {"from": user})
        expected_mint = (
            (_supply * tokenX_amount_1) // initial_tokenX_balance_lp
            if _supply > 0
            else ibfr_pool.INITIAL_RATE() * tokenX_amount_1
        )
        print("expected_mint", expected_mint)
        print(
            "swap_rate",
            _supply // initial_tokenX_balance_lp
            if _supply > 0
            else ibfr_pool.INITIAL_RATE(),
        )

        admmin_cut = expected_mint // 1000
        user_mint = expected_mint - admmin_cut

        final_tokenX_balance_user = tokenX.balanceOf(user)
        final_tokenX_balance_lp = tokenX.balanceOf(ibfr_pool.address)
        final_rbfr_balance_user = ibfr_pool.balanceOf(user)
        final_rbfr_balance_owner = ibfr_pool.balanceOf(ibfr_pool.owner())

        assert (
            final_rbfr_balance_user - initial_rbfr_balance_user == user_mint
        ), "Wrong mint"
        assert (
            final_rbfr_balance_owner - initial_rbfr_balance_owner == admmin_cut
        ), "Wrong admin mint"
        assert (
            initial_tokenX_balance_user - final_tokenX_balance_user == tokenX_amount_1
        ), "Wrong user balance"
        assert (
            final_tokenX_balance_lp - initial_tokenX_balance_lp == tokenX_amount_1
        ), "Wrong lp balance"

    def test_initiate_withdraw(user, amount):

        withdraw = ibfr_pool.withdraw(amount, {"from": user})
        return withdraw.events["InitiateWithdraw"]

    ################# COMPLETE FLOW #################

    # Initial mint
    mint(user_1)
    lock_ids = [0, 1, 2, 3, 4]

    # Buy Options
    for id in lock_ids:
        tokenX.transfer(user_2, tokenX_amount_2, {"from": owner})
        tokenX.approve(ibfr_pool.address, tokenX_amount_1, {"from": user_2})
        ibfr_pool.lock(id, tokenX_amount_3, tokenX_amount_2, {"from": user_2})

    # Check swap rate
    _supply = ibfr_pool.totalSupply()
    _tokenX_balance_lp = tokenX.balanceOf(ibfr_pool.address)

    swap_rate = _supply // _tokenX_balance_lp
    utiltization = ibfr_pool.lockedAmount() / ibfr_pool.totalTokenXBalance() * 100
    print("utiltization", utiltization)

    assert swap_rate < ibfr_pool.INITIAL_RATE(), "Wrong swap rate"

    # Mint after buying some options
    for user in users:
        mint(user)

    # Add withdraw requests
    for i, user in enumerate(users):
        withdraw = test_initiate_withdraw(user, amounts[i])
        withdraw_requests += withdraw

    # Send profit to 2 options
    for id in lock_ids[:2]:
        ibfr_pool.send(id, user_2, tokenX_amount_2, {"from": user_2})

    # Unlock the remaining options
    for id in lock_ids[2:]:
        ibfr_pool.unlock(id, {"from": user_2})

    # rollover
    chain.sleep(fixedExpiry - chain.time() + ONE_DAY)
    new_expiry = chain.time() + ONE_DAY * 14
    ibfr_pool.rollOver(new_expiry, {"from": owner})

    # Calculate withdraw amounts
    _supply = ibfr_pool.totalSupply()
    _tokenX_balance_lp = ibfr_pool.totalTokenXBalance()
    assert _tokenX_balance_lp == tokenX.balanceOf(ibfr_pool.address), "Wrong balance"

    expected_burns = []
    for req in withdraw_requests:
        swap_rate = _supply // _tokenX_balance_lp
        print("swap_rate", swap_rate)

        maxUserTokenXWithdrawal = (
            ibfr_pool.balanceOf(req["account"]) * _tokenX_balance_lp
        ) // _supply
        tokenXAmountToWithdraw = (
            maxUserTokenXWithdrawal
            if maxUserTokenXWithdrawal < req["tokenXAmount"]
            else req["tokenXAmount"]
        )

        burn = math.ceil((tokenXAmountToWithdraw * _supply) // _tokenX_balance_lp)
        expected_burns.append(burn)
        _supply -= burn
        _tokenX_balance_lp -= tokenXAmountToWithdraw
        print(" tokenXAmountToWithdraw, burn", req["tokenXAmount"], burn)

    # process withdraws
    queueEnd = ibfr_pool.queueEnd()
    queueStart = ibfr_pool.queueStart()
    requestsToProcess = queueEnd - queueStart
    print("requestsToProcess", requestsToProcess)
    steps = 1
    withdraw_events = []
    for req in range(0, requestsToProcess, steps):
        withdraw = ibfr_pool.processWithdrawRequests(steps)
        withdraw_events += withdraw.events["Withdraw"]

    print("withdraw_events")
    for j, i in enumerate(withdraw_events):
        assert isclose(i["writeAmount"] / 1e18, expected_burns[j] / 1e18, abs_tol=1e-8)
        print(
            " tokenXAmountToWithdraw, burn",
            i["amount"],
        )
