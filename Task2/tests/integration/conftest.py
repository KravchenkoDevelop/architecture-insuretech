"""
Fixtures for integration tests against a live Minikube cluster.

Prerequisites:
  - minikube start
  - minikube addons enable metrics-server
  - kubectl apply -f deployment.yaml -f service.yaml -f hpa.yaml
"""
import json
import os
import subprocess
import time

import pytest
import requests

TASK2_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
APP_NAME = "insuretech-app"
HPA_NAME  = "insuretech-app-hpa"
NAMESPACE = "default"


# ── helpers ────────────────────────────────────────────────────────────────

def kubectl(*args, check=True) -> subprocess.CompletedProcess:
    """Run a kubectl command and return the CompletedProcess."""
    cmd = ["kubectl", "-n", NAMESPACE, *args]
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


def kubectl_json(*args) -> dict | list:
    """Run kubectl with -o json and return parsed output."""
    result = kubectl(*args, "-o", "json")
    return json.loads(result.stdout)


def minikube(*args, check=True) -> subprocess.CompletedProcess:
    cmd = ["minikube", *args]
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


def wait_for_condition(condition_fn, timeout: int, interval: int = 5, label: str = ""):
    """Poll condition_fn every `interval` seconds until True or timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if condition_fn():
                return True
        except Exception:
            pass
        time.sleep(interval)
    raise TimeoutError(
        f"Condition '{label}' not met within {timeout}s"
    )


# ── session-scoped fixtures ────────────────────────────────────────────────

@pytest.fixture(scope="session")
def minikube_url() -> str:
    """Return the base URL for the insuretech-app service."""
    result = minikube("service", APP_NAME, "--url", "-n", NAMESPACE)
    url = result.stdout.strip()
    assert url.startswith("http"), f"Unexpected service URL: {url!r}"
    return url


@pytest.fixture(scope="session")
def app_url(minikube_url) -> str:
    return minikube_url


@pytest.fixture(scope="session")
def kubectl_fn():
    return kubectl


@pytest.fixture(scope="session")
def kubectl_json_fn():
    return kubectl_json


@pytest.fixture(scope="session")
def wait_fn():
    return wait_for_condition
