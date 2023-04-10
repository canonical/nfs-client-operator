#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Test nfs-share integration."""

import unittest
from unittest.mock import patch, MagicMock

import ops.testing
import utils.manager as nfs
from charm import NFSClientCharm
from ops.model import ActiveStatus, BlockedStatus, WaitingStatus
from ops.testing import Harness


class TestNFSShare(unittest.TestCase):
    """Test nfs-share integration."""

    def setUp(self) -> None:
        ops.testing.SIMULATE_CAN_CONNECT = True
        self.addCleanup(setattr, ops.testing, "SIMULATE_CAN_CONNECT", False)
        self.harness = Harness(NFSClientCharm)
        self.integration_id = self.harness.add_relation("nfs-share", "nfs-server-proxy")
        self.harness.add_relation_unit(self.integration_id, "nfs-server-proxy/0")
        self.harness.set_leader(True)
        self.harness.begin()

    def test_server_connected_no_mountpoint(self) -> None:
        """Test server connected handler when there is no configured mountpoint."""
        # Patch charm stored state.
        self.harness.charm._stored.mountpoint = None
        integration = self.harness.charm.model.get_relation("nfs-share", self.integration_id)
        app = self.harness.charm.model.get_app("nfs-server-proxy")
        self.harness.charm._nfs_share.on.server_connected.emit(integration, app)
        self.assertEqual(self.harness.model.unit.status, BlockedStatus("No configured mountpoint"))

    def test_server_connected(self) -> None:
        """Test server connected handler when mountpoint is configured."""
        # Patch charm stored state.
        self.harness.charm._stored.mountpoint = "/data"
        integration = self.harness.charm.model.get_relation("nfs-share", self.integration_id)
        app = self.harness.charm.model.get_app("nfs-server-proxy")
        self.harness.charm._nfs_share.on.server_connected.emit(integration, app)

    @patch("utils.manager.mount", side_effect=nfs.Error("Failed to mount share"))
    @patch("utils.manager.mounted", return_value=False)
    def test_mount_share_failed(self, *_) -> None:
        """Test mount share handler when mount fails."""
        integration = self.harness.charm.model.get_relation("nfs-share", self.integration_id)
        app = self.harness.charm.model.get_app("nfs-server-proxy")
        self.harness.charm._nfs_share.on.mount_share.emit(integration, app)
        self.assertEqual(self.harness.model.unit.status, BlockedStatus("Failed to mount share"))

    @patch("utils.manager.mounted", return_value=True)
    def test_mount_share_already_mounted(self, _) -> None:
        """Test mount share handler when NFS share is already mounted."""
        integration = self.harness.charm.model.get_relation("nfs-share", self.integration_id)
        app = self.harness.charm.model.get_app("nfs-server-proxy")
        self.harness.charm._nfs_share.on.mount_share.emit(integration, app)

    @patch("utils.manager.mount")
    @patch("utils.manager.mounted", return_value=False)
    def test_mount_share(self, *_) -> None:
        """Test mount share handler."""
        integration = self.harness.charm.model.get_relation("nfs-share", self.integration_id)
        app = self.harness.charm.model.get_app("nfs-server-proxy")
        self.harness.charm._nfs_share.on.mount_share.emit(integration, app)
        self.assertIsInstance(self.harness.model.unit.status, ActiveStatus)

    @patch("utils.manager.umount", side_effect=nfs.Error("Failed to umount share"))
    @patch("utils.manager.mounted")
    def test_umount_share_failed(self, *_) -> None:
        """Test umount share handler when umount fails."""
        integration = self.harness.charm.model.get_relation("nfs-share", self.integration_id)
        app = self.harness.charm.model.get_app("nfs-server-proxy")
        self.harness.charm._nfs_share.on.umount_share.emit(integration, app)
        self.assertEqual(self.harness.model.unit.status, BlockedStatus("Failed to umount share"))

    @patch("utils.manager.umount")
    @patch(
        "utils.manager.fetch",
        return_value=nfs.MountInfo(
            endpoint="127.0.0.1:/data",
            mountpoint="/data",
            fstype="nfs4",
            options="some,thing",
            freq="0",
            passno="0",
        ),
    )
    def test_umount_share_endpoint_provided_and_mounted(self, *_) -> None:
        """Test umount share handler with endpoint and active mount."""
        integration = self.harness.charm.model.get_relation("nfs-share", self.integration_id)
        app = self.harness.charm.model.get_app("nfs-server-proxy")
        self.harness.update_relation_data(
            self.integration_id, "nfs-server-proxy", {"endpoint": "nfs://127.0.0.1/data"}
        )
        self.harness.charm._nfs_share.on.umount_share.emit(integration, app)
        self.assertEqual(self.harness.model.unit.status, WaitingStatus("Waiting for NFS share"))

    @patch("utils.manager.fetch", return_value=None)
    @patch("utils.manager.mount")
    def test_umount_share_endpoint_provided_not_mounted(self, *_) -> None:
        """Test umount share handler with endpoint and no mount."""
        integration = self.harness.charm.model.get_relation("nfs-share", self.integration_id)
        app = self.harness.charm.model.get_app("nfs-server-proxy")
        self.harness.update_relation_data(
            self.integration_id, "nfs-server-proxy", {"endpoint": "nfs://127.0.0.1/data"}
        )
        self.harness.charm._nfs_share.on.umount_share.emit(integration, app)
        self.assertEqual(self.harness.model.unit.status, WaitingStatus("Waiting for NFS share"))

    @patch("utils.manager.umount")
    @patch("utils.manager.mounted", return_value=True)
    def test_umount_share_no_endpoint_and_mounted(self, *_) -> None:
        """Test umount share handler with no endpoint and active mount."""
        integration = self.harness.charm.model.get_relation("nfs-share", self.integration_id)
        app = self.harness.charm.model.get_app("nfs-server-proxy")
        self.harness.charm._nfs_share.on.umount_share.emit(integration, app)
        self.assertEqual(self.harness.model.unit.status, WaitingStatus("Waiting for NFS share"))

    @patch("utils.manager.mounted", return_value=False)
    def test_umount_share_no_endpoint_not_mounted(self, _) -> None:
        """Test umount share handler with no endpoint and no mount."""
        integration = self.harness.charm.model.get_relation("nfs-share", self.integration_id)
        app = self.harness.charm.model.get_app("nfs-server-proxy")
        self.harness.charm._nfs_share.on.umount_share.emit(integration, app)
        self.assertEqual(self.harness.model.unit.status, WaitingStatus("Waiting for NFS share"))

    @patch("utils.manager.umount")
    @patch("utils.manager.mounted", return_value=True)
    def test_force_umount_mounted_and_equal(self, *_) -> None:
        """Test force-umount action with share mounted and exact path name."""
        # Patch charm stored state.
        self.harness.charm._stored.mountpoint = "/data"
        event = MagicMock()
        setattr(event, "params", {"mountpoint": "/data"})
        self.harness.charm._on_force_umount_action(event)
        self.assertEqual(self.harness.model.unit.status, WaitingStatus("Waiting for NFS share"))

    @patch("utils.manager.umount", side_effect=nfs.Error("Failed to umount share"))
    @patch("utils.manager.mounted", return_value=True)
    def test_force_umount_failed(self, *_) -> None:
        """Test force-umount action when it fails."""
        # Patch charm stored state.
        self.harness.charm._stored.mountpoint = "/data"
        event = MagicMock()
        setattr(event, "params", {"mountpoint": "/data"})
        self.harness.charm._on_force_umount_action(event)
        self.assertEqual(self.harness.charm.unit.status, BlockedStatus("Failed to umount share"))

    def test_force_umount_bad_mountpoint(self) -> None:
        """Test force-umount action when passed mountpoint != internal mountpoint."""
        self.harness.charm._stored.mountpoint = "/data"
        event = MagicMock()
        setattr(event, "params", {"mountpoint": "/nuccitheboss"})
        self.harness.charm._on_force_umount_action(event)

    @patch("utils.manager.mounted", return_value=False)
    def test_force_umount_not_mounted(self, _) -> None:
        """Test force-umount action when mountpoint is not mounted."""
        self.harness.charm._stored.mountpoint = "/data"
        event = MagicMock()
        setattr(event, "params", {"mountpoint": "/data"})
        self.harness.charm._on_force_umount_action(event)
