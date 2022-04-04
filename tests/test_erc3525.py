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

    def compare_option_details(self, option_detail, create=False):
        print(option_detail, self.option_details)
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
        amount = option_details[2] / units * value
        locked_amount = option_details[3] / units * value
        premium = option_details[4] // units * value

        return amount, locked_amount, premium

    def verify_creation(self, minter):
        totalTokenXBalance = self.generic_pool.totalTokenXBalance()
        if totalTokenXBalance == 0:
            with brownie.reverts("Pool Error: The pool is empty"):
                self.tokenX_options.create(
                    self.amount, self.user_1, self.meta, {"from": self.user_1}
                )
            self.tokenX.transfer(self.user_2, self.liquidity, {"from": self.owner})
            self.tokenX.approve(
                self.generic_pool.address, self.liquidity, {"from": self.user_2}
            )
            self.generic_pool.provide(self.liquidity, 0, {"from": self.user_2})

        (total_fee, settlement_fee, premium) = self.tokenX_options.fees(
            self.period, self.amount, self.strike, 2
        )

        self.tokenX.transfer(minter, total_fee, {"from": self.owner})
        self.tokenX.approve(self.tokenX_options.address, total_fee, {"from": minter})

        option = self.tokenX_options.create(
            self.amount, minter, self.meta, {"from": minter}
        )
        option_id = option.return_value
        self.option_id = option_id
        option_detail = self.tokenX_options.options(option_id)
        print(option_id, option_detail)
        slot_id = self.tokenX_options.optionSlotMapping(self.option_id)

        assert slot_id == self.tokenX_options.slotOf(
            self.option_id
        ), "Slot ids should match"
        # slot_details = self.tokenX_options.slotDetails(slot_id)
        self.option_details = self.tokenX_options.options(self.option_id)

        # self.compare_option_details(slot_details, True)

        self.max_divisible_units = self.tokenX_options.maxUnits()

        transfer_event = option.events["TransferUnits"][0]
        assert (
            transfer_event["from"] == ADDRESS_0
            and transfer_event["to"]
            == self.tokenX_options.ownerOf(self.option_id)
            == self.option_holder
            and transfer_event["tokenId"] == 0
            and transfer_event["targetTokenId"] == self.option_id
            and transfer_event["transferUnits"] == self.max_divisible_units == 1000000
        ), "Parameters not verified"
        return option_id

    def verify_split(self):

        unit_1 = 50000
        unit_2 = 30000
        unit_3 = 20000

        input_array = [unit_1, unit_2, unit_3]

        with brownie.reverts(""):
            self.tokenX_options.split(
                self.option_id, [unit_1, unit_2, unit_3], {"from": self.user_2}
            )
        with brownie.reverts("Empty splitUnits"):
            self.tokenX_options.split(self.option_id, [], {"from": self.user_2})

        option_units = self.tokenX_options.units(self.option_id)

        split_function = self.tokenX_options.split(
            self.option_id, input_array, {"from": self.option_holder}
        )

        split_units = split_function.return_value
        self.split_units = split_units

        assert split_units, "Split function failed"
        for count, unit in enumerate(split_units):
            assert (
                self.tokenX_options.ownerOf(unit) == self.option_holder
            ), "Option owners should be the same"
            assert self.tokenX_options.optionSlotMapping(
                unit
            ) == self.tokenX_options.optionSlotMapping(
                self.option_id
            ), "Option slots should be the same"
            option_detail = self.tokenX_options.options(unit)
            # self.compare_option_details(option_detail)
            slot_id = self.tokenX_options.optionSlotMapping(self.option_id)
            amount, locked_amount, premium = self.get_amounts(
                input_array[count], option_units, self.option_details
            )
            assert option_detail[0] == self.option_details[0], "Wrong Option state"
            assert option_detail[1] == self.option_details[1], "Wrong strike"
            assert option_detail[2] == amount, "Amount calculation failed"
            assert option_detail[3] == locked_amount, "Locked amount calculation failed"
            assert option_detail[4] == premium, "Premium calculation failed"
            assert (
                option_detail[5] == self.option_details[5]
            ), "Expiration calculation failed"
            assert option_detail[6] == self.option_details[6], "Type calculation failed"
            split_event = split_function.events["Split"][count]

            assert (
                split_event["owner"]
                == self.option_holder
                == self.tokenX_options.ownerOf(unit)
                and split_event["tokenId"] == self.option_id
                and split_event["newTokenId"] == unit
                and split_event["splitUnits"] == input_array[count]
            ), "Parameters not verified"

            transfer_event = split_function.events["TransferUnits"][count]
            assert (
                transfer_event["from"] == ADDRESS_0
                and transfer_event["to"]
                == self.tokenX_options.ownerOf(unit)
                == self.option_holder
                and transfer_event["tokenId"] == 0
                and transfer_event["targetTokenId"] == unit
                and transfer_event["transferUnits"] == input_array[count]
            ), "Parameters not verified"

    def verify_merge(self):

        unit_1 = self.split_units[0]
        unit_2 = self.split_units[1]
        unit_3 = self.split_units[2]

        input_array = [unit_1, unit_2]

        with brownie.reverts(""):
            self.tokenX_options.merge(input_array, unit_3, {"from": self.referrer})
        with brownie.reverts("Empty optionIDs"):
            self.tokenX_options.merge([], unit_3, {"from": self.option_holder})
        with brownie.reverts("self merge not allowed"):
            self.tokenX_options.merge(
                [unit_1, unit_2], unit_2, {"from": self.option_holder}
            )

        former_target_option_detail = self.tokenX_options.options(unit_3)
        total_amount = former_target_option_detail[2]
        total_locked_amount = former_target_option_detail[3]
        merge_function = self.tokenX_options.merge(
            [unit_1, unit_2], unit_3, {"from": self.option_holder}
        )
        target_option_detail = self.tokenX_options.options(unit_3)

        # self.compare_option_details(target_option_detail)
        assert self.tokenX_options.optionSlotMapping(
            unit_3
        ) == self.tokenX_options.optionSlotMapping(
            self.option_id
        ), "Option slots should be the same"
        for count, unit in enumerate(input_array):
            option_detail = self.tokenX_options.options(unit)
            # self.compare_option_details(option_detail)
            units = self.tokenX_options.units(unit)
            total_amount += option_detail[2]
            total_locked_amount += option_detail[3]
            merge_event = merge_function.events["Merge"][count]
            with brownie.reverts(""):
                self.tokenX_options.ownerOf(unit)
            assert (
                merge_event["owner"]
                == self.option_holder
                == self.tokenX_options.ownerOf(unit_3)
                and merge_event["tokenId"] == unit
                and merge_event["targetTokenId"] == unit_3
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

    def verify_transfer(self):

        unit_1 = self.split_units[0]
        unit_2 = self.split_units[1]
        unit_3 = self.split_units[2]

        transfer_units = 1000
        units = self.tokenX_options.units(unit_3)
        former_option_detail = self.tokenX_options.options(unit_3)
        with brownie.reverts("source token owner mismatch"):
            self.tokenX_options.transferFrom(
                self.referrer,
                self.user_2,
                unit_3,
                transfer_units,
                {"from": self.referrer},
            )
        with brownie.reverts("transfer to the zero address"):
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
        self.compare_option_details(option_detail)
        assert self.tokenX_options.optionSlotMapping(
            new_option_id
        ) == self.tokenX_options.optionSlotMapping(
            self.option_id
        ), "Option slots should be the same"
        transfer_event = transfer_function.events["TransferUnits"][1]
        assert (
            transfer_event["from"] == self.option_holder
            and transfer_event["to"] == self.user_2
            and transfer_event["tokenId"] == unit_3
            and transfer_event["targetTokenId"] == new_option_id
            and transfer_event["transferUnits"] == transfer_units
        ), "Parameters not verified"

        amount, locked_amount, premium = self.get_amounts(
            transfer_units, units, former_option_detail
        )
        assert option_detail[2] == amount, "Amount calculation failed"
        assert option_detail[3] == locked_amount, "Locked amount calculation failed"
        assert option_detail[4] == premium, "Premium calculation failed"

        return new_option_id

    def verify_transfer_2(self, new_option_id):

        unit_1 = self.split_units[0]
        unit_2 = self.split_units[1]
        unit_3 = self.split_units[2]

        transfer_units = 100
        units_3 = self.tokenX_options.units(unit_3)
        units_4 = self.tokenX_options.units(new_option_id)
        option_detail_3 = self.tokenX_options.options(unit_3)
        former_tg_option_detail = self.tokenX_options.options(new_option_id)

        transfer_function = self.tokenX_options.transferFrom(
            self.option_holder,
            self.user_2,
            unit_3,
            new_option_id,
            transfer_units,
            {"from": self.option_holder},
        )
        tg_option_detail = self.tokenX_options.options(new_option_id)

        assert self.tokenX_options.optionSlotMapping(
            new_option_id
        ) == self.tokenX_options.optionSlotMapping(
            self.option_id
        ), "Option slots should be the same"
        transfer_event = transfer_function.events["TransferUnits"][0]
        assert (
            transfer_event["from"] == self.option_holder
            and transfer_event["to"] == self.user_2
            and transfer_event["tokenId"] == unit_3
            and transfer_event["targetTokenId"] == new_option_id
            and transfer_event["transferUnits"] == transfer_units
        ), "Parameters not verified"

        amount, locked_amount, premium = self.get_amounts(
            transfer_units, units_3, option_detail_3
        )
        assert (
            tg_option_detail[2] == former_tg_option_detail[2] + amount
        ), "Amount calculation failed"
        assert (
            tg_option_detail[3] == former_tg_option_detail[3] + locked_amount
        ), "Locked amount calculation failed"
        assert (
            tg_option_detail[4] == former_tg_option_detail[4] + premium
        ), "Premium calculation failed"

    def verify_unlocking(self):
        # unlock() Unchanged
        self.chain.snapshot()
        with brownie.reverts("Option has not expired yet"):
            self.tokenX_options.unlock(self.option_id, {"from": self.option_holder})

        self.chain.sleep(self.period + ONE_DAY)
        self.chain.mine(1)

        with brownie.reverts("Option has expired"):
            self.tokenX_options.exercise(self.option_id, {"from": self.option_holder})

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
        self.verify_owner()
        self.option_id = self.verify_creation(self.option_holder)
        print("#########Split#########")
        self.verify_split()
        print("#########Merge#########")
        self.verify_merge()
        new_option_id = self.verify_transfer()
        self.verify_transfer_2(new_option_id)

        self.verify_unlocking()

        self.verify_exercise()
        print("exercised", self.option_id)
        self.verify_creation(self.option_holder)
        print("created", self.option_id)
        self.verify_exercise()
        print("exercised", self.option_id)


def test_tokenX_options(contracts, accounts, chain):

    (
        tokenX,
        tokenX_options_v5,
        ibfr_pool,
        options_config,
    ) = contracts
    amount = int(1e18) // 1000
    meta = "test"
    liquidity = int(3 * 1e18)

    option = OptionERC3525Testing(
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
