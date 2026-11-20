"""Top-level package for mar_dss."""

from importlib.metadata import PackageNotFoundError, version

__author__ = """Ayman H. Alzraiee"""
__email__ = "aalzraiee@gsi-net.com"

try:
    # The version in pyproject.toml.
    __version__ = version("mar_dss")
except PackageNotFoundError:
    __version__ = "dev"
