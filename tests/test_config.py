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


# -- Pipeline B's three knobs --


def test_pipeline_b_defaults_are_the_documented_ones():
    with mock.patch.dict(os.environ, {}, clear=True):
        assert config.max_scene_chars() == 8000
        assert config.max_searches_per_check() == 8
        assert config.check_timeout_seconds() == 180


def test_the_scene_cap_still_matches_the_treatment_cap_it_was_copied_from():
    """The 8,000-character scene cap is an assumption, not a measurement: it
    was carried over from the treatment cap on the grounds that the two pastes
    are the same order of size. This test is where that assumption is written
    down, so confirming it (or moving it) is a deliberate act rather than a
    silent drift in one of the two numbers."""
    with mock.patch.dict(os.environ, {}, clear=True):
        assert config.max_scene_chars() == config.max_treatment_chars()


def test_a_check_costs_far_fewer_searches_than_a_build():
    """A check starts from a room that has already been researched and only
    pays for what the room's files do not answer."""
    with mock.patch.dict(os.environ, {}, clear=True):
        assert config.max_searches_per_check() < config.max_searches_per_build()


def test_the_check_ceiling_leaves_room_under_cloud_runs_request_timeout():
    """A check is answered inside the request that asked for it, so its
    ceiling has to fit under Cloud Run's 900s with room to spare — see
    scripts/deploy.sh's --timeout=900."""
    with mock.patch.dict(os.environ, {}, clear=True):
        assert config.check_timeout_seconds() < 900


def test_env_overrides_every_pipeline_b_knob():
    env = {
        "STAR_MAX_SCENE_CHARS": "1200",
        "STAR_MAX_SEARCHES_PER_CHECK": "2",
        "STAR_CHECK_TIMEOUT_SECONDS": "45",
    }
    with mock.patch.dict(os.environ, env):
        assert config.max_scene_chars() == 1200
        assert config.max_searches_per_check() == 2
        assert config.check_timeout_seconds() == 45


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


# -- Vertex: the key stops being required and WHERE starts being required -----


def test_validate_env_stops_demanding_an_api_key_under_vertex():
    """Vertex authenticates with the runtime's own identity. Demanding an AI
    Studio key alongside it would make the deploy carry a credential nothing
    reads."""
    env = {
        "PARALLEL_API_KEY": "x",
        "FIREBASE_API_KEY": "x",
        "GOOGLE_GENAI_USE_VERTEXAI": "TRUE",
        "GOOGLE_CLOUD_PROJECT": "star-project",
        "GOOGLE_CLOUD_LOCATION": "global",
    }
    with mock.patch.dict(os.environ, env, clear=True):
        config.validate_env()  # must not raise


def test_validate_env_requires_a_location_under_vertex():
    """The failure this catches is the expensive one. With no location
    google-genai picks a default region, the pinned model is published only to
    `global` on Vertex, and the 404 lands on the FIRST model call — minutes
    after intake accepted the treatment and told the writer it was working."""
    env = {
        "PARALLEL_API_KEY": "x",
        "FIREBASE_API_KEY": "x",
        "GOOGLE_GENAI_USE_VERTEXAI": "TRUE",
        "GOOGLE_CLOUD_PROJECT": "star-project",
    }
    with (
        mock.patch.dict(os.environ, env, clear=True),
        pytest.raises(RuntimeError, match="GOOGLE_CLOUD_LOCATION"),
    ):
        config.validate_env()


def test_validate_env_requires_a_project_under_vertex():
    env = {
        "PARALLEL_API_KEY": "x",
        "FIREBASE_API_KEY": "x",
        "FIREBASE_PROJECT_ID": "star-project",
        "GOOGLE_GENAI_USE_VERTEXAI": "TRUE",
        "GOOGLE_CLOUD_LOCATION": "global",
    }
    with (
        mock.patch.dict(os.environ, env, clear=True),
        pytest.raises(RuntimeError, match="GOOGLE_CLOUD_PROJECT"),
    ):
        config.validate_env()
