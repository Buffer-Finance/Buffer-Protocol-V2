import time
from enum import IntEnum
from re import S

import brownie


class OptionType(IntEnum):
    ALL = 0
    PUT = 1
    CALL = 2
    NONE = 3


ONE_DAY = 86400
ADDRESS_0 = "0x0000000000000000000000000000000000000000"


def sqrt(x):
    k = (x / 2) + 1
    result = x
    while k < result:
        (result, k) = (k, ((x / k) + k) / 2)
    return result


class OptionERC3525Testing(object):
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
        usdc_contract,
        bufferPp,
    ):
        self.tokenX_options = options
        self.options_config = options_config
        self.generic_pool = generic_pool
        self.amount = amount
        self.option_holder = accounts[1]
        self.meta = meta
        self.accounts = accounts
        self.owner = accounts[0]
        self.user_1 = accounts[1]
        self.user_2 = accounts[2]
        self.referrer = accounts[3]
        self.project_owner = accounts[7]
        self.option_id = 0
        self.liquidity = liquidity
        self.tokenX = tokenX
        self.chain = chain
        self.expiry = self.generic_pool.fixedExpiry()
        self.usdc_contract = usdc_contract
        self.period = self.expiry - self.chain.time()
        self.strike = self.options_config.fixedStrike()
        self.pp = bufferPp

    def verify_owner(self):
        self.generic_pool.setProjectOwner(self.project_owner, {"from": self.owner})
        assert (
            self.tokenX_options.owner() == self.accounts[0]
        ), "The owner of the contract should be the account the contract was deployed by"

    def get_amounts(self, value, units, option_details):
        amount = option_details[2] / units * value
        locked_amount = option_details[3] / units * value
        premium = option_details[4] // units * value

        return amount, locked_amount, premium

    def verify_creation(self, minter, payment_method):
        current_price = self.pp.getUsdPrice()
        totalTokenXBalance = self.generic_pool.totalTokenXBalance()
        if totalTokenXBalance == 0:
            with brownie.reverts():
                self.tokenX_options.create(
                    self.amount,
                    self.user_1,
                    self.meta,
                    payment_method,
                    {"from": self.owner},
                )
            self.tokenX.transfer(self.user_2, self.liquidity, {"from": self.owner})
            self.tokenX.approve(
                self.generic_pool.address, self.liquidity, {"from": self.owner}
            )
            self.generic_pool.provide(self.liquidity, 0, {"from": self.owner})

        (total_fee, settlement_fee, premium) = self.tokenX_options.fees(
            self.period, self.amount, self.strike, 2
        )
        projectOwner = self.generic_pool.projectOwner()

        if payment_method == 1:
            self.tokenX.transfer(minter, total_fee, {"from": self.owner})
            self.tokenX.approve(
                self.tokenX_options.address, total_fee, {"from": minter}
            )

        else:
            # Because options contract does not has any tokensX
            with brownie.reverts():
                self.tokenX_options.create(
                    self.amount,
                    self.user_1,
                    self.meta,
                    payment_method,
                    {"from": self.owner},
                )

            self.tokenX.transfer(
                self.tokenX_options.address,
                total_fee,
                {"from": self.owner},
            )
            total_fee_usd = (
                total_fee
                * (10 ** self.usdc_contract.decimals())
                / 10 ** self.tokenX.decimals()
            ) * current_price
            self.usdc_contract.transfer(
                minter,
                total_fee_usd / 1e8,
                {"from": self.owner},
            )
            self.usdc_contract.approve(
                self.tokenX_options.address,
                total_fee_usd / 1e8,
                {"from": minter},
            )

        with brownie.reverts("ERC20: transfer amount exceeds allowance"):
            self.tokenX_options.create(
                self.amount,
                self.user_1,
                self.meta,
                payment_method,
                {"from": self.owner},
            )
        self.tokenX_options.approvePoolToTransferTokenX(
            {"from": self.owner},
        )
        # Initial values
        settlementFeeRecipient = self.options_config.settlementFeeRecipient()
        stakingFeePercentage = self.options_config.stakingFeePercentage()
        referralRewardPercentage = self.options_config.referralRewardPercentage()

        initial_tokenX_balance_option_contract = self.tokenX.balanceOf(
            self.tokenX_options.address
        )
        initial_usdc_balance_option_holder = self.usdc_contract.balanceOf(
            self.option_holder
        )
        initial_usdc_balance_project_owner = self.usdc_contract.balanceOf(projectOwner)
        initial_tokenX_balance_option_holder = self.tokenX.balanceOf(self.option_holder)
        initial_tokenX_balance_settlementFeeRecipient = self.tokenX.balanceOf(
            settlementFeeRecipient
        )
        initial_tokenX_balance_pool = self.tokenX.balanceOf(self.generic_pool.address)
        initial_tokenX_balance_owner = self.tokenX.balanceOf(self.owner)
        initial_tokenX_balance_referrer = self.tokenX.balanceOf(self.referrer)
        self.tokenX.approve(self.tokenX_options.address, total_fee, {"from": minter})

        # Creation
        option = self.tokenX_options.create(
            self.amount, self.referrer, self.meta, payment_method, {"from": minter}
        )
        option_id = option.return_value
        self.option_id = option_id
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

        # Final values
        stakingAmount = (settlement_fee * stakingFeePercentage) / 100
        adminFee = settlement_fee - stakingAmount
        referralReward = (adminFee * referralRewardPercentage) / 100
        adminFee = adminFee - referralReward

        final_tokenX_balance_option_contract = self.tokenX.balanceOf(
            self.tokenX_options.address
        )
        final_usdc_balance_option_holder = self.usdc_contract.balanceOf(
            self.option_holder
        )
        final_usdc_balance_project_owner = self.usdc_contract.balanceOf(projectOwner)
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

        # asserts
        if payment_method == 1:
            assert (
                final_tokenX_balance_option_contract
                == initial_tokenX_balance_option_contract
                and final_usdc_balance_option_holder
                == initial_usdc_balance_option_holder
                and final_usdc_balance_project_owner
                == initial_usdc_balance_project_owner
            ), "Something went wrong"

        else:
            assert (
                final_tokenX_balance_option_contract
                < initial_tokenX_balance_option_contract
                and final_usdc_balance_option_holder
                < initial_usdc_balance_option_holder
                and final_usdc_balance_project_owner
                > initial_usdc_balance_project_owner
                and initial_tokenX_balance_option_holder
                == final_tokenX_balance_option_holder
            ), "Something went wrong"

        assert (
            final_tokenX_balance_owner - initial_tokenX_balance_owner
        ) == adminFee, "Wrong admin fee transfer"
        assert (
            final_tokenX_balance_settlementFeeRecipient
            - initial_tokenX_balance_settlementFeeRecipient
        ) == stakingAmount, "Wrong stakingAmount transfer"
        assert (
            final_tokenX_balance_referrer - initial_tokenX_balance_referrer
        ) == referralReward, "Wrong referralReward transfer"
        assert _strike == self.strike, "option creation should go through"
        assert _expiration == self.expiry, "option creation should go through"
        # Can't compare the fee as it won't be exactly same as it is dependent on block timestamp
        # assert (
        #     initial_tokenX_balance_option_holder - final_tokenX_balance_option_holder
        # ) == total_fee, "Wrong fee transfer"
        # assert (
        #     final_tokenX_balance_pool - initial_tokenX_balance_pool
        # ) == premium, "Wrong premium transfer"
        return option_id

    def verify_fixed_params(self):
        strike = self.options_config.fixedStrike() + int(1e8)

        with brownie.reverts(""):
            self.options_config.setStrike(strike)

        self.chain.sleep(self.period + ONE_DAY)
        self.chain.mine(1)

        self.options_config.setStrike(strike)
        fixedStrike = self.options_config.fixedStrike()
        assert fixedStrike == strike, "Wrong strike"

    def admin_function(self, round_id, expected_round_id):

        self.tokenX_options.setRoundIDForExpiry(round_id, {"from": self.accounts[0]})
        _round_id = self.tokenX_options.expiryToRoundID(self.expiry)
        assert _round_id == expected_round_id

    def european_unlock(self, round_id):
        self.chain.snapshot()
        with brownie.reverts("O4"):
            self.tokenX_options.unlock(self.option_id, {"from": self.option_holder})

        self.chain.sleep(self.period + ONE_DAY)
        self.chain.mine(1)
        option_data = self.tokenX_options.options(self.option_id)
        initial_tokenX_balance_option_holder = self.tokenX.balanceOf(self.option_holder)
        unlock_option = self.tokenX_options.unlock(
            self.option_id, {"from": self.option_holder}
        )
        final_tokenX_balance_option_holder = self.tokenX.balanceOf(self.option_holder)
        print("unlocked", self.option_id)
        option_data = self.tokenX_options.options(self.option_id)

        unlock_events = unlock_option.events
        (_, price, _, _, _) = self.pp.getRoundData(round_id)

        if self.strike <= price:
            print("profit")
            expected_profit = ((price - self.strike) * self.amount) / price

            assert unlock_events["Exercise"]["profit"] == expected_profit
            assert option_data["state"] == 2
            assert (
                final_tokenX_balance_option_holder
                - initial_tokenX_balance_option_holder
                == expected_profit
            )
        else:
            print("Expire")
            assert unlock_events["Expire"]["premium"] == option_data[4]
            assert option_data["state"] == 3
            assert (
                final_tokenX_balance_option_holder
                - initial_tokenX_balance_option_holder
                == 0
            )
        self.chain.revert()

    def european_exercise(self, round_id):
        self.chain.snapshot()
        with brownie.reverts("O4"):
            self.tokenX_options.exercise(self.option_id, {"from": self.option_holder})
        self.chain.sleep(self.period + ONE_DAY)
        self.chain.mine(1)
        (_, price, _, _, _) = self.pp.getRoundData(round_id)
        exerciser = self.user_2

        if self.strike <= price:
            initial_tokenX_balance_option_holder = self.tokenX.balanceOf(
                self.option_holder
            )
            initial_tokenX_balance_exerciser = self.tokenX.balanceOf(exerciser)
            expected_profit = ((price - self.strike) * self.amount) / price

            exercise_option = self.tokenX_options.exercise(
                self.option_id, {"from": exerciser}
            )
            print("exercised", self.option_id)

            final_tokenX_balance_option_holder = self.tokenX.balanceOf(
                self.option_holder
            )
            final_tokenX_balance_exerciser = self.tokenX.balanceOf(exerciser)
            exercise_events = exercise_option.events

            assert exercise_events["Exercise"]["profit"] == expected_profit
            assert (
                final_tokenX_balance_option_holder
                - initial_tokenX_balance_option_holder
                == expected_profit
            )
            assert (
                final_tokenX_balance_exerciser - initial_tokenX_balance_exerciser == 0
            )
        else:
            with brownie.reverts("O17"):
                exercise_option = self.tokenX_options.exercise(
                    self.option_id, {"from": self.option_holder}
                )
        self.chain.revert()

    def test_european_changes(
        self, round_ids, expiration_dates, round_id, expected_round_id, strike
    ):
        self.chain.snapshot()

        for count, _round_id in enumerate(round_ids):
            self.pp.setRoundData(
                _round_id,
                expiration_dates[count],
                strike,
                {"from": self.accounts[0]},
            )
        self.admin_function(round_id, expected_round_id)
        self.european_unlock(expected_round_id)
        self.european_exercise(expected_round_id)
        self.chain.revert()

    def complete_flow_test(self):
        self.verify_owner()
        self.option_id = self.verify_creation(self.option_holder, 1)
        self.option_id = self.verify_creation(self.option_holder, 0)

        self.chain.snapshot()
        with brownie.reverts("O20"):
            self.chain.sleep(self.period + ONE_DAY)
            self.chain.mine(1)
            unlock_option = self.tokenX_options.unlock(
                self.option_id, {"from": self.option_holder}
            )
        self.chain.revert()

        # Continuos one succeeds, in ITM
        self.test_european_changes(
            [1, 2, 3],
            [self.expiry - 2000, self.expiry, self.expiry + 86400],
            3,
            2,
            self.strike + 100,
        )

        # Discontinuos one succeeds, in OTM
        self.test_european_changes(
            [4, 5, 7],
            [self.expiry - 2000, self.expiry, self.expiry + 86400],
            7,
            5,
            self.strike - 100,
        )

        # Lies between 2 and 4, in ATM
        self.test_european_changes(
            [8, 9, 10],
            [self.expiry - 2000, self.expiry - 500, self.expiry + 500],
            10,
            9,
            self.strike,
        )

        # None succeed , in ATM
        try:
            self.test_european_changes(
                [11, 12, 13],
                [self.expiry - 2000, self.expiry - 1000, self.expiry - 500],
                13,
                0,
                self.strike,
            )
        except Exception as e:
            assert str(e).startswith("revert: C1") == True

        # None succeed , in ATM
        try:
            self.test_european_changes(
                [11, 12, 13],
                [self.expiry - 2000, self.expiry - 1000, self.expiry],
                13,
                0,
                self.strike,
            )
        except Exception as e:
            assert str(e).startswith("revert: C1") == True

        # Round id is very small
        try:
            self.test_european_changes(
                [1, 2, 4],
                [self.expiry + 2000, self.expiry, self.expiry + 500],
                1,
                0,
                self.strike + 100,
            )
        except Exception as e:
            assert str(e).startswith("revert: C3") == True

        # Round ID is of greater value then expiry
        try:
            self.test_european_changes(
                [14, 15, 16],
                [self.expiry - 2000, self.expiry + 200, self.expiry + 500],
                16,
                0,
                self.strike + 100,
            )
        except Exception as e:
            assert str(e).startswith("revert: C4") == True


def test_tokenX_options(contracts, accounts, chain):

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
    amount = int(1e18) // 1000
    meta = "test"
    liquidity = int(3 * 1e18)

    option = OptionERC3525Testing(
        accounts,
        european_usdc_options,
        ibfr_pool,
        amount,
        meta,
        chain,
        token_contract,
        liquidity,
        options_config,
        usdc_contract,
        bufferPp,
    )
    option.complete_flow_test()
    option.verify_fixed_params()
