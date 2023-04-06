# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Manage machine NFS mounts and dependencies."""

import logging
import os
import pathlib
import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import List, Optional, Tuple, Union
from urllib.parse import urlparse

import charms.operator_libs_linux.v0.apt as apt

_logger = logging.getLogger(__name__)
_nfs_url_check = re.compile(
    r"""
        nfs://[-a-zA-Z0-9@:%._+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b([-a-zA-Z0-9()!@:%_+.~#?&/=]*)
    """,
    re.VERBOSE,
)
_mount_parser = re.compile(
    r"""
        ^(?P<endpoint>\S+?)\s+
        (?P<mountpoint>\S+?)\s
        (?P<fstype>nfs\S*?)\s
        (?P<options>\S+?)\s
        (?P<freq>\d+?)\s+
        (?P<passno>\d+)
    """,
    re.VERBOSE,
)


class Error(Exception):
    """Raise if NFS client manager encounters an error."""

    @property
    def name(self):
        """Get a string representation of the error plus class name."""
        return f"<{type(self).__module__}.{type(self).__name__}>"

    @property
    def message(self):
        """Return the message passed as an argument."""
        return self.args[0]

    def __repr__(self):
        """String representation of the error."""
        return f"<{type(self).__module__}.{type(self).__name__} {self.args}>"


@dataclass(frozen=True)
class MountInfo:
    """NFS mount information.

    Notes:
        See `man fstab` for description of field types.
    """

    endpoint: str
    mountpoint: str
    fstype: str
    options: str
    freq: str
    passno: str


def _translate(url: str) -> Tuple[str, str]:
    """Translate an NFS URL to a mount.nfs endpoint.

    Args:
        url: NFS uniform resource locator (URL)

    Returns:
        Tuple[str, str]: `mount.nfs`-understandable endpoint and port number.
    """
    _logger.debug(f"Converting NFS URL {url} to `mount.nfs` format")
    nfs_url = urlparse(url)
    return f"{nfs_url.hostname}:{nfs_url.path}", nfs_url.port


def install() -> None:
    """Install NFS utilities for mounting NFS shares.

    Raises:
        Error: Raised if operation to install NFS common package fails.
    """
    _logger.debug("Installing `nfs-common` package from apt archive")
    try:
        apt.update()
        apt.add_package("nfs-common")
    except (apt.PackageError, apt.PackageNotFoundError) as e:
        _logger.error(f"Failed to install `nfs-common` package. Reason\n:{e.message}")
        raise Error(e.message)


def remove() -> None:
    """Remove NFS utilities for mounting NFS shares."""
    _logger.debug("Removing `nfs-common` package from system packages")
    try:
        apt.remove_package("nfs-common")
    except apt.PackageNotFoundError:
        _logger.warning("`nfs-common` package not found on system. Doing nothing")


def fetch(target: str) -> Optional[MountInfo]:
    """Fetch information about an NFS mount.

    Args:
        target: NFS share endpoint or mountpoint information to fetch.

    Returns:
        Optional[MountInfo]: Mount information. None if NFS share is not mounted.
    """
    # Check if target is NFS URL. If so, convert to `mount.nfs` endpoint format
    # since that is what is stored in /proc/mounts.
    if _nfs_url_check.match(target):
        target, port = _translate(target)

    # Read /proc/mounts to get current NFS mount information.
    with pathlib.Path("/proc/mounts").open(mode="rt") as mounts:
        for mount in mounts.read().splitlines():
            if nfs_mount := _mount_parser.search(mount):
                info = nfs_mount.groupdict()
                if info["mountpoint"] == target or info["endpoint"] == target:
                    return MountInfo(**info)

    return None


def mounts() -> List[MountInfo]:
    """Get all NFS mounts on a machine.

    Returns:
        List[MountInfo]: All current NFS mounts on machine.
    """
    result = []
    with pathlib.Path("/proc/mounts").open(mode="rt") as mounts:
        for mount in mounts.read().splitlines():
            if nfs_mount := _mount_parser.search(mount):
                result.append(MountInfo(**nfs_mount.groupdict()))

    return result


def mounted(target: str) -> bool:
    """Determine if NFS mountpoint or endpoint is mounted.

    Args:
        target: NFS share endpoint or mountpoint to check.
    """
    if fetch(target):
        return True
    return False


def mount(
    endpoint: str, mountpoint: Union[str, os.PathLike], options: Optional[List[str]] = None
) -> None:
    """Mount an NFS share.

    Args:
        endpoint: NFS share endpoint to mount.
        mountpoint: System location to mount NFS share endpoint.
        options: Mount options to pass when mounting NFS share.

    Raises:
        Error: Raised if NFS share mount operation fails.
    """
    # Convert NFS URL to `mount.nfs` format if endpoint is NFS URL.
    if _nfs_url_check.match(endpoint):
        endpoint, port = _translate(endpoint)
    else:
        port = None

    if not (target := pathlib.Path(mountpoint)).exists():
        _logger.debug(f"Creating mountpoint {target}")
        target.mkdir()

    cmd = ["mount", "-t", "nfs"]
    if options:
        if port:
            options.append(f"port={port}")
        cmd.extend(["-o", ",".join(options)])
    cmd.extend([endpoint, target])
    try:
        _logger.debug(f"Mounting NFS share endpoint {endpoint} at {target} with options {options}")
        subprocess.run(cmd, stderr=subprocess.PIPE, check=True, text=True)
    except subprocess.CalledProcessError as e:
        _logger.error(f"{e} Reason:\n{e.stderr}")
        raise Error(f"Failed to mount {endpoint} at {target}")


def umount(mountpoint: Union[str, os.PathLike], force: bool = False) -> None:
    """Unmount an NFS share.

    Args:
        mountpoint: NFS share mountpoint to unmount.
        force: Pass `--force` option to umount. Default: False.

    Raises:
        Error: Raised if NFS share umount operation fails.
    """
    cmd = ["umount"]
    if force:
        cmd.append("--force")
    cmd.append(mountpoint)
    try:
        _logger.debug(f"Unmounting NFS share at mountpoint {mountpoint}")
        subprocess.run(cmd, stderr=subprocess.PIPE, check=True, text=True, timeout=120)
        shutil.rmtree(mountpoint, ignore_errors=True)
    except subprocess.CalledProcessError as e:
        _logger.error(f"{e} Reason:\n{e.stderr}")
        raise Error(f"Failed to unmount {mountpoint}")
    except subprocess.TimeoutExpired as e:
        _logger.error(f"{e} Reason:\n{e.stderr}")
        raise Error(f"Failed to unmount {mountpoint} failed after {e.timeout:.0f}s")
