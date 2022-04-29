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
        print("total_fee", total_fee / 1e18)

        projectOwner = self.generic_pool.projectOwner()
        assert projectOwner != ADDRESS_0, "Wrong project owner"

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
            print(
                "total_fee_usd",
                total_fee_usd / 1e26,
            )
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

    def verify_unlocking(self):
        self.chain.snapshot()
        with brownie.reverts(""):
            self.tokenX_options.unlock(self.option_id, {"from": self.option_holder})

        self.chain.sleep(self.period + ONE_DAY)
        self.chain.mine(1)

        with brownie.reverts(""):
            self.tokenX_options.exercise(self.option_id, {"from": self.option_holder})

        unlock_option = self.tokenX_options.unlock(
            self.option_id, {"from": self.option_holder}
        )
        unlock_events = unlock_option.events
        assert unlock_events, "Should unlock on expiry"
        self.chain.revert()

    def verify_exercise(self):

        option = self.tokenX_options.options(self.option_id)
        current_price = self.pp.getUsdPrice()
        print(current_price, option["strike"], "cp strike")
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
        with brownie.reverts(""):
            self.tokenX_options.exercise(self.option_id, {"from": self.owner})
        with brownie.reverts(""):
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

        self.tokenX_options.exercise(self.option_id, {"from": self.accounts[7]})
        self.chain.revert()

    def verify_fixed_params(self):
        strike = self.options_config.fixedStrike() + int(1e8)

        with brownie.reverts(""):
            self.options_config.setStrike(strike)

        self.chain.sleep(self.period + ONE_DAY)
        self.chain.mine(1)

        self.options_config.setStrike(strike)
        fixedStrike = self.options_config.fixedStrike()
        assert fixedStrike == strike, "Wrong strike"

    def complete_flow_test(self):
        self.verify_owner()
        # payment_method : 0. usdc 1. tokenX
        self.option_id = self.verify_creation(self.option_holder, 1)
        print("created", self.option_id)

        self.verify_unlocking()

        self.verify_exercise()
        print("exercised", self.option_id)
        self.option_id = self.verify_creation(self.option_holder, 0)
        print("created", self.option_id)
        self.verify_exercise()
        print("exercised", self.option_id)


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
        usdc_options,
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
