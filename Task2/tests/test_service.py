"""
Tests for Task2/service.yaml — Kubernetes Service manifest.
"""
import pytest


class TestServiceTopLevel:
    """Validate top-level fields of the Service manifest."""

    def test_api_version(self, service):
        assert service["apiVersion"] == "v1", (
            "Service must use apiVersion 'v1'"
        )

    def test_kind(self, service):
        assert service["kind"] == "Service", (
            "Resource kind must be 'Service'"
        )

    def test_metadata_exists(self, service):
        assert "metadata" in service, "Service must have 'metadata' section"

    def test_metadata_name(self, service):
        assert service["metadata"]["name"] == "insuretech-app", (
            "Service name must be 'insuretech-app'"
        )

    def test_metadata_labels_exist(self, service):
        assert "labels" in service["metadata"], (
            "Service metadata must contain labels"
        )

    def test_metadata_label_app(self, service):
        labels = service["metadata"]["labels"]
        assert labels.get("app") == "insuretech-app", (
            "Service metadata label 'app' must be 'insuretech-app'"
        )


class TestServiceSpec:
    """Validate spec of the Service manifest."""

    def test_spec_exists(self, service):
        assert "spec" in service, "Service must have a 'spec' section"

    def test_type_nodeport(self, service):
        assert service["spec"]["type"] == "NodePort", (
            "Service type must be 'NodePort'"
        )

    def test_selector_exists(self, service):
        assert "selector" in service["spec"], (
            "Service spec must have a 'selector'"
        )

    def test_selector_app(self, service):
        assert service["spec"]["selector"].get("app") == "insuretech-app", (
            "Service selector 'app' must be 'insuretech-app'"
        )

    def test_ports_defined(self, service):
        ports = service["spec"].get("ports", [])
        assert len(ports) >= 1, "Service must define at least one port"

    @pytest.fixture(scope="class")
    def http_port(self, service):
        ports = service["spec"]["ports"]
        named = [p for p in ports if p.get("name") == "http"]
        assert named, "Service must have a port named 'http'"
        return named[0]

    def test_port_name_http(self, http_port):
        assert http_port["name"] == "http", "Port name must be 'http'"

    def test_port_protocol_tcp(self, http_port):
        assert http_port["protocol"] == "TCP", (
            "Port protocol must be 'TCP'"
        )

    def test_port_number(self, http_port):
        assert http_port["port"] == 8080, (
            "Service port must be 8080"
        )

    def test_target_port(self, http_port):
        assert http_port["targetPort"] == 8080, (
            "Service targetPort must be 8080"
        )

    def test_port_and_target_port_match(self, http_port):
        assert http_port["port"] == http_port["targetPort"], (
            "port and targetPort must match for single-container setup"
        )

    def test_nodeport_range_if_set(self, service):
        """NodePort value, if explicitly set, must be in 30000–32767."""
        for port in service["spec"]["ports"]:
            node_port = port.get("nodePort")
            if node_port is not None:
                assert 30000 <= node_port <= 32767, (
                    f"nodePort {node_port} is outside valid range 30000-32767"
                )
