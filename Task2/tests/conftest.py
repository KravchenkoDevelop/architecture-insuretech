"""
Shared fixtures for Task2 tests.
Loads and parses all Kubernetes manifests from the Task2 directory.
"""
import os
import re
import pytest
import yaml

TASK2_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def load_yaml(filename: str) -> dict:
    path = os.path.join(TASK2_DIR, filename)
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def parse_memory_mi(value: str) -> float:
    """Convert Kubernetes memory string (e.g. '30Mi', '15Mi') to float MiB."""
    m = re.fullmatch(r"(\d+(?:\.\d+)?)Mi", str(value))
    if m:
        return float(m.group(1))
    m = re.fullmatch(r"(\d+(?:\.\d+)?)Gi", str(value))
    if m:
        return float(m.group(1)) * 1024
    m = re.fullmatch(r"(\d+(?:\.\d+)?)Ki", str(value))
    if m:
        return float(m.group(1)) / 1024
    raise ValueError(f"Cannot parse memory value: {value!r}")


def parse_cpu_millicores(value: str) -> float:
    """Convert Kubernetes CPU string (e.g. '50m', '200m', '1') to millicores."""
    s = str(value)
    if s.endswith("m"):
        return float(s[:-1])
    return float(s) * 1000


@pytest.fixture(scope="session")
def deployment() -> dict:
    return load_yaml("deployment.yaml")


@pytest.fixture(scope="session")
def service() -> dict:
    return load_yaml("service.yaml")


@pytest.fixture(scope="session")
def hpa() -> dict:
    return load_yaml("hpa.yaml")


@pytest.fixture(scope="session")
def parse_mem():
    return parse_memory_mi


@pytest.fixture(scope="session")
def parse_cpu():
    return parse_cpu_millicores
