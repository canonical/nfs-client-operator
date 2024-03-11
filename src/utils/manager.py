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
from typing import Iterator, List, Optional, Tuple, Union
from urllib.parse import urlparse

import charms.operator_libs_linux.v0.apt as apt
import charms.operator_libs_linux.v1.systemd as systemd

_logger = logging.getLogger(__name__)
_nfs_url_check = re.compile(
    r"""
        nfs://[-a-zA-Z0-9@:%._+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b([-a-zA-Z0-9()!@:%_+.~#?&/=]*)
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


def supported() -> bool:
    """Check if underlying base supports mounting NFS shares."""
    try:
        result = subprocess.run(
            ["systemd-detect-virt"], stdout=subprocess.PIPE, check=True, text=True
        )
        if "lxc" in result.stdout:
            # Cannot mount NFS shares inside LXD containers.
            return False
        else:
            return True
    except subprocess.CalledProcessError:
        _logger.warning("Could not detect execution in virtualized environment")
        return True


def install() -> None:
    """Install NFS utilities for mounting NFS shares.

    Raises:
        Error: Raised if this failed to install any of the required packages.
    """
    _logger.debug("Installing required packages from apt archive.")
    try:
        apt.add_package(["nfs-common", "autofs"], update_cache=True)
    except (apt.PackageError, apt.PackageNotFoundError) as e:
        _logger.error(f"Failed to install required packages. Reason:\n{e.message}")
        raise Error(e.message)


def remove() -> None:
    """Remove NFS utilities for mounting NFS shares.

    Raises
        Error: Raised if a required package was installed but could not be removed.
    """
    _logger.debug("Removing required packages from system packages")
    try:
        apt.remove_package(["nfs-common", "autofs"])
    except apt.PackageNotFoundError as e:
        _logger.warning(f"Skipping package that is not installed. Reason:\n{e}")
    except apt.PackageError as e:
        _logger.error(f"Failed to remove required packages. Reason:\n{e}")
        raise Error("Failed to remove required packages")


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

    # We need to trigger an automount for the mounts that are of type `autofs`,
    # since those could contain a `nfs` or `nfs4` mount.
    _trigger_autofs()

    for mount in _mounts("nfs"):
        if mount.mountpoint == target or mount.endpoint == target:
            return mount

    return None


def mounts() -> List[MountInfo]:
    """Get all NFS mounts on a machine.

    Returns:
        List[MountInfo]: All current NFS mounts on machine.
    """
    _trigger_autofs()

    return list(_mounts("nfs"))


def mounted(target: str) -> bool:
    """Determine if NFS mountpoint or endpoint is mounted.

    Args:
        target: NFS share endpoint or mountpoint to check.
    """
    return fetch(target) is not None


def mount(
    endpoint: str, mountpoint: Union[str, os.PathLike], options: Optional[List[str]] = None
) -> None:
    """Mount an NFS share.

    Args:
        endpoint: NFS share endpoint to mount.
        mountpoint: System location to mount NFS share endpoint.
        options: Mount options to pass when mounting NFS share.

    Raises:
        Error: Raised if the mount operation fails.
    """
    # Convert `endpoint` to the `mount.nfs` format if `endpoint` is an NFS URL.
    if _nfs_url_check.match(endpoint):
        endpoint, port = _translate(endpoint)
    else:
        port = None

    # Try to create the mountpoint without checking if it exists to avoid TOCTOU.
    target = pathlib.Path(mountpoint)
    try:
        target.mkdir()
        _logger.debug(f"Created mountpoint {mountpoint}.")
    except FileExistsError:
        _logger.warning(f"Mountpoint {mountpoint} already exists.")

    mount_opts = ""
    if options:
        if port:
            options.append(f"port={port}")
        mount_opts = ",".join(options)

    _logger.debug(f"Mounting NFS share endpoint {endpoint} at {target} with options {options}")
    autofs_id = _mountpoint_to_autofs_id(target)
    master = f"/- /etc/auto.{autofs_id}" + (f" {mount_opts}" if mount_opts else "")
    pathlib.Path(f"/etc/auto.master.d/{autofs_id}.autofs").write_text(master)
    pathlib.Path(f"/etc/auto.{autofs_id}").write_text(f"{target} {endpoint}")

    try:
        systemd.service_reload("autofs", restart_on_failure=True)
    except systemd.SystemdError as e:
        _logger.error(f"Failed to mount {endpoint} at {target}. Reason:\n{e}")
        if "Operation not permitted" in str(e) and not supported():
            raise Error("Mounting NFS shares not supported on LXD containers")
        raise Error(f"Failed to mount {endpoint} at {target}")


def umount(mountpoint: Union[str, os.PathLike]) -> None:
    """Unmount an NFS share.

    Args:
        mountpoint: NFS share mountpoint to unmount.

    Raises:
        Error: Raised if NFS share umount operation fails.
    """
    _logger.debug(f"Unmounting NFS share at mountpoint {mountpoint}")
    autofs_id = _mountpoint_to_autofs_id(mountpoint)
    pathlib.Path(f"/etc/auto.{autofs_id}").unlink(missing_ok=True)
    pathlib.Path(f"/etc/auto.master.d/{autofs_id}.autofs").unlink(missing_ok=True)

    try:
        systemd.service_reload("autofs", restart_on_failure=True)
    except systemd.SystemdError as e:
        _logger.error(f"Failed to unmount {mountpoint}. Reason:\n{e}")
        raise Error(f"Failed to unmount {mountpoint}.")

    shutil.rmtree(mountpoint, ignore_errors=True)


def _trigger_autofs() -> None:
    """Triggers a mount on all filesystems handled by autofs.

    This function is useful to make autofs-managed mounts appear on the
    `/proc/mount` file, since they could be unmounted when reading the file.
    """
    for fs in _mounts("autofs"):
        _logger.info(f"triggering automount for `{fs.mountpoint}`")
        try:
            os.scandir(fs.mountpoint).close()
        except OSError as e:
            # Not critical since it could also be caused by unrelated mounts,
            # but should be good to log it in case this causes problems.
            _logger.warning(f"Could not trigger automount for `{fs.mountpoint}`. Reason:\n{e}")


def _mountpoint_to_autofs_id(mountpoint: Union[str, os.PathLike]) -> str:
    """Converts a mountpoint to its corresponding autofs id.

    Args:
        mountpoint: NFS share mountpoint.
    """
    path = pathlib.Path(mountpoint).resolve()
    return str(path).lstrip("/").replace("/", "-")


def _mounts(fstype: str) -> Iterator[MountInfo]:
    """Gets an iterator of all mounts in the system that have the requested fstype.

    Returns:
        Iterator[MountInfo]: All the mounts with a valid fstype.
    """
    with pathlib.Path("/proc/mounts").open("rt") as mounts:
        for mount in mounts:
            # Lines in /proc/mounts follow the standard format
            # <endpoint> <mountpoint> <fstype> <options> <freq> <passno>
            m = MountInfo(*mount.split())
            if not m.fstype.startswith(fstype):
                continue

            yield m
