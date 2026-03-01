"""
Tests for Task2/locustfile.py — Locust load test scenario.

Tests cover:
- Module importability
- WebsiteUser class structure (inheritance, tasks, wait_time)
- HTTP task behaviour via mocked client
"""
import importlib.util
import os
import sys
import types
from unittest.mock import MagicMock, patch, call

import pytest

TASK2_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LOCUSTFILE = os.path.join(TASK2_DIR, "locustfile.py")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_locustfile_module():
    """
    Load locustfile.py dynamically so tests are independent of locust being
    installed globally.  We stub the 'locust' package if it is not available.
    """
    # Build a minimal locust stub so the import always succeeds
    if "locust" not in sys.modules:
        locust_stub = types.ModuleType("locust")

        class _HttpUser:
            abstract = True

        def _between(lo, hi):
            return (lo, hi)

        def _task(fn):
            fn._is_task = True
            fn._task_weight = 1
            return fn

        locust_stub.HttpUser = _HttpUser
        locust_stub.between = _between
        locust_stub.task = _task
        sys.modules["locust"] = locust_stub

    spec = importlib.util.spec_from_file_location("locustfile", LOCUSTFILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def locust_module():
    return _load_locustfile_module()


@pytest.fixture(scope="module")
def HttpUser(locust_module):
    return sys.modules["locust"].HttpUser


@pytest.fixture(scope="module")
def website_user_cls(locust_module):
    cls = getattr(locust_module, "WebsiteUser", None)
    assert cls is not None, "locustfile.py must define a 'WebsiteUser' class"
    return cls


# ---------------------------------------------------------------------------
# Structure tests
# ---------------------------------------------------------------------------

class TestLocustfileImport:
    def test_file_exists(self):
        assert os.path.isfile(LOCUSTFILE), (
            f"locustfile.py not found at {LOCUSTFILE}"
        )

    def test_module_loads_without_error(self, locust_module):
        assert locust_module is not None

    def test_module_has_website_user(self, locust_module):
        assert hasattr(locust_module, "WebsiteUser"), (
            "locustfile.py must export a 'WebsiteUser' class"
        )


class TestWebsiteUserClass:
    def test_inherits_http_user(self, website_user_cls, HttpUser):
        assert issubclass(website_user_cls, HttpUser), (
            "WebsiteUser must inherit from locust.HttpUser"
        )

    def test_wait_time_defined(self, website_user_cls):
        assert hasattr(website_user_cls, "wait_time"), (
            "WebsiteUser must define 'wait_time'"
        )

    def test_wait_time_is_callable_or_tuple(self, website_user_cls):
        wt = website_user_cls.wait_time
        assert callable(wt) or isinstance(wt, tuple), (
            "wait_time must be callable (e.g. between()) or a tuple"
        )

    def test_wait_time_between_1_and_5(self, website_user_cls):
        """
        between(1, 5) returns the tuple (1, 5) in our stub.
        Verify the configured bounds.
        """
        wt = website_user_cls.wait_time
        if isinstance(wt, tuple):
            lo, hi = wt
            assert lo == 1, f"wait_time lower bound must be 1, got {lo}"
            assert hi == 5, f"wait_time upper bound must be 5, got {hi}"
        else:
            # If the real locust is installed, between() returns a callable.
            # We at least verify it is callable.
            assert callable(wt)

    def test_has_index_method(self, website_user_cls):
        assert hasattr(website_user_cls, "index"), (
            "WebsiteUser must define an 'index' method"
        )

    def test_index_is_task(self, website_user_cls):
        """index method must be decorated with @task."""
        method = getattr(website_user_cls, "index")
        assert callable(method), "WebsiteUser.index must be callable"
        # Our stub sets _is_task=True; real locust uses task_weight attr
        has_task_marker = (
            getattr(method, "_is_task", False)
            or hasattr(method, "task_weight")
            or getattr(method, "locust_task_weight", None) is not None
        )
        assert has_task_marker, (
            "WebsiteUser.index must be decorated with @task"
        )

    def test_no_extra_public_tasks(self, website_user_cls):
        """
        The only public non-dunder method should be 'index'.
        This guards against unintended task additions.
        """
        public_methods = [
            name for name in dir(website_user_cls)
            if not name.startswith("_")
            and callable(getattr(website_user_cls, name))
            and name not in {"wait_time", "abstract"}
        ]
        # Filter to only the methods actually defined on the class (not inherited)
        own_methods = [
            name for name in public_methods
            if name in website_user_cls.__dict__
        ]
        assert own_methods == ["index"], (
            f"Expected only ['index'] task, found {own_methods}"
        )


class TestIndexTask:
    """Verify that the index task calls GET /."""

    def test_index_calls_get_root(self, website_user_cls):
        """
        Instantiate WebsiteUser with a mocked HTTP client and verify
        that index() calls GET /.
        """
        user = object.__new__(website_user_cls)
        mock_client = MagicMock()
        user.client = mock_client

        user.index()

        mock_client.get.assert_called_once_with("/")

    def test_index_called_multiple_times(self, website_user_cls):
        """Each call to index() must issue exactly one GET /."""
        user = object.__new__(website_user_cls)
        mock_client = MagicMock()
        user.client = mock_client

        for _ in range(3):
            user.index()

        assert mock_client.get.call_count == 3
        mock_client.get.assert_called_with("/")

    def test_index_does_not_call_post(self, website_user_cls):
        user = object.__new__(website_user_cls)
        mock_client = MagicMock()
        user.client = mock_client

        user.index()

        mock_client.post.assert_not_called()

    def test_index_does_not_call_put(self, website_user_cls):
        user = object.__new__(website_user_cls)
        mock_client = MagicMock()
        user.client = mock_client

        user.index()

        mock_client.put.assert_not_called()

    def test_index_does_not_call_delete(self, website_user_cls):
        user = object.__new__(website_user_cls)
        mock_client = MagicMock()
        user.client = mock_client

        user.index()

        mock_client.delete.assert_not_called()
