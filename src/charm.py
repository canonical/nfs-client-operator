#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""NFS client charmed operator for mounting NFS shares."""

import logging

from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus

logger = logging.getLogger(__name__)


class NFSClientCharm(CharmBase):
    """NFS client charmed operator."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.framework.observe(self.on.start, self._on_start)

    def _on_start(self, event):
        """Handle start event."""
        self.unit.status = ActiveStatus()


if __name__ == "__main__":  # pragma: nocover
    main(NFSClientCharm)
