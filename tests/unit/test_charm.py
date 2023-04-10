#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Test base charm events such as Install, Stop, etc."""

import unittest
from unittest.mock import PropertyMock, patch

import ops.testing
import utils.manager as nfs
from charm import NFSClientCharm
from ops.model import BlockedStatus, MaintenanceStatus, WaitingStatus
from ops.testing import Harness


class TestCharm(unittest.TestCase):
    """Test nfs-client charmed operator."""

    def setUp(self) -> None:
        ops.testing.SIMULATE_CAN_CONNECT = True
        self.addCleanup(setattr, ops.testing, "SIMULATE_CAN_CONNECT", False)
        self.harness = Harness(NFSClientCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    @patch("utils.manager.install")
    def test_install(self, _) -> None:
        """Test that nfs-client can successfully be installed."""
        self.harness.charm.on.install.emit()
        self.assertEqual(
            self.harness.model.unit.status, MaintenanceStatus("Installing `nfs-common`")
        )

    @patch("utils.manager.install", side_effect=nfs.Error("Failed to install `nfs-common`"))
    def test_install_fail(self, _) -> None:
        """Test that nfs-client install fail handler works."""
        self.harness.charm.on.install.emit()
        self.assertEqual(
            self.harness.model.unit.status, BlockedStatus("Failed to install `nfs-common`")
        )

    @patch(
        "charm.NFSClientCharm.config", new_callable=PropertyMock(return_value={"mountpoint": None})
    )
    def test_config_no_mountpoint(self, _) -> None:
        """Test config changed handler when no mountpoint is set."""
        self.harness.charm.on.config_changed.emit()
        self.assertEqual(self.harness.model.unit.status, BlockedStatus("No configured mountpoint"))

    @patch(
        "charm.NFSClientCharm.config",
        new_callable=PropertyMock(return_value={"mountpoint": "/data"}),
    )
    def test_config_set_mountpoint(self, _) -> None:
        """Test config changed handler when new mountpoint is available."""
        self.harness.charm.on.config_changed.emit()
        self.assertEqual(self.harness.model.unit.status, WaitingStatus("Waiting for NFS share"))

    @patch(
        "charm.NFSClientCharm.config",
        new_callable=PropertyMock(
            return_value={
                "mountpoint": "/data",
                "size": 100,
                "noexec": False,
                "nosuid": False,
                "nodev": False,
                "read-only": False,
            }
        ),
    )
    def test_config_already_set(self, *_) -> None:
        """Test config changed handler after all values have been set."""
        # Patch charm stored state.
        self.harness.charm._stored.mountpoint = "/data"
        self.harness.charm._stored.size = 100
        self.harness.charm._stored.mntopts = {
            "noexec": False,
            "nosuid": False,
            "nodev": False,
            "read-only": False,
        }
        self.harness.charm.on.config_changed.emit()
        self.assertEqual(self.harness.model.unit.status, WaitingStatus("Waiting for NFS share"))

    @patch("utils.manager.mounted", return_value=True)
    @patch.object(nfs, "umount")
    @patch("utils.manager.mounts", return_value=[])
    @patch.object(nfs, "remove")
    def test_on_stop(self, remove, mounts, umount, mounted) -> None:
        """Test on stop handler."""
        self.harness.charm.on.stop.emit()
        umount.assert_called_once()
        remove.assert_called_once()
        self.assertEqual(self.harness.model.unit.status, MaintenanceStatus("Shutting down..."))
