pragma solidity ^0.8.0;

/**
 * SPDX-License-Identifier: GPL-3.0-or-later
 * Buffer
 * Copyright (C) 2020 Buffer Protocol
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <http://www.gnu.org/licenses/>.
 */
import "@openzeppelin/contracts/token/ERC721/ERC721.sol";

import "@openzeppelin/contracts/utils/structs/EnumerableSet.sol";
import "../../Interfaces/InterfacesV5.sol";
import "@openzeppelin/contracts/access/AccessControl.sol";
import "../Pool/BufferIBFRPoolV5.sol";
import "@openzeppelin/contracts/token/ERC721/extensions/ERC721URIStorage.sol";

abstract contract BufferNFTCore is
    ERC721,
    IBufferOptionsV5,
    AccessControl,
    ERC721URIStorage
{
    using EnumerableSet for EnumerableSet.UintSet;
    using Address for address;


    /// @dev optionId => units
    mapping(uint256 => uint256) public units;
    mapping(uint256 => uint256) public optionSlotMapping;
    mapping(uint256 => SlotDetail) internal slotDetails;

    /// @dev optionId => operator => units
    mapping(uint256 => ApproveUnits) private _tokenApprovalUnits;

    /// @dev slot => optionIds
    mapping(uint256 => EnumerableSet.UintSet) private _slotTokens;

    uint8 internal _unitDecimals = 18;
    uint256 public maxUnits = 1000000;
    BufferIBFRPoolV5 public pool;

    function _mintUnits(
        address minter_,
        uint256 optionId_,
        uint256 slot_,
        uint256 units_
    ) internal virtual {
        if (!_exists(optionId_)) {
            _mint(minter_, optionId_);
            _slotTokens[slot_].add(optionId_);
        }

        units[optionId_] = units[optionId_] + units_;
        emit TransferUnits(address(0), minter_, 0, optionId_, units_);
    }

    function _mint(
        uint256 optionID,
        address minter_,
        uint256 slot_
    ) internal virtual {
        optionSlotMapping[optionID] = slot_;
        _mintUnits(minter_, optionID, slot_, maxUnits);
    }

    function _modifyOption(
        uint256 optionID,
        Option memory option,
        uint256 lockedAmount,
        uint256 amount,
        uint256 premium
    ) internal virtual returns (Option memory modifiedOption) {
        option.lockedAmount = lockedAmount;
        option.amount = amount;
        option.premium = premium;
        modifiedOption = option;
        _setOption(optionID, option);
    }

    function split(uint256 optionID, uint256[] calldata splitUnits_)
        public
        virtual
        returns (uint256[] memory newOptionIDs)
    {
        require(splitUnits_.length > 0, "Empty splitUnits");
        newOptionIDs = new uint256[](splitUnits_.length);
        Option memory option = _getOption(optionID);
        uint256 amountUnits = option.amount / units[optionID];
        uint256 premiumUnits = option.premium / units[optionID];
        uint256 lockedAmountUnits = option.lockedAmount / units[optionID];
        for (uint256 i = 0; i < splitUnits_.length; i++) {
            uint256 newOptionID = _generateTokenId();
            newOptionIDs[i] = newOptionID;
            optionSlotMapping[newOptionID] = optionSlotMapping[optionID];
            _split(optionID, newOptionID, splitUnits_[i]);

            uint256 newAmount = amountUnits * splitUnits_[i];
            uint256 newPremium = premiumUnits * splitUnits_[i];
            uint256 newLockedAmount = lockedAmountUnits * splitUnits_[i];

            Option memory newOption = Option(
                option.state,
                option.strike,
                newAmount,
                newLockedAmount,
                newPremium,
                option.expiration,
                option.optionType
            );

            _setOption(newOptionID, newOption);
            _setOptionBlock(newOptionID);
            option = _modifyOption(
                optionID,
                option,
                option.lockedAmount - newLockedAmount,
                option.amount - newAmount,
                option.premium - newPremium
            );
            pool.lockChange(optionID, option.lockedAmount, option.premium);
            approve_token(address(pool), newOption.premium);
            pool.lock(newOptionID, newOption.lockedAmount, newOption.premium);
        }
    }

    function _split(
        uint256 optionId_,
        uint256 newOptionId_,
        uint256 splitUnits_
    ) internal virtual {
        require(
            _isApprovedOrOwner(_msgSender(), optionId_),
            "NFT: not owner nor approved"
        );
        require(!_exists(newOptionId_), "new token already exists");
        units[optionId_] = units[optionId_] - splitUnits_;

        address owner = ownerOf(optionId_);
        _mintUnits(owner, newOptionId_, _slotOf(optionId_), splitUnits_);

        emit Split(owner, optionId_, newOptionId_, splitUnits_);
    }

    function merge(uint256[] calldata optionIDs, uint256 targetOptionID)
        public
        virtual
    {
        require(optionIDs.length > 0, "Empty optionIDs");
        Option memory targetOption = _getOption(targetOptionID);

        uint256 totalLockedAmount = targetOption.lockedAmount;
        uint256 totalAmount = targetOption.amount;
        uint256 totalPremium = targetOption.premium;

        for (uint256 i = 0; i < optionIDs.length; i++) {
            Option memory option = _getOption(optionIDs[i]);
            totalLockedAmount = totalLockedAmount + option.lockedAmount;
            totalAmount = totalAmount + option.amount;
            totalPremium = totalPremium + option.premium;
            pool.unlockWithoutProfit(optionIDs[i]);
            BufferNFTCore._merge(optionIDs[i], targetOptionID);
            delete optionSlotMapping[optionIDs[i]];
        }
        _modifyOption(
            targetOptionID,
            targetOption,
            totalLockedAmount,
            totalAmount,
            totalPremium
        );
        pool.lockChange(targetOptionID, totalLockedAmount, totalPremium);
    }

    function _merge(uint256 optionId_, uint256 targetOptionId_)
        internal
        virtual
    {
        require(
            _isApprovedOrOwner(_msgSender(), optionId_),
            "NFT: not owner nor approved"
        );
        require(optionId_ != targetOptionId_, "self merge not allowed");
        require(
            _slotOf(optionId_) == _slotOf(targetOptionId_),
            "slot mismatch"
        );

        address owner = ownerOf(optionId_);
        require(owner == ownerOf(targetOptionId_), "not same owner");

        uint256 mergeUnits = units[optionId_];
        units[targetOptionId_] = mergeUnits + units[targetOptionId_];
        _burn(optionId_);

        emit Merge(owner, optionId_, targetOptionId_, mergeUnits);
    }

    function _transferUnitsFrom(
        address from_,
        address to_,
        uint256 optionId_,
        uint256 targetOptionId_,
        uint256 transferUnits_
    ) internal virtual {
        require(from_ == ownerOf(optionId_), "source token owner mismatch");
        require(to_ != address(0), "transfer to the zero address");
        _beforeTransferUnits(
            from_,
            to_,
            optionId_,
            targetOptionId_,
            transferUnits_
        );

        if (_msgSender() != from_ && !isApprovedForAll(from_, _msgSender())) {
            _tokenApprovalUnits[optionId_].allowances[_msgSender()] =
                _tokenApprovalUnits[optionId_].allowances[_msgSender()] -
                transferUnits_;
        }

        units[optionId_] = units[optionId_] - transferUnits_;

        if (!_exists(targetOptionId_)) {
            _mintUnits(
                to_,
                targetOptionId_,
                _slotOf(optionId_),
                transferUnits_
            );
        } else {
            require(
                ownerOf(targetOptionId_) == to_,
                "target token owner mismatch"
            );
            require(
                _slotOf(optionId_) == _slotOf(targetOptionId_),
                "slot mismatch"
            );
            units[targetOptionId_] = units[targetOptionId_] + transferUnits_;
        }
        optionSlotMapping[targetOptionId_] = optionSlotMapping[optionId_];

        emit TransferUnits(
            from_,
            to_,
            optionId_,
            targetOptionId_,
            transferUnits_
        );
    }

    /**
     * @notice Transfer part of units of a nft to target address.
     * @param from_ Address of the nft sender
     * @param to_ Address of the nft recipient
     * @param optionID Id of the nft to transfer
     * @param transferUnits_ Amount of units to transfer
     */
    function transferFrom(
        address from_,
        address to_,
        uint256 optionID,
        uint256 transferUnits_
    ) public virtual returns (uint256 newOptionID) {
        Option memory option = _getOption(optionID);
        newOptionID = _generateTokenId();
        uint256 newAmount = (option.amount / units[optionID]) * transferUnits_;
        uint256 newPremium = (option.premium / units[optionID]) *
            transferUnits_;
        uint256 newLockedAmount = (option.lockedAmount / units[optionID]) *
            transferUnits_;
        Option memory newOption = Option(
            option.state,
            option.strike,
            newAmount,
            newLockedAmount,
            newPremium,
            option.expiration,
            option.optionType
        );
        _setOption(newOptionID, newOption);
        option = _modifyOption(
            optionID,
            option,
            option.lockedAmount - newLockedAmount,
            option.amount - newAmount,
            option.premium - newPremium
        );
        pool.lockChange(optionID, option.lockedAmount, option.premium);
        approve_token(address(pool), newPremium);
        pool.lock(newOptionID, newLockedAmount, newPremium);
        _transferUnitsFrom(from_, to_, optionID, newOptionID, transferUnits_);
    }

    /**
     * @notice Transfer part of units of a nft to another nft.
     * @param from_ Address of the nft sender
     * @param to_ Address of the nft recipient
     * @param optionID Id of the nft to transfer
     * @param targetOptionID Id of the nft to receive
     * @param transferUnits_ Amount of units to transfer
     */
    function transferFrom(
        address from_,
        address to_,
        uint256 optionID,
        uint256 targetOptionID,
        uint256 transferUnits_
    ) public virtual {
        require(_exists(targetOptionID), "target token not exists");
        Option memory option = _getOption(optionID);
        uint256 newAmount = (option.amount / units[optionID]) * transferUnits_;
        uint256 newPremium = (option.premium / units[optionID]) *
            transferUnits_;
        uint256 newLockedAmount = (option.lockedAmount / units[optionID]) *
            transferUnits_;
        Option memory targetOption = _getOption(targetOptionID);
        targetOption = _modifyOption(
            targetOptionID,
            targetOption,
            targetOption.lockedAmount + newLockedAmount,
            targetOption.amount + newAmount,
            targetOption.premium + newPremium
        );
        option = _modifyOption(
            optionID,
            option,
            option.lockedAmount - newLockedAmount,
            option.amount - newAmount,
            option.premium - newPremium
        );
        pool.lockChange(optionID, option.lockedAmount, option.premium);
        pool.lockChange(
            targetOptionID,
            targetOption.lockedAmount,
            targetOption.premium
        );
        _transferUnitsFrom(
            from_,
            to_,
            optionID,
            targetOptionID,
            transferUnits_
        );
    }

    function _safeTransferUnitsFrom(
        address from_,
        address to_,
        uint256 tokenId_,
        uint256 targetTokenId_,
        uint256 transferUnits_,
        bytes memory data_
    ) internal virtual {
        _transferUnitsFrom(
            from_,
            to_,
            tokenId_,
            targetTokenId_,
            transferUnits_
        );
        require(
            _checkOnNFTReceived(
                from_,
                to_,
                targetTokenId_,
                transferUnits_,
                data_
            ),
            "to non NFTReceiver implementer"
        );
    }

    function safeTransferFrom(
        address from_,
        address to_,
        uint256 tokenId_,
        uint256 transferUnits_,
        bytes memory data_
    ) public virtual returns (uint256 newTokenId) {
        newTokenId = transferFrom(from_, to_, tokenId_, transferUnits_);
        require(
            _checkOnNFTReceived(from_, to_, newTokenId, transferUnits_, data_),
            "to non NFTReceiver"
        );
        return newTokenId;
    }

    // function safeTransferFrom(
    //     address from_,
    //     address to_,
    //     uint256 tokenId_,
    //     uint256 targetTokenId_,
    //     uint256 transferUnits_,
    //     bytes memory data_
    // ) public virtual {
    //     transferFrom(from_, to_, tokenId_, targetTokenId_, transferUnits_);
    //     require(
    //         _checkOnNFTReceived(
    //             from_,
    //             to_,
    //             targetTokenId_,
    //             transferUnits_,
    //             data_
    //         ),
    //         "to non NFTReceiver"
    //     );
    // }


    function getSlotDetail(uint256 slot_)
        internal
        view
        returns (SlotDetail memory)
    {
        return slotDetails[slot_];
    }

    function getSlot(
        uint256 strike,
        uint256 expiration,
        OptionType optionType,
        uint256 optionID
    ) public pure returns (uint256) {
        return
            uint256(
                keccak256(abi.encode(strike, expiration, optionType, optionID))
            );
    }

    function createSlot(uint256 optionID) internal returns (uint256 slot) {
        Option memory option = _getOption(optionID);
        slot = getSlot(
            option.strike,
            option.expiration,
            option.optionType,
            optionID
        );
        require(!slotDetails[slot].isValid, "slot already existed");
        slotDetails[slot] = SlotDetail(
            option.strike,
            option.expiration,
            option.optionType,
            true
        );
    }

    function _burnUnits(uint256 optionId_, uint256 burnUnits_)
        internal
        virtual
        returns (uint256 balance)
    {
        address owner = ownerOf(optionId_);
        units[optionId_] = units[optionId_] - burnUnits_;

        emit TransferUnits(owner, address(0), optionId_, 0, burnUnits_);
        return units[optionId_];
    }

    function _burn(uint256 optionId_)
        internal
        virtual
        override(ERC721, ERC721URIStorage)
    {
        address owner = ownerOf(optionId_);
        uint256 slot = _slotOf(optionId_);
        uint256 burnUnits = units[optionId_];

        _slotTokens[slot].remove(optionId_);
        delete units[optionId_];

        ERC721._burn(optionId_);
        emit TransferUnits(owner, address(0), optionId_, 0, burnUnits);
    }

    function approve(
        address to_,
        uint256 optionId_,
        uint256 allowance_
    ) public virtual {
        require(_msgSender() == ownerOf(optionId_), "NFT: only owner");
        _approveUnits(to_, optionId_, allowance_);
    }

    function allowance(uint256 optionId_, address spender_)
        public
        view
        virtual
        returns (uint256)
    {
        return _tokenApprovalUnits[optionId_].allowances[spender_];
    }

    /**
     * @dev Approve `to_` to operate on `optionId_` within range of `allowance_`
     */
    function _approveUnits(
        address to_,
        uint256 optionId_,
        uint256 allowance_
    ) internal virtual {
        if (_tokenApprovalUnits[optionId_].allowances[to_] == 0) {
            _tokenApprovalUnits[optionId_].approvals.push(to_);
        }
        _tokenApprovalUnits[optionId_].allowances[to_] = allowance_;
        emit ApprovalUnits(to_, optionId_, allowance_);
    }

    /**
     * @dev Clear existing approveUnits for `optionId_`, including approved addresses and their approved units.
     */
    function _clearApproveUnits(uint256 optionId_) internal virtual {
        ApproveUnits storage approveUnits = _tokenApprovalUnits[optionId_];
        for (uint256 i = 0; i < approveUnits.approvals.length; i++) {
            delete approveUnits.allowances[approveUnits.approvals[i]];
            delete approveUnits.approvals[i];
        }
    }

    function unitDecimals() public view returns (uint8) {
        return _unitDecimals;
    }

    function unitsInSlot(uint256 slot_) public view returns (uint256 units_) {
        for (uint256 i = 0; i < tokensInSlot(slot_); i++) {
            units_ = units_ + unitsInToken(tokenOfSlotByIndex(slot_, i));
        }
    }

    function unitsInToken(uint256 optionId_)
        public
        view
        virtual
        returns (uint256)
    {
        return units[optionId_];
    }

    function tokensInSlot(uint256 slot_) public view returns (uint256) {
        return _slotTokens[slot_].length();
    }

    function tokenOfSlotByIndex(uint256 slot_, uint256 index_)
        public
        view
        returns (uint256)
    {
        return _slotTokens[slot_].at(index_);
    }

    function slotOf(uint256 optionId_) public view returns (uint256) {
        return _slotOf(optionId_);
    }

    function _slotOf(uint256 optionID) internal view virtual returns (uint256) {
        return optionSlotMapping[optionID];
    }

    /**
     * @dev Before transferring or burning a token, the existing approveUnits should be cleared.
     */
    function _beforeTokenTransfer(
        address from_,
        address to_,
        uint256 optionId_
    ) internal virtual override {
        if (from_ != address(0)) {
            _clearApproveUnits(optionId_);
        }
    }

    function _generateTokenId() internal virtual returns (uint256);

    function approve_token(address receipent, uint256 amount) public virtual;

    function _getOption(uint256 optionId_)
        internal
        view
        virtual
        returns (Option memory);

    function _setOption(uint256 optionId_, Option memory option)
        internal
        virtual;

    function _setOptionBlock(uint256 optionId_) internal virtual;

    function _beforeTransferUnits(
        address from_,
        address to_,
        uint256 optionId_,
        uint256 targetOptionId_,
        uint256 transferUnits_
    ) internal virtual {}

    function supportsInterface(bytes4 interfaceId)
        public
        view
        override(ERC721, AccessControl)
        returns (bool)
    {
        return super.supportsInterface(interfaceId);
    }

    /**
     * @dev Template code provided by OpenZepplin Code Wizard
     */
    function _setTokenURI(uint256 tokenId, string memory _tokenURI)
        internal
        override
    {
        return super._setTokenURI(tokenId, _tokenURI);
    }

    /**
     * @dev Template code provided by OpenZepplin Code Wizard
     */
    function _baseURI() internal pure override returns (string memory) {
        return "https://gateway.pinata.cloud/ipfs/";
    }

    /**
     * @dev Template code provided by OpenZepplin Code Wizard
     */
    function tokenURI(uint256 tokenId)
        public
        view
        override(ERC721, ERC721URIStorage)
        returns (string memory)
    {
        return super.tokenURI(tokenId);
    }

    function _checkOnNFTReceived(
        address from_,
        address to_,
        uint256 tokenId_,
        uint256 units_,
        bytes memory _data
    ) internal returns (bool) {
        if (!to_.isContract()) {
            return true;
        }
        bytes memory returndata = to_.functionCall(
            abi.encodeWithSelector(
                INFTReceiver(to_).onNFTReceived.selector,
                _msgSender(),
                from_,
                tokenId_,
                units_,
                _data
            ),
            "non NFTReceiver implementer"
        );
        bytes4 retval = abi.decode(returndata, (bytes4));
        /*b382cdcd  =>  onNFTReceived(address,address,uint256,uint256,bytes)*/
        return (retval == type(INFTReceiver).interfaceId);
    }

}
