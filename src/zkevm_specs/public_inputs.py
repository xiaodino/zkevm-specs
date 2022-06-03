from dataclasses import dataclass
from typing import NamedTuple, Tuple, List, Sequence, Set, Union, cast
from enum import IntEnum
from math import log, ceil
from functools import reduce

from .util import FQ, RLC, U64, U160, U256, Expression
from .encoding import U8, is_circuit_code
from .evm import (
    RW,
    AccountFieldTag,
    CallContextFieldTag,
    TxLogFieldTag,
    TxReceiptFieldTag,
    MPTTableRow,
    MPTTableTag,
    lookup,
)

BLOCK_LEN = 7 + 256  # Length of block public data
EXTRA_LEN = 2 # Length of fields that don't belong to any table
TX_LEN = 11 # Length of tx public data (without calldata)

@dataclass
class BlockTableRow():
    value: FQ

@dataclass
class TxTableRow():
    tx_id: FQ
    tag: FQ
    index: FQ
    value: FQ

class Row(NamedTuple):
    """
    PublicInputs circuit row
    """

    block_table: BlockTableRow
    tx_table: TxTableRow

    raw_public_inputs: FQ
    rpi_rlc_acc: FQ  # raw_public_inputs accumulated RLC from bottom to top
    rand_rpi: FQ

    q_end: FQ

class PublicInputs(NamedTuple):
    """
    Public Inputs of the PublicInputs circuit
    """

    rand_rpi: FQ  # randomness used in the RLC of the raw_public_inputs
    rpi_rlc: FQ  # raw_public_inputs RLC encoded

    chain_id: FQ
    state_root: FQ
    state_root_prev: FQ

@is_circuit_code
def check_row(row: Row, row_next: Row):

    q_not_end = (1 - row.q_end)

    # 0.0 rpi_rlc_acc[0] == RLC(raw_public_inputs, rand_rpi)
    assert row.rpi_rlc_acc == q_not_end * row_next.rpi_rlc_acc * row.rand_rpi + row.raw_public_inputs

    # 0.1 rand_rpi[i] == rand_rpi[j]
    assert q_not_end * row.rand_rpi == q_not_end * row_next.rand_rpi


@dataclass
class Witness():
    rows: List[Row]  # PublicInputs rows
    public_inputs: PublicInputs  # Public Inputs of the PublicInputs circuit

@is_circuit_code
def verify_circuit(
    witness: Witness,
    MAX_TXS: int,
    MAX_CALLDATA_BYTES: int,
) -> None:
    """
    Entry level circuit verification function
    """

    rows = witness.rows

    # 1.0 rand_rpi copy constraint from public input to advice column
    assert rows[0].rand_rpi == witness.public_inputs.rand_rpi

    # 1.1 rpi_rlc copy constraint from public input to advice column
    assert rows[0].rpi_rlc_acc == witness.public_inputs.rpi_rlc

    for i in range(len(rows)-1):
        row = rows[i]
        row_next = rows[i+1]
        check_row(row, row_next)

@dataclass
class Block:
    hash: U256
    parent_hash: U256
    uncle_hash: U256
    coinbase: U160
    root: U256 # State Trie Root
    tx_hash: U256 # Txs Trie Root
    receipt_hash: U256 # Receipts Trie Root
    bloom: bytes # 256 bytes
    difficulty: U256
    number: U64
    gas_limit: U64
    gas_used: U64
    time: U64
    extra: bytes # NOTE: We assume this is always an empty byte array
    mix_digest: U256
    nonce: U64
    base_fee: U256 # NOTE: BaseFee was added by EIP-1559 and is ignored in legacy headers.


@dataclass
class Transaction:
    nonce: U64
    gas_price: U256
    gas: U64
    from_addr: U160
    to_addr: U160
    value: U256
    data: bytes
    tx_sign_hash: U256

    @classmethod
    def default(cls):
        return Transaction(U64(0), U256(0), U64(0), U160(0), U160(0), U256(0), bytes([]), U256(0))

@dataclass
class PublicData:
    chain_id: U64
    block: Block
    block_prev_root: U256
    block_hashes: List[U256] # 256 previous block hashes
    txs: List[Transaction]

def linear_combine(seq: Sequence[FQ], base: FQ) -> FQ:
    def accumulate(acc: FQ, v: FQ) -> FQ:
        return acc * base + FQ(v)

    return reduce(accumulate, reversed(seq), FQ(0))

