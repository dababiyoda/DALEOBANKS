"""Minimal stub of python-dotenv for testing."""

from __future__ import annotations

from typing import Optional


def load_dotenv(path: Optional[str] = None, verbose: bool = False, override: bool = False) -> bool:
    """Pretend to load environment variables from a .env file.

    The real library reads environment files.  For the purposes of the
    tests we simply return ``False`` to indicate that no file was loaded.
    """

    return False
