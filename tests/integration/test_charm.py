#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Test nfs-client charm against other NFS share provides in latest/edge."""

import asyncio
import logging
import pathlib
from typing import Any, Coroutine

import pytest
import tenacity
from helpers import bootstrap_nfs_server, modify_default_profile
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)

BASE = "ubuntu"
NFS_CLIENT = "nfs-client"
NFS_SERVER_PROXY = "nfs-server-proxy"


@pytest.mark.abort_on_fail
@pytest.mark.skip_if_deployed
@pytest.mark.order(1)
async def test_build_and_deploy(
    ops_test: OpsTest, nfs_client_charm: Coroutine[Any, Any, pathlib.Path], charm_base: str
) -> None:
    """Test that nfs-client can stabilize against nfs-server-proxy."""
    modify_default_profile()
    endpoint = bootstrap_nfs_server()
    logger.info(f"Deploying {NFS_CLIENT} against {NFS_SERVER_PROXY} and {BASE}")
    await asyncio.gather(
        ops_test.model.deploy(
            str(await nfs_client_charm),
            application_name=NFS_CLIENT,
            config={"mountpoint": "/data"},
            num_units=None,
            base=charm_base,
        ),
        ops_test.model.deploy(
            BASE,
            application_name=BASE,
            channel="edge",
            num_units=1,
            base=charm_base,
        ),
        ops_test.model.deploy(
            NFS_SERVER_PROXY,
            application_name=NFS_SERVER_PROXY,
            config={"endpoint": endpoint},
            channel="edge",
            num_units=1,
            base="ubuntu@22.04",
        ),
    )
    # Set integrations for charmed applications
    await ops_test.model.integrate(f"{NFS_CLIENT}:juju-info", f"{BASE}:juju-info")
    await ops_test.model.integrate(f"{NFS_CLIENT}:nfs-share", f"{NFS_SERVER_PROXY}:nfs-share")
    # Reduce the update status frequency to accelerate the triggering of deferred events.
    async with ops_test.fast_forward():
        await ops_test.model.wait_for_idle(apps=[NFS_CLIENT], status="active", timeout=1000)
        assert ops_test.model.applications[NFS_CLIENT].units[0].workload_status == "active"


@pytest.mark.abort_on_fail
@pytest.mark.order(2)
@tenacity.retry(
    wait=tenacity.wait.wait_exponential(multiplier=2, min=1, max=30),
    stop=tenacity.stop_after_attempt(3),
    reraise=True,
)
async def test_share_active(ops_test: OpsTest) -> None:
    """Test that NFS share is successfully mounted on principle base charm."""
    logger.info(f"Checking that /data is mounted on principle charm {BASE}")
    base_unit = ops_test.model.applications[BASE].units[0]
    result = (await base_unit.ssh("ls /data")).strip("\n")
    assert "test-1" in result
    assert "test-2" in result
    assert "test-3" in result
