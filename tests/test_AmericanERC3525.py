import time
from enum import IntEnum

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
        self.option_id = 0
        self.liquidity = liquidity
        self.tokenX = tokenX
        self.chain = chain
        self.expiry = self.generic_pool.fixedExpiry()
        self.period = self.expiry - self.chain.time()
        self.strike = self.options_config.fixedStrike()
        self.pp = bufferPp

    def compare_option_details(self, option_detail, create=False):
        for i, detail in enumerate(self.option_details):
            if create == False and i in [2, 3, 4]:
                pass
            else:
                assert option_detail[i] == detail, f"Detail at index {i} not verified"

    def verify_owner(self):
        assert (
            self.tokenX_options.owner() == self.accounts[0]
        ), "The owner of the contract should be the account the contract was deployed by"

    def get_amounts(self, value, units, option_details):
        amount = option_details[2] * value / units
        locked_amount = option_details[3] * value / units
        premium = option_details[4] * value // units

        return amount, locked_amount, premium

    def verify_creation(self, minter):
        totalTokenXBalance = self.generic_pool.totalTokenXBalance()
        if totalTokenXBalance == 0:
            with brownie.reverts("O8"):
                self.tokenX_options.create(
                    self.amount, self.user_1, self.meta, 1, {"from": self.owner}
                )
            self.tokenX.transfer(self.user_2, self.liquidity, {"from": self.owner})
            self.tokenX.approve(
                self.generic_pool.address, self.liquidity, {"from": self.owner}
            )
            self.generic_pool.provide(self.liquidity, 0, {"from": self.owner})

        (total_fee, settlement_fee, premium) = self.tokenX_options.fees(
            self.period, self.amount, self.strike, 2
        )
        self.tokenX.approve(self.tokenX_options.address, total_fee, {"from": minter})

        self.tokenX.transfer(minter, total_fee, {"from": self.owner})
        self.tokenX.approve(self.tokenX_options.address, total_fee, {"from": minter})
        self.tokenX_options.approvePoolToTransferTokenX(
            {"from": self.owner},
        )
        option = self.tokenX_options.create(
            self.amount, self.referrer, self.meta, 1, {"from": minter}
        )
        option_id = option.return_value
        self.option_id = option_id
        self.tokenX_options.options(option_id)
        self.tokenX_options.slotOf(self.option_id)
        self.option_details = self.tokenX_options.options(self.option_id)

        transfer_event = option.events["TransferUnits"][0]
        assert (
            transfer_event["from"] == ADDRESS_0
            and transfer_event["to"]
            == self.tokenX_options.ownerOf(self.option_id)
            == self.option_holder
            and transfer_event["tokenId"] == 0
            and transfer_event["targetTokenId"] == self.option_id
            and transfer_event["transferUnits"] == 1000000
        ), "Parameters not verified"
        return option_id

    def verify_split(self):

        unit_1 = 50000
        unit_2 = 30000
        unit_3 = 20000
        initial_totalTokenXBalance = self.generic_pool.totalTokenXBalance()

        initial_locked_amount = self.generic_pool.lockedAmount()
        input_array = [unit_1, unit_2, unit_3]

        with brownie.reverts("N2"):
            self.tokenX_options.split(
                self.option_id, [unit_1, unit_2, unit_3], {"from": self.user_2}
            )
        with brownie.reverts("N1"):
            self.tokenX_options.split(self.option_id, [], {"from": self.user_2})

        option_units = self.tokenX_options.unitsInToken(self.option_id)
        initial_parent_option_details = self.tokenX_options.options(self.option_id)

        split_function = self.tokenX_options.split(
            self.option_id, input_array, {"from": self.option_holder}
        )

        split_units = split_function.return_value
        self.split_units = split_units
        final_locked_amount = self.generic_pool.lockedAmount()
        final_totalTokenXBalance = self.generic_pool.totalTokenXBalance()
        final_parent_option_details = self.tokenX_options.options(self.option_id)

        assert split_units, "Split function failed"

        totalChildAmount = totalChildPremium = totalChildLockedAmount = 0
        for count, unit in enumerate(split_units):
            option_detail = self.tokenX_options.options(unit)
            self.tokenX_options.slotOf(self.option_id)
            amount, locked_amount, premium = self.get_amounts(
                input_array[count], option_units, self.option_details
            )
            split_event = split_function.events["Split"][count]
            transfer_event = split_function.events["TransferUnits"][count]
            totalChildAmount += amount
            totalChildLockedAmount += locked_amount
            totalChildPremium += premium

            assert (
                self.tokenX_options.ownerOf(unit) == self.option_holder
            ), "Option owners should be the same"
            assert self.tokenX_options.slotOf(unit) == self.tokenX_options.slotOf(
                self.option_id
            ), "Option slots should be the same"
            assert option_detail[0] == self.option_details[0], "Wrong Option state"
            assert option_detail[1] == self.option_details[1], "Wrong strike"
            assert option_detail[2] == amount, "Amount calculation failed"
            assert option_detail[3] == locked_amount, "Locked amount calculation failed"
            assert option_detail[4] == premium, "Premium calculation failed"
            assert (
                option_detail[5] == self.option_details[5]
            ), "Expiration calculation failed"
            assert option_detail[6] == self.option_details[6], "Type calculation failed"
            assert (
                split_event["owner"]
                == self.option_holder
                == self.tokenX_options.ownerOf(unit)
                and split_event["tokenId"] == self.option_id
                and split_event["newTokenId"] == unit
                and split_event["splitUnits"] == input_array[count]
            ), "Parameters not verified"
            assert (
                transfer_event["from"] == ADDRESS_0
                and transfer_event["to"]
                == self.tokenX_options.ownerOf(unit)
                == self.option_holder
                and transfer_event["tokenId"] == 0
                and transfer_event["targetTokenId"] == unit
                and transfer_event["transferUnits"] == input_array[count]
            ), "Parameters not verified"
        assert (
            initial_locked_amount == final_locked_amount
        ), "Locked amount does not match"
        assert (
            initial_totalTokenXBalance == final_totalTokenXBalance
        ), "Token balance does not match"
        assert (
            initial_parent_option_details["amount"]
            - final_parent_option_details["amount"]
            == totalChildAmount
        ), "Wrong parent amount"
        assert (
            initial_parent_option_details["lockedAmount"]
            - final_parent_option_details["lockedAmount"]
            == totalChildLockedAmount
        ), "Wrong parent premium"
        assert (
            initial_parent_option_details["premium"]
            - final_parent_option_details["premium"]
            == totalChildPremium
        ), "Wrong parent locked amount"

    def verify_merge(self, merge_ids, target_id):

        input_array = merge_ids

        with brownie.reverts("N5"):
            self.tokenX_options.merge(input_array, target_id, {"from": self.referrer})
        with brownie.reverts("N4"):
            self.tokenX_options.merge([], target_id, {"from": self.option_holder})
        with brownie.reverts("N6"):
            self.tokenX_options.merge(
                input_array, input_array[1], {"from": self.option_holder}
            )

        former_target_option_detail = self.tokenX_options.options(target_id)
        total_amount = former_target_option_detail[2]
        total_locked_amount = former_target_option_detail[3]
        merge_function = self.tokenX_options.merge(
            input_array, target_id, {"from": self.option_holder}
        )
        target_option_detail = self.tokenX_options.options(target_id)

        assert self.tokenX_options.slotOf(target_id) == self.tokenX_options.slotOf(
            self.option_id
        ), "Option slots should be the same"

        for count, unit in enumerate(input_array):
            option_detail = self.tokenX_options.options(unit)
            self.tokenX_options.unitsInToken(unit)
            total_amount += option_detail[2]
            total_locked_amount += option_detail[3]
            merge_event = merge_function.events["Merge"][count]

            # Original token id should be burnt
            with brownie.reverts(""):
                self.tokenX_options.ownerOf(unit)
            assert (
                merge_event["owner"]
                == self.option_holder
                == self.tokenX_options.ownerOf(target_id)
                and merge_event["tokenId"] == unit
                and merge_event["targetTokenId"] == target_id
            ), "Parameters not verified"
            transfer_event = merge_function.events["TransferUnits"][count]
            assert (
                transfer_event["from"] == self.option_holder
                and transfer_event["to"] == ADDRESS_0
                and transfer_event["tokenId"] == unit
                and transfer_event["targetTokenId"] == 0
            ), "Parameters not verified"
        assert target_option_detail[2] == total_amount, "Amount does not match"
        assert (
            target_option_detail[3] == total_locked_amount
        ), "Locked amount does not match"

    def verify_transfer(self, unit_3):

        transfer_units = 1000
        units = self.tokenX_options.unitsInToken(unit_3)
        former_option_detail = self.tokenX_options.options(unit_3)
        with brownie.reverts("N9"):
            self.tokenX_options.transferFrom(
                self.referrer,
                self.user_2,
                unit_3,
                transfer_units,
                {"from": self.referrer},
            )
        with brownie.reverts("N10"):
            self.tokenX_options.transferFrom(
                self.option_holder,
                ADDRESS_0,
                unit_3,
                transfer_units,
                {"from": self.referrer},
            )
        transfer_function = self.tokenX_options.transferFrom(
            self.option_holder,
            self.user_2,
            unit_3,
            transfer_units,
            {"from": self.option_holder},
        )
        new_option_id = transfer_function.return_value

        assert new_option_id, "Transfer function failed"
        assert (
            self.tokenX_options.ownerOf(new_option_id) == self.user_2
        ), "Option owners should verify"

        option_detail = self.tokenX_options.options(new_option_id)
        final_option_detail = self.tokenX_options.options(unit_3)

        self.compare_option_details(option_detail)
        assert self.tokenX_options.slotOf(new_option_id) == self.tokenX_options.slotOf(
            self.option_id
        ), "Option slots should be the same"
        transfer_event = transfer_function.events["TransferUnits"][1]

        amount, locked_amount, premium = self.get_amounts(
            transfer_units, units, former_option_detail
        )
        assert option_detail[2] == amount, "Amount calculation failed"
        assert option_detail[3] == locked_amount, "Locked amount calculation failed"
        assert option_detail[4] == premium, "Premium calculation failed"

        assert (
            former_option_detail[2] - final_option_detail[2] == amount
        ), "Amount calculation failed"
        assert (
            former_option_detail[3] - final_option_detail[3] == locked_amount
        ), "Locked amount calculation failed"
        assert (
            former_option_detail[4] - final_option_detail[4] == premium
        ), "Premium calculation failed"
        assert (
            transfer_event["from"] == self.option_holder
            and transfer_event["to"] == self.user_2
            and transfer_event["tokenId"] == unit_3
            and transfer_event["targetTokenId"] == new_option_id
            and transfer_event["transferUnits"] == transfer_units
        ), "Parameters not verified"

        return new_option_id

    def verify_transfer_2(self, unit_3, new_option_id):

        transfer_units = 100
        units_3 = self.tokenX_options.unitsInToken(unit_3)
        self.tokenX_options.unitsInToken(new_option_id)
        option_detail_3 = self.tokenX_options.options(unit_3)
        former_tg_option_detail = self.tokenX_options.options(new_option_id)
        former_from_option_detail = self.tokenX_options.options(unit_3)

        transfer_function = self.tokenX_options.transferFrom(
            self.option_holder,
            self.user_2,
            unit_3,
            new_option_id,
            transfer_units,
            {"from": self.option_holder},
        )
        tg_option_detail = self.tokenX_options.options(new_option_id)
        from_option_detail = self.tokenX_options.options(unit_3)
        transfer_event = transfer_function.events["TransferUnits"][0]
        amount, locked_amount, premium = self.get_amounts(
            transfer_units, units_3, option_detail_3
        )
        assert self.tokenX_options.slotOf(new_option_id) == self.tokenX_options.slotOf(
            self.option_id
        ), "Option slots should be the same"
        assert (
            transfer_event["from"] == self.option_holder
            and transfer_event["to"] == self.user_2
            and transfer_event["tokenId"] == unit_3
            and transfer_event["targetTokenId"] == new_option_id
            and transfer_event["transferUnits"] == transfer_units
        ), "Parameters not verified"
        assert (
            tg_option_detail[2] == former_tg_option_detail[2] + amount
        ), "Amount calculation failed"
        assert (
            tg_option_detail[3] == former_tg_option_detail[3] + locked_amount
        ), "Locked amount calculation failed"
        assert (
            tg_option_detail[4] == former_tg_option_detail[4] + premium
        ), "Premium calculation failed"

        assert (
            former_from_option_detail[2] == from_option_detail[2] + amount
        ), "Amount calculation failed"
        assert (
            former_from_option_detail[3] == from_option_detail[3] + locked_amount
        ), "Locked amount calculation failed"
        assert (
            former_from_option_detail[4] == from_option_detail[4] + premium
        ), "Premium calculation failed"

    def verify_unlocking(self):
        self.chain.snapshot()
        option_owner = self.tokenX_options.ownerOf(self.option_id)

        with brownie.reverts("O4"):
            self.tokenX_options.unlock(self.option_id, {"from": option_owner})

        self.chain.sleep(self.period + ONE_DAY)
        self.chain.mine(1)

        with brownie.reverts("O13"):
            self.tokenX_options.exercise(self.option_id, {"from": option_owner})

        option_details = self.tokenX_options.options(self.option_id)
        initial_locked_premium = self.generic_pool.lockedPremium()
        initial_locked_amount = self.generic_pool.lockedAmount()
        unlock_option = self.tokenX_options.unlock(
            self.option_id, {"from": option_owner}
        )
        final_locked_premium = self.generic_pool.lockedPremium()
        final_locked_amount = self.generic_pool.lockedAmount()
        final_option_details = self.tokenX_options.options(self.option_id)

        unlock_events = unlock_option.events

        assert unlock_events, "Should unlock on expiry"
        assert (
            initial_locked_amount - final_locked_amount == option_details[3]
        ), "Wrong amount unlocked"
        assert (
            initial_locked_premium - final_locked_premium == option_details[4]
        ), "Wrong premium unlocked"
        assert unlock_events["Profit"][0]["amount"] == option_details[4], "Wrong profit"
        assert unlock_events, "Should unlock on expiry"
        assert final_option_details[0] == 3, "Option not expired"
        print("unlocked", self.option_id)

        self.chain.revert()

    def verify_exercise(self):

        option_owner = self.tokenX_options.ownerOf(self.option_id)
        option = self.tokenX_options.options(self.option_id)
        current_price = self.pp.getUsdPrice()
        profit = min(
            (current_price - option["strike"]) * option["amount"] // current_price,
            option["lockedAmount"],
        )

        initial_tokenX_balance_option_holder = self.tokenX.balanceOf(option_owner)
        initial_tokenX_balance_pool = self.tokenX.balanceOf(self.generic_pool.address)

        self.chain.mine(50)
        self.tokenX_options.exercise(self.option_id, {"from": option_owner})

        final_tokenX_balance_option_holder = self.tokenX.balanceOf(option_owner)
        final_tokenX_balance_pool = self.tokenX.balanceOf(self.generic_pool.address)
        print("profit", profit)
        assert (
            final_tokenX_balance_option_holder - initial_tokenX_balance_option_holder
        ) == profit, "Wrong fee transfer"
        assert (
            initial_tokenX_balance_pool - final_tokenX_balance_pool
        ) == profit, "pool sent wrong profit"
        print("exercised", self.option_id)

    def verify_auto_exercise(self):
        with brownie.reverts(""):
            self.tokenX_options.exercise(self.option_id, {"from": self.owner})
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

    def verify_temp_exercise(self, id):
        self.chain.snapshot()
        self.option_id = id
        self.verify_exercise()
        self.chain.revert()

    def verify_temp_unlocking(self, id):
        self.chain.snapshot()
        self.option_id = id
        self.verify_unlocking()
        self.chain.revert()

    def complete_flow_test(self):
        self.verify_owner()
        for _ in range(2):
            print("round ", _)
            self.option_id = self.verify_creation(self.option_holder)

            print("#########Split#########")
            self.verify_split()
            print(self.split_units, self.option_id)

            self.verify_exercise()
            for i in self.split_units:
                self.verify_temp_exercise(i)
                self.verify_temp_unlocking(i)

            print("#########Merge#########")
            target_id = self.split_units[2]
            merged_ids = [self.split_units[0], self.split_units[1]]
            self.verify_merge(merged_ids, target_id)
            self.verify_temp_exercise(target_id)
            self.verify_temp_unlocking(target_id)

            print("#########Transfer1#########")
            from_id = self.split_units[2]
            new_option_id = self.verify_transfer(from_id)
            self.verify_temp_exercise(from_id)
            self.verify_temp_exercise(new_option_id)
            self.verify_temp_unlocking(from_id)
            self.verify_temp_unlocking(new_option_id)

            print("#########Transfer2#########")
            self.verify_transfer_2(from_id, new_option_id)
            self.verify_temp_exercise(from_id)
            self.verify_temp_exercise(new_option_id)
            self.verify_temp_unlocking(from_id)
            self.verify_temp_unlocking(new_option_id)

            print("#########Unlocking#########")
            self.verify_unlocking()

            self.verify_exercise()
            self.verify_creation(self.option_holder)
            print("created", self.option_id)


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
        bufferPp,
    )
    option.complete_flow_test()
    option.verify_fixed_params()
