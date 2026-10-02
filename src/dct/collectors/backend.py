"""Compatibility names for the normalized executor boundary."""

from dct.executors import SAFE_PATH as SAFE_PATH
from dct.executors import Executor as Backend
from dct.executors import FixtureExecutor as FixtureBackend
from dct.executors import LocalExecutor as LinuxBackend

__all__ = ["Backend", "FixtureBackend", "LinuxBackend", "SAFE_PATH"]
