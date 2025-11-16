import contextlib
import typing

import pytest
from modern_di.registries.state_registry.state import ProviderState


def test_sync_state_async_tear_down() -> None:
    state = ProviderState[typing.Any]()
    state.context_stack = contextlib.AsyncExitStack()
    with pytest.raises(RuntimeError, match="Cannot tear down async context in `sync_tear_down`"):
        state.sync_tear_down()
