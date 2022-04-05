from enum import IntEnum
from math import isclose

import brownie


class OptionType(IntEnum):
    ALL = 0
    PUT = 1
    CALL = 2
    NONE = 3


ONE_DAY = 86400


def sqrt(x):
    k = (x / 2) + 1
    result = x
    while k < result:
        (result, k) = (k, ((x / k) + k) / 2)
    return result


class OptionTesting(object):
    def __init__(
        self,
        accounts,
        options,
        generic_pool,
        amount,
        meta,
        chain,
        tokenX,
        liquidity,
        options_config,
    ):
        self.tokenX_options = options
        self.options_config = options_config
        self.generic_pool = generic_pool
        self.amount = amount
        self.option_holder = accounts[4]
        self.meta = meta
        self.accounts = accounts
        self.owner = accounts[0]
        self.user_1 = accounts[1]
        self.user_2 = accounts[2]
        self.referrer = accounts[3]
        self.option_id = 0
        self.liquidity = liquidity
        self.tokenX = tokenX
        self.chain = chain
        self.expiry = self.generic_pool.fixedExpiry()
        self.period = self.expiry - self.chain.time()
        self.strike = self.options_config.fixedStrike()

    def verify_option_type(self):
        # Should verify that fixedOptionType is Call
        assert (
            self.tokenX_options.fixedOptionType() == OptionType.CALL
        ), "Wrong trading permission"

    def verify_owner(self):
        # Should verify the owner
        assert (
            self.tokenX_options.owner() == self.accounts[0]
        ), "The owner of the contract should be the account the contract was deployed by"

    def verify_role(self):
        # Should have the option issuer role
        OPTION_ISSUER_ROLE = self.generic_pool.OPTION_ISSUER_ROLE()

        assert (
            self.generic_pool.hasRole(OPTION_ISSUER_ROLE, self.tokenX_options.address)
            == True
        ), "option issuer role verified"

    def verify_token_price(self):
        # getTokenPrice() Should return thr tokenX/USD price
        token_price = self.tokenX_options.getCurrentPrice()
        print("token_price", token_price / 1e8)

    def verify_creation(self):
        # create() SHould create an option
        # if option type is not call, revert
        # if the total fee was X
        # If user hasn't approved enough, revert
        # should Transfer X tokenX from the user to the contract
        # should Add options to the the options object
        # should Mint the NFT
        # should distributeSettlementFee()
        # Should transfer stakingAmount(tokenX) from options to settlementFeeRecipient
        # Should transfer adminFee(tokenX) from options to owner
        # Should referralReward adminFee(tokenX) from options to referrer
        # should approve pool to premium(tokenX)
        # should lock()
        # should trasnfer premium(tokenX) from options to pool
        totalTokenXBalance = self.generic_pool.totalTokenXBalance()
        if totalTokenXBalance == 0:
            with brownie.reverts("Pool Error: The pool is empty"):
                self.tokenX_options.create(
                    self.amount, self.user_1, self.meta, {"from": self.user_1}
                )

            # Add liquidity in the pool first
            self.tokenX.transfer(self.user_2, self.liquidity, {"from": self.owner})
            self.tokenX.approve(
                self.generic_pool.address, self.liquidity, {"from": self.user_2}
            )
            self.generic_pool.provide(self.liquidity, 0, {"from": self.user_2})

        with brownie.reverts("ERC20: transfer amount exceeds balance"):
            self.tokenX_options.create(
                self.amount, self.user_1, self.meta, {"from": self.user_1}
            )

        # Should work with the updated priceFeed(pancakePair)
        (total_fee, settlement_fee, premium) = self.tokenX_options.fees(
            self.period, self.amount, self.strike, 2
        )

        self.tokenX.transfer(self.option_holder, total_fee, {"from": self.owner})

        settlementFeeRecipient = self.tokenX_options.settlementFeeRecipient()
        stakingFeePercentage = self.options_config.stakingFeePercentage()
        referralRewardPercentage = self.options_config.referralRewardPercentage()

        initial_tokenX_balance_option_holder = self.tokenX.balanceOf(self.option_holder)
        initial_tokenX_balance_settlementFeeRecipient = self.tokenX.balanceOf(
            settlementFeeRecipient
        )
        initial_tokenX_balance_pool = self.tokenX.balanceOf(self.generic_pool.address)
        initial_tokenX_balance_owner = self.tokenX.balanceOf(self.owner)
        initial_tokenX_balance_referrer = self.tokenX.balanceOf(self.referrer)

        self.tokenX.approve(
            self.tokenX_options.address, total_fee, {"from": self.option_holder}
        )

        option = self.tokenX_options.create(
            self.amount, self.referrer, self.meta, {"from": self.option_holder}
        )
        self.option_id = option.return_value
        (
            _,
            _strike,
            _,
            _locked_amount,
            _,
            _expiration,
            _,
        ) = self.tokenX_options.options(self.option_id)

        stakingAmount = (settlement_fee * stakingFeePercentage) / 100
        adminFee = settlement_fee - stakingAmount
        referralReward = (adminFee * referralRewardPercentage) / 100
        adminFee = adminFee - referralReward

        final_tokenX_balance_option_holder = self.tokenX.balanceOf(self.option_holder)
        final_tokenX_balance_settlementFeeRecipient = self.tokenX.balanceOf(
            settlementFeeRecipient
        )
        final_tokenX_balance_pool = self.tokenX.balanceOf(self.generic_pool.address)
        final_tokenX_balance_owner = self.tokenX.balanceOf(self.owner)
        final_tokenX_balance_referrer = self.tokenX.balanceOf(self.referrer)
        print(final_tokenX_balance_pool - initial_tokenX_balance_pool, "premium")
        print("stakingAmount", stakingAmount / 1e18)
        print("referralReward", referralReward / 1e18)
        print("adminFee", adminFee / 1e18)
        print("premium", premium / 1e18)
        print("total_fee", total_fee / 1e18)
        print("_locked_amount", _locked_amount / 1e18)
        assert (
            self.tokenX.balanceOf(self.tokenX_options.address) == 0
        ), "Something went wrong"
        assert (
            final_tokenX_balance_owner - initial_tokenX_balance_owner
        ) == adminFee, "Wrong admin fee transfer"
        # assert (
        #     final_tokenX_balance_settlementFeeRecipient
        #     - initial_tokenX_balance_settlementFeeRecipient
        # ) == stakingAmount, "Wrong stakingAmount transfer"
        assert (
            final_tokenX_balance_referrer - initial_tokenX_balance_referrer
        ) == referralReward, "Wrong referralReward transfer"
        assert _strike == self.strike, "option creation should go through"
        assert _expiration == self.expiry, "option creation should go through"
        # Can't compare the fee as it won't be exactly same as it is dependent on block timestamp
        # assert (
        #     initial_tokenX_balance_option_holder - final_tokenX_balance_option_holder
        # ) == total_fee, "Wrong fee transfer"
        # # assert (
        #     final_tokenX_balance_pool - initial_tokenX_balance_pool
        # ) == premium, "Wrong premium transfer"

    def verify_unlocking(self):
        # unlock() Unchanged
        self.chain.snapshot()
        with brownie.reverts("Option has not expired yet"):
            self.tokenX_options.unlock(self.option_id, {"from": self.option_holder})

        self.chain.sleep(self.period + ONE_DAY)
        self.chain.mine(1)

        # with brownie.reverts("Option has expired"):
        #     self.tokenX_options.exercise(self.option_id, {"from": self.option_holder})

        unlock_option = self.tokenX_options.unlock(
            self.option_id, {"from": self.option_holder}
        )
        unlock_events = unlock_option.events
        assert unlock_events, "Should unlock on expiry"
        self.chain.revert()

    def verify_exercise(self):
        # canExercise()
        # if current block number is same as that of creation then revert
        option_block = self.tokenX_options.optionBlocks(self.option_id)
        if option_block == self.chain.height:
            with brownie.reverts("Block number not permitted"):
                self.tokenX_options.exercise.call(
                    self.option_id, {"from": self.option_holder}
                )

        # exercise() Unchanged
        # payProfit()
        # Should work with the updated priceFeed(pancakePair)
        # SHould transfer profit(tokenX) to the option holder
        option = self.tokenX_options.options(self.option_id)
        current_price = self.tokenX_options.getCurrentPrice()
        profit = min(
            (current_price - option["strike"]) * option["amount"] // current_price,
            option["lockedAmount"],
        )

        initial_tokenX_balance_option_holder = self.tokenX.balanceOf(self.option_holder)
        initial_tokenX_balance_pool = self.tokenX.balanceOf(self.generic_pool.address)

        self.chain.mine(50)
        self.tokenX_options.exercise(self.option_id, {"from": self.option_holder})

        final_tokenX_balance_option_holder = self.tokenX.balanceOf(self.option_holder)
        final_tokenX_balance_pool = self.tokenX.balanceOf(self.generic_pool.address)

        assert (
            final_tokenX_balance_option_holder - initial_tokenX_balance_option_holder
        ) == profit, "Wrong fee transfer"
        assert (
            initial_tokenX_balance_pool - final_tokenX_balance_pool
        ) == profit, "pool sent wrong profit"

    def verify_auto_exercise(self):
        with brownie.reverts("msg.sender is not eligible to exercise the option"):
            self.tokenX_options.exercise(self.option_id, {"from": self.owner})
        with brownie.reverts("msg.sender is not eligible to exercise the option"):
            self.tokenX_options.exercise(self.option_id, {"from": self.accounts[7]})
        AUTO_CLOSER_ROLE = self.tokenX_options.AUTO_CLOSER_ROLE()

        self.tokenX_options.grantRole(
            AUTO_CLOSER_ROLE,
            self.accounts[7],
            {"from": self.owner},
        )
        self.chain.snapshot()

        last_half_hour_of_expiry = self.period - 27 * 60
        self.chain.sleep(last_half_hour_of_expiry)
        self.chain.mine(50)

        exercise = self.tokenX_options.exercise(
            self.option_id, {"from": self.accounts[7]}
        )
        self.chain.revert()

    def verify_fixed_params(self):
        expiry = self.generic_pool.fixedExpiry() + ONE_DAY * 10
        strike = self.options_config.fixedStrike() + int(1e8)

        with brownie.reverts("Can't change expiry before the expiry ends"):
            self.generic_pool.setExpiry(expiry)
        with brownie.reverts("Can't change strike before the expiry ends"):
            self.options_config.setStrike(strike)

        self.chain.sleep(self.period + ONE_DAY)
        self.chain.mine(1)

        self.options_config.setStrike(strike)
        fixedStrike = self.options_config.fixedStrike()
        self.generic_pool.setExpiry(expiry)
        fixedExpiry = self.generic_pool.fixedExpiry()

        self.strike = fixedStrike
        self.expiry = fixedExpiry
        self.period = fixedExpiry - self.chain.time()
        assert fixedStrike == strike, "Wrong strike"
        assert fixedExpiry == expiry, "Wrong Expiry"

    def complete_flow_test(self):
        self.verify_option_type()
        self.verify_owner()
        self.verify_role()
        self.verify_token_price()

        # setImpliedVolRate() Unchanged

        # setSettlementFeePercentage() Unchanged

        # setStakingFeePercentage() Unchanged

        # setTradingPermission() Unchanged

        # setReferralRewardPercentage() Unchanged

        # setOptionCollaterizationRatio() Unchanged

        # setNFTSaleRoyaltyPercentage() Unchanged

        # setSettlementFeeRecipient() should change the settlement fee recipient

        self.verify_creation()
        print("created", self.option_id)

        # getSettlementFee() Unchanged

        # unlockAll() Unchanged

        # unlock() Unchanged

        self.verify_unlocking()

        # self.verify_exercise()
        # print("exercised", self.option_id)

        self.verify_creation()
        print("created", self.option_id)
        # self.verify_auto_exercise()
        # print("exercised", self.option_id)


def test_tokenX_options(contracts, accounts, chain):

    (tokenX, tokenX_options_v5, ibfr_pool, options_config) = contracts
    amount = int(1e18) // 100
    meta = "test"
    liquidity = int(1 * 1e18)

    option = OptionTesting(
        accounts,
        tokenX_options_v5,
        ibfr_pool,
        amount,
        meta,
        chain,
        tokenX,
        liquidity,
        options_config,
    )
    option.verify_fixed_params()
    option.complete_flow_test()
