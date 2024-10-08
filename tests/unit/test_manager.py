#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Test nfs manager utils."""

import os
import textwrap
from dataclasses import dataclass
from pathlib import Path
from subprocess import CalledProcessError
from types import SimpleNamespace
from typing import List, Optional, Union
from unittest.mock import patch

import charms.operator_libs_linux.v0.apt as apt
import charms.operator_libs_linux.v1.systemd as systemd
from pyfakefs.fake_filesystem_unittest import TestCase

import utils.manager as nfs


@dataclass(frozen=True, kw_only=True)
class MountParams:
    """Test parameters for the `mount` operation."""

    endpoint: str
    mountpoint: Union[str, os.PathLike]
    options: Optional[List[str]]
    master_file: Union[str, os.PathLike]
    master_data: str
    map_file: Union[str, os.PathLike]
    map_data: str


@patch("charms.operator_libs_linux.v1.systemd.service_reload")
@patch("subprocess.run")
class TestNFSManager(TestCase):
    """Test nfs manager utils."""

    def setUp(self) -> None:
        self.setUpPyfakefs()
        self.fs.create_dir("/etc/auto.master.d")
        self.fs.create_file(
            "/proc/mounts",
            contents=textwrap.dedent(
                """\
                /dev/sda1 / ext4 rw,relatime,discard,errors=remount-ro 0 0
                192.168.1.150:/data /data nfs4 rw,relatime,vers=4.2 0 0
                [ffcc:aabb::10]:/things /things nfs rw 0 0
                nsfs /run/snapd/ns/lxd.mnt nsfs rw 0 0
                /etc/auto.data /data autofs rw,relatime 0 0
                tmpfs /run/lock tmpfs rw,nosuid,nodev,noexec,relatime 0 0
                """,
            ),
        )
        self.data_mount = nfs.MountInfo(
            "192.168.1.150:/data", "/data", "nfs4", "rw,relatime,vers=4.2", "0", "0"
        )
        self.things_mount = nfs.MountInfo(
            "[ffcc:aabb::10]:/things", "/things", "nfs", "rw", "0", "0"
        )

    def test_mount_valid_endpoint(self, *_) -> None:
        """Test that various kinds of endpoints can be properly mounted."""
        cases = [
            # IPv4
            MountParams(
                endpoint="nfs://192.168.1.254/things",
                mountpoint="/things",
                options=[],
                master_file="/etc/auto.master.d/things.autofs",
                master_data="/- /etc/auto.things",
                map_file="/etc/auto.things",
                map_data="/things 192.168.1.254:/things",
            ),
            # IPv4 + options
            MountParams(
                endpoint="nfs://192.168.1.254/things",
                mountpoint="/things",
                options=["some", "opts"],
                master_file="/etc/auto.master.d/things.autofs",
                master_data="/- /etc/auto.things some,opts",
                map_file="/etc/auto.things",
                map_data="/things 192.168.1.254:/things",
            ),
            # IPv4 + port + options
            MountParams(
                endpoint="nfs://192.168.1.254:2049/things",
                mountpoint="/things",
                options=["some", "opts"],
                master_file="/etc/auto.master.d/things.autofs",
                master_data="/- /etc/auto.things some,opts,port=2049",
                map_file="/etc/auto.things",
                map_data="/things 192.168.1.254:/things",
            ),
            # IPv6
            MountParams(
                endpoint="nfs://[fd42:7650:65a::dbf5:b3c:5961]/things",
                mountpoint="/things",
                options=[],
                master_file="/etc/auto.master.d/things.autofs",
                master_data="/- /etc/auto.things",
                map_file="/etc/auto.things",
                map_data="/things [fd42:7650:65a::dbf5:b3c:5961]:/things",
            ),
            # IPv6 + port + options
            MountParams(
                endpoint="nfs://[fd42:7650:65a::dbf5:b3c:5961]:2049/things",
                mountpoint="/things",
                options=["some", "opts"],
                master_file="/etc/auto.master.d/things.autofs",
                master_data="/- /etc/auto.things some,opts,port=2049",
                map_file="/etc/auto.things",
                map_data="/things [fd42:7650:65a::dbf5:b3c:5961]:/things",
            ),
            # hostname
            MountParams(
                endpoint="nfs://server.com/things",
                mountpoint="/things",
                options=[],
                master_file="/etc/auto.master.d/things.autofs",
                master_data="/- /etc/auto.things",
                map_file="/etc/auto.things",
                map_data="/things server.com:/things",
            ),
            # hostname + port + options
            MountParams(
                endpoint="nfs://server.com:65535/things",
                mountpoint="/things",
                options=["some", "opts"],
                master_file="/etc/auto.master.d/things.autofs",
                master_data="/- /etc/auto.things some,opts,port=65535",
                map_file="/etc/auto.things",
                map_data="/things server.com:/things",
            ),
            # hostname with dot
            MountParams(
                endpoint="nfs://server.com./things",
                mountpoint="/things",
                options=[],
                master_file="/etc/auto.master.d/things.autofs",
                master_data="/- /etc/auto.things",
                map_file="/etc/auto.things",
                map_data="/things server.com.:/things",
            ),
        ]

        for case in cases:
            with self.subTest(
                endpoint=case.endpoint, mountpoint=case.mountpoint, options=case.options
            ):
                nfs.mount(case.endpoint, case.mountpoint, case.options)

                master_data = Path(case.master_file).read_text()
                self.assertEqual(case.master_data, master_data)
                map_data = Path(case.map_file).read_text()
                self.assertEqual(case.map_data, map_data)

    def test_mount_invalid_endpoint(self, *_) -> None:
        """Test that malformed endpoints are rejected."""
        cases = [
            # Missing protocol
            "192.168.1.254/things",
            # Invalid protocol
            "ssh://192.168.1.254/things",
            # IPv6 without brackets
            "nfs://ffff:eeee::cccc:bbbb:2049/things",
            # IPv6 with invalid brackets
            "nfs://[ffff:eeee::cccc:bbbb:2049/things",
            # Invalid port
            "nfs://hostname:abc/things",
            # Queries
            "nfs://endpoint.com?query1=1&query2=2/things",
            # Fragments
            "nfs://endpoint.com#fragment/things",
            # Empty host
            "nfs:///things",
        ]

        for case in cases:
            with self.subTest(endpoint=case), self.assertRaises(nfs.Error):
                nfs.mount(case, "/data")

    def test_mount_systemd_error(self, subproc, reload, *_):
        """Test that the mount operation correctly raises if systemd cannot reload the service."""
        subproc.return_value = SimpleNamespace(stdout="kvm")

        # Normal error
        reload.side_effect = systemd.SystemdError("error message")
        with self.assertRaises(nfs.Error) as sup:
            nfs.mount("nfs://192.168.1.254:2049/data", "/data")
        self.assertEqual(sup.exception.message, "Failed to mount 192.168.1.254:/data at /data")

        # Operation not permitted but not LXC virtualization
        reload.side_effect = systemd.SystemdError("Operation not permitted")
        with self.assertRaises(nfs.Error) as sup:
            nfs.mount("nfs://192.168.1.254:2049/data", "/data")
        self.assertEqual(sup.exception.message, "Failed to mount 192.168.1.254:/data at /data")

        subproc.return_value = SimpleNamespace(stdout="lxc")

        # Normal error on LXC virtualization
        reload.side_effect = systemd.SystemdError("error message")
        with self.assertRaises(nfs.Error) as sup:
            nfs.mount("nfs://192.168.1.254:2049/data", "/data")
        self.assertEqual(sup.exception.message, "Failed to mount 192.168.1.254:/data at /data")

        # Operation not permitted on LXC virtualization. Should show a useful error message.
        reload.side_effect = systemd.SystemdError("Operation not permitted")
        with self.assertRaises(nfs.Error) as sup:
            nfs.mount("nfs://192.168.1.254:2049/data", "/data")
        self.assertEqual(
            sup.exception.message, "Mounting NFS shares not supported on LXD containers"
        )

        # Error trying to check the virtualization type. Should throw the normal error message
        # for good measure.
        subproc.side_effect = CalledProcessError(-1, "error message")
        with self.assertRaises(nfs.Error) as sup:
            nfs.mount("nfs://192.168.1.254:2049/data", "/data")
        self.assertEqual(sup.exception.message, "Failed to mount 192.168.1.254:/data at /data")

    @patch("charms.operator_libs_linux.v0.apt.add_package")
    def test_install(self, add_package, *_):
        """Test that the install operation correctly succeeds or bails on error."""
        nfs.install()

        add_package.side_effect = apt.PackageError("error message")
        with self.assertRaises(nfs.Error) as e:
            nfs.install()

        self.assertEqual(e.exception.message, "error message")

    @patch("charms.operator_libs_linux.v0.apt.remove_package")
    def test_remove(self, remove_package, *_):
        """Test that the remove operation never bails on error, but fails on package error."""
        # Sunny day
        nfs.remove()

        remove_package.side_effect = apt.PackageNotFoundError("error message")
        # Rainy day
        nfs.remove()

        remove_package.side_effect = apt.PackageError("error message")
        with self.assertRaises(nfs.Error):
            nfs.remove()

    def test_fetch_valid(self, *_):
        """Test that the fetch operation fetches all defined nfs mounts."""
        cases = [
            ("nfs://192.168.1.150/data", self.data_mount),
            ("/data", self.data_mount),
            ("nfs://[ffcc:aabb::10]/things", self.things_mount),
            ("/things", self.things_mount),
        ]

        for case, info in cases:
            with self.subTest(target=case):
                self.assertEqual(nfs.fetch(case), info)

    def test_fetch_invalid(self, *_):
        """Test that the fetch operation cannot fetch unknown or invalid mounts."""
        cases = ["/dev/sda1", "/", "192.168.1.1:/data", "/datum", "/etc/auto.data"]

        for case in cases:
            with self.subTest(target=case):
                self.assertIsNone(nfs.fetch(case))

    def test_mounts(self, *_):
        """Test that the mounts operation returns only nfs mounts."""
        self.assertEqual(nfs.mounts(), [self.data_mount, self.things_mount])

    def test_umount(self, _subprocess, reload, *_):
        """Test that the umount operation correctly deletes files and raises if systemd raises."""
        self.fs.create_dir("/data")
        self.fs.create_file("/etc/auto.data")
        self.fs.create_file("/etc/auto.master.d/data.autofs")

        nfs.umount("/data")

        self.assertFalse(self.fs.exists("/data"))
        self.assertFalse(self.fs.exists("/etc/auto.data"))
        self.assertFalse(self.fs.exists("/etc/auto.master.d/data.autofs"))

        reload.side_effect = systemd.SystemdError("error message")
        with self.assertRaises(nfs.Error) as e:
            # umount cannot throw if the files don't exist, only if systemd raises an error.
            nfs.umount("/data")

        self.assertEqual(e.exception.message, "Failed to unmount /data")

    def test_error(self, *_):
        """Test the properties of the Error class."""
        error = nfs.Error("error message")
        self.assertEqual(error.name, "<utils.manager.Error>")
        self.assertEqual(repr(error), "<utils.manager.Error ('error message',)>")
