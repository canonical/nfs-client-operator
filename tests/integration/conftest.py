#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Configure integration test run."""

import pathlib
from typing import Any, Coroutine

import pytest
from _pytest.config.argparsing import Parser
from pytest_operator.plugin import OpsTest


def pytest_addoption(parser: Parser) -> None:
    parser.addoption(
        "--charm-base", action="store", default="ubuntu@22.04", help="Charm base to test."
    )
    parser.addoption("--ipv6", action="store_true", default=False, help="Use IPv6 for addresses.")


@pytest.fixture(scope="module")
def charm_base(request) -> str:
    """Get nfs-client charm series to use."""
    return request.config.getoption("--charm-base")


@pytest.fixture(scope="module")
def use_ipv6(request) -> bool:
    """Get if tests should use IPv6 for addresses."""
    return request.config.getoption("--ipv6")


@pytest.fixture(scope="module")
async def nfs_client_charm(ops_test: OpsTest, request) -> Coroutine[Any, Any, pathlib.Path]:
    """Build nfs-client charm to use for integration tests."""
    charm = await ops_test.build_charm(".")
    return charm
