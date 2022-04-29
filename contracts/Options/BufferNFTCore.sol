pragma solidity ^0.8.0;

// SPDX-License-Identifier: BUSL-1.1

import "@openzeppelin/contracts/token/ERC721/ERC721.sol";

import "@openzeppelin/contracts/utils/structs/EnumerableSet.sol";
import "../Interfaces/Interfaces.sol";
import "@openzeppelin/contracts/access/AccessControl.sol";
import "@openzeppelin/contracts/token/ERC721/extensions/ERC721URIStorage.sol";

abstract contract BufferNFTCore is
    ERC721,
    IBufferOptions,
    AccessControl,
    ERC721URIStorage
{
    using EnumerableSet for EnumerableSet.UintSet;
    using Address for address;

    /// @dev optionId => units
    mapping(uint256 => uint256) public optionSlotMapping;

    /// @dev optionId => operator => units
    mapping(uint256 => ApproveUnits) private _tokenApprovalUnits;

    /// @dev slot => optionIds
    mapping(uint256 => EnumerableSet.UintSet) private _slotTokens;

    uint256 public maxUnits = 1e6;
    uint8 internal _unitDecimals = 18;
    mapping(uint256 => uint256) public _units;

    constructor() ERC721("Buffer", "BFR") {
        _setupRole(DEFAULT_ADMIN_ROLE, msg.sender);
    }

    function _mintUnits(
        address minter_,
        uint256 optionId_,
        uint256 slot_,
        uint256 units_
    ) internal {
        if (!_exists(optionId_)) {
            _mint(minter_, optionId_);
            _slotTokens[slot_].add(optionId_);
        }

        _units[optionId_] = _units[optionId_] + units_;
        emit TransferUnits(address(0), minter_, 0, optionId_, units_);
    }

    function _mint(
        uint256 optionID,
        address minter_,
        uint256 slot_
    ) internal {
        optionSlotMapping[optionID] = slot_;
        _mintUnits(minter_, optionID, slot_, maxUnits);
    }

    function _split(
        uint256 optionId_,
        uint256 newOptionId_,
        uint256 splitUnits_
    ) internal {
        require(_isApprovedOrOwner(_msgSender(), optionId_), "N2");
        require(!_exists(newOptionId_), "N3");
        setSlotOf(newOptionId_, slotOf(optionId_));
        _units[optionId_] = _units[optionId_] - splitUnits_;

        address owner = ownerOf(optionId_);
        _mintUnits(owner, newOptionId_, slotOf(optionId_), splitUnits_);

        emit Split(owner, optionId_, newOptionId_, splitUnits_);
    }

    function _merge(uint256 optionId_, uint256 targetOptionId_) internal {
        require(_isApprovedOrOwner(_msgSender(), optionId_), "N5");
        require(optionId_ != targetOptionId_, "N6");
        require(slotOf(optionId_) == slotOf(targetOptionId_), "N7");

        address owner = ownerOf(optionId_);
        require(owner == ownerOf(targetOptionId_), "N8");

        uint256 mergeUnits = _units[optionId_];
        _units[targetOptionId_] = mergeUnits + _units[targetOptionId_];
        burnToken(optionId_);

        emit Merge(owner, optionId_, targetOptionId_, mergeUnits);
    }

    function _transferUnitsFrom(
        address from_,
        address to_,
        uint256 optionId_,
        uint256 targetOptionId_,
        uint256 transferUnits_
    ) internal {
        require(from_ == ownerOf(optionId_), "N9");
        require(to_ != address(0), "N10");
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

        _units[optionId_] = _units[optionId_] - transferUnits_;

        if (!_exists(targetOptionId_)) {
            _mintUnits(to_, targetOptionId_, slotOf(optionId_), transferUnits_);
        } else {
            require(ownerOf(targetOptionId_) == to_, "N11");
            require(slotOf(optionId_) == slotOf(targetOptionId_), "N7");
            _units[targetOptionId_] = _units[targetOptionId_] + transferUnits_;
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
     * @dev See EIP-165: ERC-165 Standard Interface Detection
     * https://eips.ethereum.org/EIPS/eip-165
     **/

    function burnToken(uint256 optionID) internal {
        delete optionSlotMapping[optionID];
        _burn(optionID);
    }

    function _burnUnits(uint256 optionId_, uint256 burnUnits_)
        internal
        returns (uint256 balance)
    {
        address owner = ownerOf(optionId_);
        _units[optionId_] = _units[optionId_] - burnUnits_;

        emit TransferUnits(owner, address(0), optionId_, 0, burnUnits_);
        return _units[optionId_];
    }

    function _burn(uint256 optionId_)
        internal
        override(ERC721, ERC721URIStorage)
    {
        address owner = ownerOf(optionId_);
        uint256 slot = slotOf(optionId_);
        uint256 burnUnits = _units[optionId_];

        _slotTokens[slot].remove(optionId_);
        delete _units[optionId_];

        ERC721._burn(optionId_);
        emit TransferUnits(owner, address(0), optionId_, 0, burnUnits);
    }

    function approve(
        address to_,
        uint256 optionId_,
        uint256 allowance_
    ) public {
        require(_msgSender() == ownerOf(optionId_), "O9");
        _approveUnits(to_, optionId_, allowance_);
    }

    function allowance(uint256 optionId_, address spender_)
        public
        view
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
    ) internal {
        if (_tokenApprovalUnits[optionId_].allowances[to_] == 0) {
            _tokenApprovalUnits[optionId_].approvals.push(to_);
        }
        _tokenApprovalUnits[optionId_].allowances[to_] = allowance_;
        emit ApprovalUnits(to_, optionId_, allowance_);
    }

    /**
     * @dev Clear existing approveUnits for `optionId_`, including approved addresses and their approved units.
     */
    function _clearApproveUnits(uint256 optionId_) internal {
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

    function unitsInToken(uint256 optionId_) public view returns (uint256) {
        return _units[optionId_];
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
        return optionSlotMapping[optionId_];
    }

    function exists(uint256 optionID) public view returns (bool) {
        return _exists(optionID);
    }

    function setSlotOf(uint256 optionID, uint256 _slot) internal {
        optionSlotMapping[optionID] = _slot;
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

    function _beforeTransferUnits(
        address from_,
        address to_,
        uint256 optionId_,
        uint256 targetOptionId_,
        uint256 transferUnits_
    ) internal {}

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
}
