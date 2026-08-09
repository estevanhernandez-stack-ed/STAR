"""Model IDs must stay pinned, not floating.

`-latest` aliases move whenever Google ships. A model shift during a
rehearsed demo is an avoidable loss, so the defaults are versioned and this
test fails if anyone reintroduces an alias.
"""

import os
from unittest import mock

from star import config


def test_default_models_are_pinned_not_aliases():
    with mock.patch.dict(os.environ, {}, clear=True):
        for model in (config.fast_model(), config.smart_model()):
            assert "latest" not in model, f"{model} is a floating alias"
            assert model[0].isalpha() and any(ch.isdigit() for ch in model)


def test_env_still_overrides_the_pin():
    with mock.patch.dict(os.environ, {"STAR_FAST_MODEL": "gemini-2.0-flash-001"}):
        assert config.fast_model() == "gemini-2.0-flash-001"
