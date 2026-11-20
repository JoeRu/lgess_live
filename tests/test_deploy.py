"""deploy(): bundled files are read in the executor, SSH errors map to DeployError."""
from unittest.mock import patch

import pytest

from custom_components.lgess_live import deploy as deploy_mod
from custom_components.lgess_live.deploy import DeployError, deploy


async def test_bundled_read_in_executor_and_ssh_error(hass):
    calls = []
    orig = hass.async_add_executor_job

    def spy(target, *args):
        calls.append(target)
        return orig(target, *args)

    with patch.object(hass, "async_add_executor_job", side_effect=spy), \
         patch.object(deploy_mod.asyncssh, "connect", side_effect=OSError("unreachable")), \
         pytest.raises(DeployError, match="OSError: unreachable"):
        await deploy(hass, "10.0.0.17", "root")
    assert calls == [deploy_mod._bundled]
