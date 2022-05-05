import math
import time

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
    tokenX_amount_1 = int(3 * 1e18) // 100
    tokenX_amount_2 = int(2 * 1e18) // 100
    tokenX_amount_3 = int(1 * 1e18) // 100
    MAX_INTEGER = 2 ** 256 - 1
    ONE_DAY = 86400
    ADDRESS_0 = "0x0000000000000000000000000000000000000000"

    # Should verify lp name, lp short name and tokenX for the lp
    assert tokenX.address == ibfr_pool.tokenX(), "Token is incorrect"
    assert f"Buffer Generic {tokenX.symbol()} LP Token" == ibfr_pool.name()
    assert f"r{tokenX.symbol()}" == ibfr_pool.symbol()

    # Should verify the roles assigned by constructor
    OPTION_ISSUER_ROLE = ibfr_pool.OPTION_ISSUER_ROLE()
    assert ibfr_pool.hasRole(OPTION_ISSUER_ROLE, user_2) == False
    ibfr_pool.grantRole(OPTION_ISSUER_ROLE, user_2, {"from": owner})
    assert (
        ibfr_pool.hasRole(OPTION_ISSUER_ROLE, user_2) == True
    ), "Option Issuer Role wasn't granted"

    DEFAULT_ADMIN_ROLE = ibfr_pool.DEFAULT_ADMIN_ROLE()
    assert (
        ibfr_pool.hasRole(DEFAULT_ADMIN_ROLE, owner) == True
    ), "Default Admin Role wasnt granted to deployer"
    assert (
        ibfr_pool.hasRole(DEFAULT_ADMIN_ROLE, user_2) == False
    ), "Random user has Admin Role"

    assert ibfr_pool.owner() == owner, "Wrong buffer owner"

    # Should assign the expiry in the constructor
    fixedExpiry = ibfr_pool.fixedExpiry()
    # print("fixedExpiry", fixedExpiry)
    assert (
        fixedExpiry > chain.time()
    ), "Expiry should be greater than the current block time"
    assert not ibfr_pool.hasPoolEnded(), "Wrong pool state"

    # Should verify setting project owner
    with brownie.reverts():  # Wrong role
        ibfr_pool.setProjectOwner(accounts[7], {"from": user_1})
    PROJECT_OWNER_ROLE = ibfr_pool.PROJECT_OWNER_ROLE()

    ibfr_pool.setProjectOwner(accounts[7], {"from": owner})
    assert ibfr_pool.projectOwner() == accounts[7], "Wasn't able to set project Owner"
    assert (
        ibfr_pool.hasRole(PROJECT_OWNER_ROLE, accounts[7]) == True
    ), "PROJECT_OWNER_ROLE verified"

    # Should verify setting project owner
    with brownie.reverts():  # Wrong role
        ibfr_pool.setMaxLiquidity(5000000e18, {"from": user_1})
    maxLiquidity = 5000000 * 10 ** tokenX.decimals()
    ibfr_pool.setMaxLiquidity(maxLiquidity, {"from": owner})
    assert ibfr_pool.maxLiquidity() == maxLiquidity, "Wrong maxLiquidity"

    # Should verify functioning of the revoke call
    chain.snapshot()
    ibfr_pool.revokeRole(DEFAULT_ADMIN_ROLE, owner, {"from": owner})
    assert (
        ibfr_pool.hasRole(DEFAULT_ADMIN_ROLE, owner) == False
    ), "Default Admin Role should be revoked"
    chain.revert()

    users = [user_1, user_2, user_1, user_3, user_4, user_5]
    amounts = [
        tokenX_amount_1,
        tokenX_amount_1 + 10,
        tokenX_amount_1 * 2,
        tokenX_amount_1,
        tokenX_amount_1,
        tokenX_amount_1,
    ]
    hasPoolEnded = ibfr_pool.hasPoolEnded()

    # Initial share is 0
    assert ibfr_pool.shareOf(user_1) == 0, "wrong share"

    with brownie.reverts():  # Nothing to withdraw
        ibfr_pool.withdraw(tokenX_amount_1, {"from": user_1})

    # provide() Should provide liquidity
    # If amount of tokenx provided to the contract are X
    # If provider hasn't approved that much amount then it should revert
    # If f(X) < minMint then revert
    # else X tokenX should be transferred from the provider to the lp
    # and f(X) rbfr should be transferred to the provider(minted)
    for user in users:
        with brownie.reverts("ERC20: transfer amount exceeds balance"):
            ibfr_pool.provide(tokenX_amount_1, 0, {"from": user})

        tokenX.transfer(user, tokenX_amount_1, {"from": owner})
        tokenX.approve(ibfr_pool.address, tokenX_amount_1, {"from": user})

        initial_tokenX_balance_user = tokenX.balanceOf(user)
        initial_tokenX_balance_lp = tokenX.balanceOf(ibfr_pool.address)
        initial_rbfr_balance_user = ibfr_pool.balanceOf(user)
        initial_rbfr_balance_owner = ibfr_pool.balanceOf(ibfr_pool.owner())

        ibfr_pool.provide(tokenX_amount_1, 0, {"from": user})
        expected_mint = ibfr_pool.INITIAL_RATE() * tokenX_amount_1
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

        # withdraw() Should not withdraw before expiry
        # If timestamp is before expiry just add to the queue and emit AddedWithdrawRequest event
        # Should increment the requestCount

        round = ibfr_pool.currentRound()
        queueEnd = ibfr_pool.queueEnd()
        default_dict = {"withdrawAmount": 0, "account": 0, "round": 0}
        initialAddressToWithdrawRequest = ibfr_pool.AddressToWithdrawRequest(user)

        withdrawRequestInitial = (
            ibfr_pool.WithdrawRequestQueue(
                initialAddressToWithdrawRequest["requestIndex"]
            )
            if initialAddressToWithdrawRequest["exists"]
            else default_dict
        )
        initial_rbfr_balance_user = ibfr_pool.balanceOf(user)
        initial_tokenX_balance_user = tokenX.balanceOf(user)
        initial_tokenX_pool = ibfr_pool.totalTokenXBalance()
        initial_rbfr_pool = ibfr_pool.totalSupply()

        withdraw = ibfr_pool.withdraw(amount, {"from": user})

        addressToWithdrawRequest = ibfr_pool.AddressToWithdrawRequest(user)
        withdrawRequest = ibfr_pool.WithdrawRequestQueue(
            addressToWithdrawRequest["requestIndex"]
        )
        final_tokenX_balance_user = tokenX.balanceOf(user)
        final_rbfr_balance_user = ibfr_pool.balanceOf(user)
        final_tokenX_pool = ibfr_pool.totalTokenXBalance()
        final_rbfr_pool = ibfr_pool.totalSupply()

        assert withdraw.events["InitiateWithdraw"], "Wrong event emitted"
        assert addressToWithdrawRequest["requestIndex"] == (
            initialAddressToWithdrawRequest["requestIndex"]
            if initialAddressToWithdrawRequest["exists"]
            else queueEnd
        ), "Wrong index"
        assert addressToWithdrawRequest["exists"] == True, "Wrong flag"

        assert (
            withdrawRequest["withdrawAmount"] - withdrawRequestInitial["withdrawAmount"]
            == amount
        ), "Wrong amount"
        assert withdrawRequest["round"] == round, "Wrong round"
        assert withdrawRequest["account"] == user, "Wrong account"

        assert (
            final_tokenX_balance_user - initial_tokenX_balance_user
        ) == 0, "Wrong user1 tokenX balance"
        assert (
            final_tokenX_pool - initial_tokenX_pool
        ) == 0, "Wrong pool tokenX  balance"
        assert (
            final_rbfr_balance_user - initial_rbfr_balance_user
        ) == 0, "Wrong rbfr user1  balance"
        assert (final_rbfr_pool - initial_rbfr_pool) == 0, "Wrong rbfr pool  balance"

    def test_withdraw(user, amount):
        # withdraw() Should withdraw liquidity after expiry
        # If amount of tokenx to be withdrawn from the contract are X
        # if enough funds are not there or f(x) > maxBurn then revert
        # else X tokenX should be transferred from the lp to the provider
        # and f(X) rbfr should be burnt

        _supply = ibfr_pool.totalSupply()
        _totalTokenXBalance = ibfr_pool.totalTokenXBalance()
        pool_balance_user = ibfr_pool.balanceOf(user)
        initial_tokenX_balance_user = tokenX.balanceOf(user)
        initial_tokenX_balance_lp = tokenX.balanceOf(ibfr_pool.address)

        maxUserWithdrawal = (pool_balance_user * _totalTokenXBalance) // _supply
        amountToWithdraw = min(maxUserWithdrawal, amount)

        withdraw = ibfr_pool.withdraw(amountToWithdraw, {"from": user})
        expected_burn = math.ceil((amountToWithdraw * _supply) / _totalTokenXBalance)

        final_tokenX_balance_user = tokenX.balanceOf(user)
        final_tokenX_balance_lp = tokenX.balanceOf(ibfr_pool.address)

        assert withdraw.events["Withdraw"], "Wrong event emitted"
        assert (
            pool_balance_user - ibfr_pool.balanceOf(user) == expected_burn
        ), "Wrong burn"
        assert (
            initial_tokenX_balance_lp - final_tokenX_balance_lp
        ) == amountToWithdraw, "Wrong lp balance"
        assert (
            final_tokenX_balance_user - initial_tokenX_balance_user
        ) == amountToWithdraw, "Wrong user balance"

    def test_unlock(user, id):
        ll = ibfr_pool.lockedLiquidity(user, id)
        lockedPremium = ibfr_pool.lockedPremium()
        lockedAmount = ibfr_pool.lockedAmount()

        unlock = ibfr_pool.unlock(id, {"from": user})

        final_ll = ibfr_pool.lockedLiquidity(user, id)
        final_lockedPremium = ibfr_pool.lockedPremium()
        final_lockedAmount = ibfr_pool.lockedAmount()

        assert (
            lockedPremium - final_lockedPremium == ll["premium"]
        ), "Wrong lockedPremium"
        assert lockedAmount - final_lockedAmount == ll["amount"], "Wrong lockedAmount"
        assert unlock.events["Profit"]["amount"] == ll["premium"], "Wrong premium"
        assert final_ll["locked"] == False, "Wrong state"

    # processWithdrawRequests() Should reset when 0 requests are there
    chain.snapshot()

    withdraw = ibfr_pool.processWithdrawRequests(2)
    isAcceptingWithdrawRequests = ibfr_pool.isAcceptingWithdrawRequests()
    assert isAcceptingWithdrawRequests, "Wrong isAcceptingWithdrawRequests"

    chain.revert()

    # adminWithdraw()
    chain.snapshot()

    initial_tokenX_balance_user = tokenX.balanceOf(user_1)
    share_of = ibfr_pool.shareOf(user_1)

    with brownie.reverts():  # Wrong role
        ibfr_pool.adminWithdraw(user_1, share_of, {"from": user_1})

    withdraw = ibfr_pool.adminWithdraw(user_1, share_of, {"from": owner})

    final_tokenX_balance_user = tokenX.balanceOf(user_1)

    assert (
        final_tokenX_balance_user - initial_tokenX_balance_user
    ) == share_of, "Wrong user balance"

    chain.revert()

    for i, user in enumerate(users):
        test_initiate_withdraw(user, amounts[i])
    updatedQueueEnd = ibfr_pool.queueEnd()
    assert updatedQueueEnd == len(set(users)), "Wrong queue end"
    print("Withdrawals initiated")

    # setPoolState()
    with brownie.reverts():  # Wrong role
        ibfr_pool.setPoolState(False, {"from": user_2})
    chain.snapshot()

    ibfr_pool.setPoolState(True, {"from": owner})

    for i, user in enumerate(users):
        test_withdraw(user, amounts[i])
    print("Processed Withdrawal after pool has ended")

    chain.revert()
    lock_ids = [0, 1]
    lock_amount = tokenX_amount_3
    # lock() Should lock funds
    # Revert if msg.sender does not has OPTION_ISSUER_ROLE
    # Revert if wrong id
    # If amount of tokenx to be locked are X
    # if X > totalTokenXBalance then revert
    # if the total locked amount after this is > 80% of total pool balance then Revert
    # if options contracts hasn't approved premimum for pool then revert
    # else
    # transfer premimum(tokenX) from the options to the pool
    # Should update the lockedLiquidity,lockedPremium and lockedAmount
    for id in lock_ids:
        with brownie.reverts():  # Wrong role
            ibfr_pool.lock(id, tokenX_amount_3, tokenX_amount_2, {"from": user_1})

        _supply = ibfr_pool.totalSupply()
        _totalTokenXBalance = ibfr_pool.totalTokenXBalance()
        initial_locked_liquidity = ibfr_pool.lockedAmount()
        initial_locked_premimum = ibfr_pool.lockedPremium()

        tokenX.transfer(user_2, tokenX_amount_2, {"from": owner})

        with brownie.reverts("Pool: Amount is too large."):
            ibfr_pool.lock(
                id,
                _totalTokenXBalance + tokenX_amount_3,
                tokenX_amount_2,
                {"from": user_2},
            )

        with brownie.reverts("ERC20: transfer amount exceeds allowance"):
            ibfr_pool.lock(id, tokenX_amount_3, tokenX_amount_2, {"from": user_2})

        initial_tokenX_balance_options = tokenX.balanceOf(user_2)
        initial_tokenX_balance_lp = tokenX.balanceOf(ibfr_pool.address)

        tokenX.approve(ibfr_pool.address, tokenX_amount_1, {"from": user_2})
        ibfr_pool.lock(id, lock_amount, tokenX_amount_2, {"from": user_2})

        final_tokenX_balance_options = tokenX.balanceOf(user_2)
        final_tokenX_balance_lp = tokenX.balanceOf(ibfr_pool.address)
        final_locked_liquidity = ibfr_pool.lockedAmount()
        final_locked_premimum = ibfr_pool.lockedPremium()

        assert (
            initial_tokenX_balance_options - final_tokenX_balance_options
        ) == tokenX_amount_2, "Wrong options balance"
        assert (
            final_tokenX_balance_lp - initial_tokenX_balance_lp
        ) == tokenX_amount_2, "Wrong lp balance"
        assert (
            final_locked_premimum - initial_locked_premimum
        ) == tokenX_amount_2, "Wrong lockedPremium"
        assert (
            final_locked_liquidity - initial_locked_liquidity
        ) == tokenX_amount_3, "Wrong lockedAmount"

    # changeLock()
    old_premium = tokenX_amount_2
    old_amount = tokenX_amount_3

    def test_change_lock(new_amount, new_premium):
        chain.snapshot()
        initial_locked_liquidity = ibfr_pool.lockedAmount()
        initial_locked_premimum = ibfr_pool.lockedPremium()
        initial_tokenX_balance_options = tokenX.balanceOf(user_2)

        ibfr_pool.changeLock(id, new_amount, new_premium, {"from": user_2})

        final_locked_liquidity = ibfr_pool.lockedAmount()
        final_tokenX_balance_options = tokenX.balanceOf(user_2)
        final_locked_premimum = ibfr_pool.lockedPremium()

        if old_premium > new_premium:
            assert (
                abs(initial_tokenX_balance_options - final_tokenX_balance_options)
                == old_premium - new_premium
            ), "Wrong options balance"
        else:
            assert (
                abs(initial_tokenX_balance_options - final_tokenX_balance_options) == 0
            ), "Wrong options balance"

        assert (abs(final_locked_premimum - initial_locked_premimum)) == abs(
            old_premium - new_premium
        ), "Wrong lockedPremium"
        assert (abs(final_locked_liquidity - initial_locked_liquidity)) == abs(
            new_amount - old_amount
        ), "Wrong lockedAmount"

        chain.revert()

    new_locks = [
        (tokenX_amount_3 * 0.95, int(old_premium * 0.95)),
        (tokenX_amount_3 * 0.95, int(old_premium * 1)),
        (tokenX_amount_3 * 1.05, int(old_premium * 1.05)),
    ]
    for i in new_locks:
        test_change_lock(i[0], i[1])
    print("changed lock")

    # send() Should send profit to option holder
    # Revert if msg.sender does not has OPTION_ISSUER_ROLE
    # Revert if wrong id
    # Revert if invalid address
    # If amount of tokenx to be sent as profit are X
    # then Transfer the min(X, ll.amount)
    # Emit events accordingly
    def test_send(payout, id):
        chain.snapshot()
        initial_locked_liquidity = ibfr_pool.lockedAmount()
        initial_locked_premimum = ibfr_pool.lockedPremium()
        initial_tokenX_balance_user = tokenX.balanceOf(user_1)
        ll = ibfr_pool.lockedLiquidity(user_2, id)
        expected_payout = min(payout, ll["amount"])

        send = ibfr_pool.send(id, user_1, payout, {"from": user_2})

        final_ll = ibfr_pool.lockedLiquidity(user_2, id)
        final_locked_liquidity = ibfr_pool.lockedAmount()
        final_tokenX_balance_user = tokenX.balanceOf(user_1)
        final_locked_premimum = ibfr_pool.lockedPremium()

        if expected_payout > ll["premium"]:
            assert (
                send.events["Loss"]["amount"] == expected_payout - ll["premium"]
            ), "Wrong loss amount"
        else:
            assert (
                send.events["Profit"]["amount"] == ll["premium"] - expected_payout
            ), "Wrong profit amount"

        assert final_ll["locked"] == False, "Wrong state"
        assert (
            initial_locked_premimum - final_locked_premimum == ll["premium"]
        ), "Wrong lockedPremium"
        assert (
            initial_locked_liquidity - final_locked_liquidity == ll["amount"]
        ), "Wrong lockedAmount"
        assert (
            final_tokenX_balance_user - initial_tokenX_balance_user
        ) == expected_payout, "Wrong user balance"
        chain.revert()

    payouts = [int(lock_amount * 0.95), int(lock_amount * 1.05)]
    with brownie.reverts():  # Wrong role
        ibfr_pool.send(lock_ids[0], user_1, tokenX_amount_3, {"from": user_1})
    for index, id in enumerate(lock_ids):
        test_send(payouts[index], id)
    print("sent profits")

    # shareOf() Should return user's share of token(X) in the lp
    # Should return 0 if totalSupply is 0
    # Else it should return user's rbfr * (tokenX per rbfr)
    pool_balance_user1 = ibfr_pool.balanceOf(user_1)
    _supply = ibfr_pool.totalSupply()
    _totalTokenXBalance = ibfr_pool.totalTokenXBalance()
    expected_share = pool_balance_user1 * (_totalTokenXBalance / _supply)

    assert ibfr_pool.shareOf(user_1) == expected_share, "wrong share"

    # processWithdrawRequests() Shouldn't Process before roll over
    with brownie.reverts("Can't process the requests when the round is active"):
        ibfr_pool.processWithdrawRequests(2)

    # rollOver()
    with brownie.reverts():  # Wrong role
        ibfr_pool.rollOver(chain.time() + ONE_DAY * 14, {"from": user_2})
    with brownie.reverts("Can't roll over before the expiry ends"):
        ibfr_pool.rollOver(chain.time() + ONE_DAY * 14, {"from": owner})

    chain.snapshot()
    chain.sleep(fixedExpiry - chain.time() + ONE_DAY)
    chain.mine(1)
    with brownie.reverts("Current round hasn't ended completely"):
        ibfr_pool.rollOver(chain.time() + ONE_DAY * 14, {"from": owner})

    # Unlock all the funds before rollOver
    for id in lock_ids:
        test_unlock(user_2, id)
    assert ibfr_pool.lockedAmount() == 0, "Wrong value"
    assert ibfr_pool.lockedPremium() == 0, "Wrong value"

    initialRound = ibfr_pool.currentRound()
    new_expiry = chain.time() + ONE_DAY * 14
    ibfr_pool.rollOver(new_expiry, {"from": owner})

    finalRound = ibfr_pool.currentRound()
    assert finalRound - initialRound == 1, "Wrong round"
    assert ibfr_pool.fixedExpiry() == new_expiry, "Wrong expiry"
    assert (
        not ibfr_pool.isAcceptingWithdrawRequests()
    ), "Wrong isAcceptingWithdrawRequests"

    with brownie.reverts("Pool: Not accepting withdraw requests currently"):
        withdraw = ibfr_pool.withdraw(tokenX_amount_1, {"from": user_1})

    with brownie.reverts():  # Already unlocked
        ibfr_pool.send(lock_ids[0], user_1, tokenX_amount_3, {"from": user_2})

    # chain.revert()

    # processWithdrawRequests() Should Process withdraw requests
    # If timestamp is before expiry just revert
    # Else check if the requestIndex is valid
    # If yes then call withdraw() with the request's params
    # Delete the request when processed
    queueEnd = ibfr_pool.queueEnd()
    queueStart = ibfr_pool.queueStart()
    requestsToProcess = queueEnd - queueStart
    print("requestsToProcess", requestsToProcess)
    # Tested all the processing is working with minimal granularity
    print("processing withdrawals 1 at a time")
    chain.snapshot()
    withdraw_events = []
    steps = 1
    for req in range(0, requestsToProcess, steps):

        withdrawRequest = ibfr_pool.WithdrawRequestQueue(req)
        user = withdrawRequest["account"]

        _supply = ibfr_pool.totalSupply()
        _totalTokenXBalance = ibfr_pool.totalTokenXBalance()
        pool_balance_user1 = ibfr_pool.balanceOf(user)
        initial_tokenX_balance_lp = tokenX.balanceOf(ibfr_pool.address)
        maxUserWithdrawal = pool_balance_user1 * _totalTokenXBalance // _supply

        withdraw = ibfr_pool.processWithdrawRequests(steps)
        withdraw_events += withdraw.events["ProcessWithdrawRequest"]

        withdrawRequest = ibfr_pool.WithdrawRequestQueue(req)
        addressToWithdrawRequest = ibfr_pool.AddressToWithdrawRequest(user)

        assert withdraw.events["Withdraw"]["amount"] == min(
            maxUserWithdrawal,
            withdraw.events["ProcessWithdrawRequest"]["tokenXAmount"],
        )
        assert (
            withdraw.events["Withdraw"] and withdraw.events["ProcessWithdrawRequest"]
        ), "Wrong events"
        assert (
            withdrawRequest["withdrawAmount"] == 0
            and withdrawRequest["account"] == ADDRESS_0
            and withdrawRequest["round"] == 0
        ), "Request not deleted"
        assert (
            addressToWithdrawRequest["exists"] == False
            and addressToWithdrawRequest["requestIndex"] == 0
        ), "User not deleted"

    queueEnd = ibfr_pool.queueEnd()
    queueStart = ibfr_pool.queueStart()
    assert queueEnd == queueStart == 0, "Wrong queue values"
    assert len(withdraw_events) == len(set(users)), "Wrong number of requests processed"
    assert ibfr_pool.isAcceptingWithdrawRequests(), "Wrong isAcceptingWithdrawRequests"
    print("processed")
    chain.revert()

    # Tested all the processing is working with random granularity
    print("processing withdrawals 2 at a time")
    chain.snapshot()
    withdraw_events = []
    steps = 2

    count = 1
    x = (
        requestsToProcess // steps
        if requestsToProcess % steps == 0
        else requestsToProcess // steps + 1
    )
    while True:
        withdraw = ibfr_pool.processWithdrawRequests(steps)
        withdraw_events += withdraw.events["ProcessWithdrawRequest"]
        count += 1

        if count > x:
            break
    queueEnd = ibfr_pool.queueEnd()
    queueStart = ibfr_pool.queueStart()
    assert queueEnd == queueStart == 0, "Wrong queue values"
    assert len(withdraw_events) == len(set(users)), "Wrong number of requests processed"
    assert ibfr_pool.isAcceptingWithdrawRequests(), "Wrong isAcceptingWithdrawRequests"
    print("processed")
    chain.revert()