def public_data2witness(public_data: PublicData, MAX_TXS: int, MAX_CALLDATA_BYTES: int, rand_rpi: FQ) -> Witness:
    raw_public_inputs = []

    # Block table
    raw_public_inputs.append(FQ(public_data.block.coinbase)) # offset = 0
    raw_public_inputs.append(FQ(public_data.block.gas_limit))
    raw_public_inputs.append(FQ(public_data.block.number))
    raw_public_inputs.append(FQ(public_data.block.time))
    raw_public_inputs.append(FQ(public_data.block.difficulty))
    raw_public_inputs.append(FQ(public_data.block.base_fee))
    raw_public_inputs.append(FQ(public_data.chain_id))
    assert len(public_data.block_hashes) == 256
    for block_hash in public_data.block_hashes:
        raw_public_inputs.append(FQ(block_hash)) # offset = 7

    # Extra fields
    raw_public_inputs.append(FQ(public_data.block.hash)) # offset = BLOCK_LEN
    raw_public_inputs.append(FQ(public_data.block_prev_root))

    # Tx Table, fields except for calldata
    tx_id_col = []
    index_col = []
    value_col = []
    assert len(public_data.txs) <= MAX_TXS
    calldata_len = 0
    for i in range(MAX_TXS):
        tx = Transaction.default()
        if i < len(public_data.txs):
            tx = public_data.txs

        tx_id_col.extend([FQ(i+1)] * 11)
        index_col.extend([FQ(0)] * 11)
        value_col.append(FQ(tx.nonce))
        value_col.append(FQ(tx.gas))
        value_col.append(FQ(tx.gas_price))
        value_col.append(FQ(0)) # GasTipCap
        value_col.append(FQ(0)) # GasFeeCap
        value_col.append(FQ(tx.from_addr))
        value_col.append(FQ(tx.to_addr))
        value_col.append(FQ(1 if tx.to_addr == FQ(0) else 0))
        value_col.append(FQ(tx.value))
        value_col.append(FQ(len(tx.data)))
        value_col.append(FQ(tx.tx_sign_hash))

        calldata_len += len(tx.data)

    # Tx Table -> calldata
    assert calldata_len <= MAX_CALLDATA_BYTES
    for i, tx in enumerate(public_data.txs):
        for byte_index, byte in enumerate(tx.data):
            tx_id_col.append(FQ(i+1))
            index_col.append(FQ(byte_index))
            value_col.append(FQ(byte))

    calldata_padding = [FQ(0)] * (MAX_CALLDATA_BYTES - calldata_len)
    tx_id_col.extend(calldata_padding)
    index_col.extend(calldata_padding)
    value_col.extend(calldata_padding)

    raw_public_inputs.extend(tx_id_col) # offset = BLOCK_LEN + EXTRA_LEN
    raw_public_inputs.extend(index_col) # offset += (TX_LEN * MAX_TXS + MAX_CALLDATA_BYTES)
    raw_public_inputs.extend(value_col) # offset += (TX_LEN * MAX_TXS + MAX_CALLDATA_BYTES)

    assert len(raw_public_inputs) == BLOCK_LEN + EXTRA_LEN + 3 * (TX_LEN * MAX_TXS + MAX_CALLDATA_BYTES)
    rpi_rlc = linear_combine(raw_public_inputs, rand_rpi)

    rpi_rlc_acc_col = [raw_public_inputs[-1]]
    for i in reversed(range(1, len(raw_public_inputs))):
        rpi_rlc_acc_col.append(rpi_rlc_acc_col[-1] * rand_rpi + raw_public_inputs[i])
    rpi_rlc_acc_col = list(reversed(rpi_rlc_acc_col))

    rows = []
    for i in range(len(raw_public_inputs)):
        q_end = FQ(1) if i == len(raw_public_inputs)-1  else FQ(0)
        block_row = BlockTableRow(FQ(0))
        if i < BLOCK_LEN:
            block_row = BlockTableRow(raw_public_inputs[0 + i])
        tx_row = TxTableRow(FQ(0), FQ(0), FQ(0), FQ(0))
        if i < TX_LEN * MAX_TXS + MAX_CALLDATA_BYTES:
            tx_id = FQ(0) # TODO
            tag = pass # TODO
            index = FQ(0)# TODO
            value = FQ(0)# TODO
            tx_row = TxTableRow(tx_id, tag, index, value)
        rows.append(Row(block_row, tx_row, raw_public_inputs[i], rpi_rlc_acc_col[i], rand_rpi, q_end))

    public_inputs = PublicInputs(rand_rpi, rpi_rlc, FQ(public_data.chain_id),
            FQ(public_data.block.root), FQ(public_data.block_prev_root))
    return Witness(rows, public_inputs)
