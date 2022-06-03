import traceback
from typing import Union, List
from eth_keys import keys
from eth_utils import keccak
import rlp
from zkevm_specs.public_inputs import *
from zkevm_specs.util import rand_fq, FQ, RLC, U64

randomness = rand_fq()
rand_rpi = randomness  # Simulate a randomness for now


def verify(
    public_data_or_witness: Union[PublicData, Witness]
    MAX_TXS: int,
    MAX_CALLDATA_BYTES: int,
    rand_rpi: FQ,
    success: bool = True,
):
    """
    Verify the circuit with the assigned witness (or the witness calculated
    from the PublicData).  If `success` is False, expect the verification to
    fail.
    """
    witness = public_data_or_witness
    if isinstance(public_data_or_witness, Witness):
        pass
    else:
        witness = public_data2witness(public_data_or_witness, MAX_TXS, MAX_CALLDATA_BYTES, rand_rpi)
    # assert len(witness.rows) == MAX_TXS * Tag.TxSignHash + MAX_CALLDATA_BYTES
    # assert len(witness.sign_verifications) == MAX_TXS
    ok = True
    if success:
        verify_circuit(
            witness,
            MAX_TXS,
            MAX_CALLDATA_BYTES,
        )
    else:
        try:
            verify_circuit(
                witness,
                MAX_TXS,
                MAX_CALLDATA_BYTES,
            )
        except AssertionError as e:
            ok = False
    assert ok == success

