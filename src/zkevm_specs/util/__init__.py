from typing import Union
from Crypto.Random import get_random_bytes
from Crypto.Random.random import randrange

from .arithmetic import *
from .constraint_system import *
from .hash import *
from .param import *
from .typing import *
from .testing import memory_expansion, memory_word_size


def rand_range(stop: Union[int, float] = 2**256) -> int:
    return randrange(0, int(stop))


def rand_fq() -> FQ:
    return FQ(rand_range(FQ.field_modulus))


def rand_address() -> U160:
    return U160(rand_range(2**160))


def rand_word() -> U256:
    return U256(rand_range(2**256))


def rand_bytes(n_bytes: int = 32) -> bytes:
    return get_random_bytes(n_bytes)
