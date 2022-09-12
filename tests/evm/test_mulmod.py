import pytest

from typing import Optional
from zkevm_specs.evm import (
    ExecutionState,
    StepState,
    verify_steps,
    Tables,
    Block,
    Bytecode,
    RWDictionary,
)
from zkevm_specs.util import rand_fq, RLC

MAXU256 = (2**256) - 1


TESTING_DATA = [
    (1, 1, 2),
    (1, 1, 0),
    (0, 2, 3),
    (MAXU256, MAXU256, MAXU256),
    (MAXU256, MAXU256, 1),
    (MAXU256, 1, MAXU256),
    (MAXU256, 2, 2),
    (0, 0, 0),
]


@pytest.mark.parametrize("a, b, n", TESTING_DATA)
def test_mulmod(a: int, b: int, n: int):
    randomness = rand_fq()

    if n == 0:
        r = RLC(0, randomness)
    else:
        r = RLC((a * b) % n, randomness)

    a = RLC(a, randomness)
    b = RLC(b, randomness)
    n = RLC(n, randomness)

    bytecode = Bytecode().mulmod(a, b, n).stop()
    bytecode_hash = RLC(bytecode.hash(), randomness)

    tables = Tables(
        block_table=set(Block().table_assignments(randomness)),
        tx_table=set(),
        bytecode_table=set(bytecode.table_assignments(randomness)),
        rw_table=set(
            RWDictionary(9)
            .stack_read(1, 1021, a)
            .stack_read(1, 1022, b)
            .stack_read(1, 1023, n)
            .stack_write(1, 1023, r)
            .rws
        ),
    )

    verify_steps(
        randomness=randomness,
        tables=tables,
        steps=[
            StepState(
                execution_state=ExecutionState.MULMOD,
                rw_counter=9,
                call_id=1,
                is_root=True,
                is_create=False,
                code_hash=bytecode_hash,
                program_counter=99,
                stack_pointer=1021,
                gas_left=8,
            ),
            StepState(
                execution_state=ExecutionState.STOP,
                rw_counter=13,
                call_id=1,
                is_root=True,
                is_create=False,
                code_hash=bytecode_hash,
                program_counter=100,
                stack_pointer=1023,
                gas_left=0,
            ),
        ],
    )
