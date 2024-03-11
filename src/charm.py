#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""NFS client charmed operator for mounting NFS shares."""

import logging

import utils.manager as nfs
from charms.storage_libs.v0.nfs_interfaces import (
    MountShareEvent,
    NFSRequires,
    ServerConnectedEvent,
    UmountShareEvent,
)
from ops.charm import ActionEvent, CharmBase
from ops.framework import StoredState
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus

logger = logging.getLogger(__name__)


class NFSClientCharm(CharmBase):
    """NFS client charmed operator."""

    _stored = StoredState()

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._stored.set_default(
            mountpoint=None,
            size=None,
            mntopts={"noexec": None, "nosuid": None, "nodev": None, "read-only": None},
        )
        self._nfs_share = NFSRequires(self, "nfs-share")
        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.stop, self._on_stop)
        self.framework.observe(self._nfs_share.on.server_connected, self._on_server_connected)
        self.framework.observe(self._nfs_share.on.mount_share, self._on_mount_share)
        self.framework.observe(self._nfs_share.on.umount_share, self._on_umount_share)
        self.framework.observe(self.on.force_umount_action, self._on_force_umount_action)

        # ensures the required packages are installed after a `juju refresh`.
        self.framework.observe(self.on.upgrade_charm, self._on_install)

    def _on_install(self, _) -> None:
        """Install required packages for mounting NFS shares."""
        self.unit.status = MaintenanceStatus("Installing required packages")
        try:
            nfs.install()
        except nfs.Error as e:
            self.unit.status = BlockedStatus(e.message)

    def _on_config_changed(self, _) -> None:
        """Handle updates to NFS client configuration."""
        mountpoint = self.config.get("mountpoint")
        if mountpoint is None:
            self.unit.status = BlockedStatus("No configured mountpoint")
            return

        if self._stored.mountpoint is None:
            logger.debug(f"Setting mountpoint as {mountpoint}")
            self._stored.mountpoint = mountpoint
        elif self._stored.mountpoint is not None:
            self.unit.status = WaitingStatus("Already set")
            logger.warning(f"Mountpoint can only be set once. Ignoring {mountpoint}")

        size = self.config.get("size")
        if self._stored.size is None:
            logger.debug(f"Setting NFS share size as {size}")
            self._stored.size = size
        elif self._stored.size is not None:
            logger.warning(f"Size can only be set once. Ignoring {size}")

        for opt, val in self._stored.mntopts.items():
            new_val = self.config.get(opt)
            if val is None:
                self._stored.mntopts[opt] = new_val
            else:
                logger.warning(f"{opt} can only be set once. Ignoring {new_val}")

        self.unit.status = WaitingStatus("Waiting for NFS share")

    def _on_stop(self, _) -> None:
        """Clean up machine before de-provisioning."""
        if nfs.mounted(mountpoint := self.config.get("mountpoint")):
            self.unit.status = MaintenanceStatus(f"Unmounting {mountpoint}")
            nfs.umount(mountpoint)

        # Only remove the required packages if there are no existing NFS shares outside of charm.
        if not nfs.mounts():
            self.unit.status = MaintenanceStatus("Removing required packages")
            nfs.remove()

        self.unit.status = MaintenanceStatus("Shutting down...")

    def _on_server_connected(self, event: ServerConnectedEvent) -> None:
        """Handle when client has connected to NFS server."""
        self.unit.status = MaintenanceStatus("Requesting NFS share")
        if self._stored.mountpoint is None:
            logger.warning("Deferring ServerConnectedEvent event because mountpoint is not set")
            self.unit.status = BlockedStatus("No configured mountpoint")
            event.defer()
            return

        self._nfs_share.request_share(
            event.relation.id,
            name=self._stored.mountpoint,
            size=self._stored.size,
            allowlist="0.0.0.0/0",
        )

    def _on_mount_share(self, event: MountShareEvent) -> None:
        """Mount an NFS share."""
        try:
            if not nfs.mounted(event.endpoint):
                opts = []
                opts.append("noexec") if self._stored.mntopts["noexec"] else opts.append("exec")
                opts.append("nosuid") if self._stored.mntopts["nosuid"] else opts.append("suid")
                opts.append("nodev") if self._stored.mntopts["nodev"] else opts.append("dev")
                opts.append("ro") if self._stored.mntopts["read-only"] else opts.append("rw")
                nfs.mount(event.endpoint, self._stored.mountpoint, options=opts)
                self.unit.status = ActiveStatus(f"NFS share mounted at {self._stored.mountpoint}")
            else:
                logger.warning(f"Endpoint {event.endpoint} already mounted")
        except nfs.Error as e:
            self.unit.status = BlockedStatus(e.message)

    def _on_umount_share(self, event: UmountShareEvent) -> None:
        """Umount an NFS share."""
        self.unit.status = MaintenanceStatus(f"Unmounting NFS share at {self._stored.mountpoint}")
        try:
            if event.endpoint:
                if mount_info := nfs.fetch(event.endpoint):
                    nfs.umount(mount_info.mountpoint)
                else:
                    logger.warning(f"{event.endpoint} is not mounted")
            else:
                logger.warning(f"No endpoint provided, defaulting to {self._stored.mountpoint}")
                if nfs.mounted(self._stored.mountpoint):
                    nfs.umount(self._stored.mountpoint)
                else:
                    logger.warning(f"{self._stored.mountpoint} is not mounted")

            self.unit.status = WaitingStatus("Waiting for NFS share")
        except nfs.Error as e:
            self.unit.status = BlockedStatus(e.message)

    def _on_force_umount_action(self, event: ActionEvent) -> None:
        """Handle `force-umount` action."""
        if (
            nfs.mounted(self._stored.mountpoint)
            and self._stored.mountpoint == event.params["mountpoint"]
        ):
            self.unit.status = MaintenanceStatus(
                f"Forcefully unmounting NFS share at {self._stored.mountpoint}"
            )
            try:
                logger.warning(
                    (
                        f"Forcefully unmounting {self._stored.mountpoint}. "
                        "A forced umount can potentially cause data corruption"
                    )
                )
                nfs.umount(self._stored.mountpoint)
                self.unit.status = WaitingStatus("Waiting for NFS share")
                event.set_results({"result": "Forced umount successful"})
            except nfs.Error as e:
                self.unit.status = BlockedStatus(e.message)
                event.fail(e.message)
        else:
            if self._stored.mountpoint != event.params["mountpoint"]:
                logger.debug(
                    message := (
                        f"Mountpoint {self._stored.mountpoint} does not equal "
                        f"specified mountpoint {event.params['mountpoint']}"
                    )
                )
                event.fail(message)
            else:
                logger.debug(message := f"{self._stored.mountpoint} is not mounted")
                event.fail(message)


if __name__ == "__main__":  # pragma: nocover
    main(NFSClientCharm)
