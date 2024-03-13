# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Helpers for nfs-client integration tests."""

import logging
import textwrap

from pylxd import Client

_logger = logging.getLogger(__name__)


def modify_lxd_config(use_ipv6: bool) -> None:
    """Modify the LXD config."""
    client = Client()
    config = {
        "security.privileged": "true",
        "raw.apparmor": "mount fstype=nfs*, mount fstype=rpc_pipefs,",
    }
    _logger.info(f"Updating default LXD profile configuration to {config}")
    default = client.profiles.get("default")
    default.config.update(config)
    default.save()

    network = client.networks.get("lxdbr0")
    if use_ipv6:
        _logger.info("Enabling ipv6 addresses on network lxdbr0")
        network.config["ipv6.address"] = "auto"
    else:
        _logger.info("Disabling ipv6 addresses on network lxdbr0")
        network.config["ipv6.address"] = "none"
    network.save()


def bootstrap_nfs_server(use_ipv6: bool) -> str:
    """Bootstrap a minimal NFS kernel server in LXD.

    Returns:
        str: NFS URL endpoint.
    """
    client = Client()

    if client.instances.exists("nfs-server"):
        _logger.info("NFS server already exists")
        instance = client.instances.get("nfs-server")
        address = instance.state().network["eth0"]["addresses"][int(use_ipv6)]["address"]
        if use_ipv6:
            endpoint = f"nfs://[{address}]/data"
        else:
            endpoint = f"nfs://{address}/data"
        _logger.info(f"NFS share endpoint is {endpoint}")
        return endpoint

    _logger.info("Bootstrapping minimal NFS kernel server")
    config = {
        "name": "nfs-server",
        "source": {
            "alias": "jammy/amd64",
            "mode": "pull",
            "protocol": "simplestreams",
            "server": "https://cloud-images.ubuntu.com/releases",
            "type": "image",
        },
        "type": "container",
    }
    client.instances.create(config, wait=True)
    instance = client.instances.get(config["name"])
    instance.start(wait=True)
    _logger.info("Installing NFS server inside LXD container")
    instance.execute(
        ["apt-get", "-y", "update"], environment={"DEBIAN_FRONTEND": "noninteractive"}
    )
    instance.execute(
        ["apt-get", "-y", "upgrade"], environment={"DEBIAN_FRONTEND": "noninteractive"}
    )
    instance.execute(
        ["apt-get", "-y", "install", "nfs-kernel-server"],
        environment={"DEBIAN_FRONTEND": "noninteractive"},
    )
    exports = textwrap.dedent(
        """
        /srv     *(ro,sync,subtree_check)
        /data    *(rw,sync,no_subtree_check,no_root_squash)
        """
    ).strip("\n")
    _logger.info(f"Uploading the following /etc/exports file:\n{exports}")
    instance.files.put("/etc/exports", exports)
    _logger.info("Starting NFS server")
    instance.execute(["mkdir", "-p", "/data"])
    instance.execute(["exportfs", "-a"])
    instance.execute(["systemctl", "restart", "nfs-kernel-server"])
    for i in ["1", "2", "3"]:
        instance.execute(["touch", f"/data/test-{i}"])
    address = instance.state().network["eth0"]["addresses"][int(use_ipv6)]["address"]
    if use_ipv6:
        endpoint = f"nfs://[{address}]/data"
    else:
        endpoint = f"nfs://{address}/data"
    _logger.info(f"NFS share endpoint is {endpoint}")
    return endpoint
