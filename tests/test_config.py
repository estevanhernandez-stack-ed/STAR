"""Model IDs must stay pinned, not floating.

`-latest` aliases move whenever Google ships. A model shift during a
rehearsed demo is an avoidable loss, so the defaults are versioned and this
test fails if anyone reintroduces an alias.
"""

import os
from unittest import mock

import pytest

from star import config


def test_default_models_are_pinned_not_aliases():
    with mock.patch.dict(os.environ, {}, clear=True):
        for model in (config.fast_model(), config.smart_model()):
            assert "latest" not in model, f"{model} is a floating alias"
            assert model[0].isalpha() and any(ch.isdigit() for ch in model)


def test_env_still_overrides_the_pin():
    with mock.patch.dict(os.environ, {"STAR_FAST_MODEL": "gemini-2.0-flash-001"}):
        assert config.fast_model() == "gemini-2.0-flash-001"


# -- Finding 4: validate_env must catch the vars Phase 2 made load-bearing --

_BASE_ENV = {"PARALLEL_API_KEY": "x", "GOOGLE_API_KEY": "x"}


def test_validate_env_requires_a_firebase_project_id_or_google_cloud_project():
    env = {**_BASE_ENV, "FIREBASE_API_KEY": "x"}
    with (
        mock.patch.dict(os.environ, env, clear=True),
        pytest.raises(RuntimeError, match="FIREBASE_PROJECT_ID"),
    ):
        config.validate_env()


def test_validate_env_accepts_google_cloud_project_as_a_substitute_for_firebase_project_id():
    """star/auth.py and star/store.py both fall back to GOOGLE_CLOUD_PROJECT,
    so validate_env must accept the same substitute rather than demanding a
    variable the code doesn't actually require."""
    env = {**_BASE_ENV, "FIREBASE_API_KEY": "x", "GOOGLE_CLOUD_PROJECT": "star-project"}
    with mock.patch.dict(os.environ, env, clear=True):
        config.validate_env()  # must not raise


def test_validate_env_accepts_firebase_project_id_alone():
    env = {**_BASE_ENV, "FIREBASE_API_KEY": "x", "FIREBASE_PROJECT_ID": "star-project"}
    with mock.patch.dict(os.environ, env, clear=True):
        config.validate_env()  # must not raise


def test_validate_env_requires_a_firebase_api_key():
    """Missing this fails closed but silently: /config.js would serve an
    empty apiKey to the browser and every sign-in attempt would just fail."""
    env = {**_BASE_ENV, "FIREBASE_PROJECT_ID": "star-project"}
    with (
        mock.patch.dict(os.environ, env, clear=True),
        pytest.raises(RuntimeError, match="FIREBASE_API_KEY"),
    ):
        config.validate_env()


def test_validate_env_passes_with_every_phase_2_variable_present():
    env = {
        **_BASE_ENV,
        "FIREBASE_PROJECT_ID": "star-project",
        "FIREBASE_API_KEY": "x",
    }
    with mock.patch.dict(os.environ, env, clear=True):
        config.validate_env()  # must not raise
