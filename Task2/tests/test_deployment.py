"""
Tests for Task2/deployment.yaml — Kubernetes Deployment manifest.
"""
import pytest


class TestDeploymentTopLevel:
    """Validate top-level fields of the Deployment manifest."""

    def test_api_version(self, deployment):
        assert deployment["apiVersion"] == "apps/v1", (
            "Deployment must use apiVersion apps/v1"
        )

    def test_kind(self, deployment):
        assert deployment["kind"] == "Deployment", (
            "Resource kind must be 'Deployment'"
        )

    def test_metadata_exists(self, deployment):
        assert "metadata" in deployment, "Deployment must have 'metadata' section"

    def test_metadata_name(self, deployment):
        assert deployment["metadata"]["name"] == "insuretech-app", (
            "Deployment name must be 'insuretech-app'"
        )

    def test_metadata_labels_exist(self, deployment):
        assert "labels" in deployment["metadata"], (
            "Deployment metadata must contain labels"
        )

    def test_metadata_label_app(self, deployment):
        labels = deployment["metadata"]["labels"]
        assert labels.get("app") == "insuretech-app", (
            "Deployment metadata label 'app' must be 'insuretech-app'"
        )


class TestDeploymentSpec:
    """Validate spec of the Deployment manifest."""

    def test_spec_exists(self, deployment):
        assert "spec" in deployment, "Deployment must have a 'spec' section"

    def test_replicas(self, deployment):
        assert deployment["spec"]["replicas"] == 1, (
            "Initial replica count must be 1"
        )

    def test_selector_exists(self, deployment):
        assert "selector" in deployment["spec"], (
            "Deployment spec must have a 'selector'"
        )

    def test_selector_match_labels(self, deployment):
        ml = deployment["spec"]["selector"].get("matchLabels", {})
        assert ml.get("app") == "insuretech-app", (
            "selector.matchLabels.app must be 'insuretech-app'"
        )

    def test_template_exists(self, deployment):
        assert "template" in deployment["spec"], (
            "Deployment spec must have a pod 'template'"
        )

    def test_template_metadata_labels(self, deployment):
        labels = deployment["spec"]["template"]["metadata"]["labels"]
        assert labels.get("app") == "insuretech-app", (
            "Pod template label 'app' must be 'insuretech-app'"
        )

    def test_selector_matches_template_labels(self, deployment):
        """Deployment selector must match pod template labels exactly."""
        selector = deployment["spec"]["selector"]["matchLabels"]
        pod_labels = deployment["spec"]["template"]["metadata"]["labels"]
        for key, val in selector.items():
            assert pod_labels.get(key) == val, (
                f"Template label '{key}={val}' not found in pod labels {pod_labels}"
            )


class TestDeploymentContainer:
    """Validate container spec inside the Deployment."""

    @pytest.fixture(scope="class")
    def container(self, deployment):
        containers = deployment["spec"]["template"]["spec"]["containers"]
        assert len(containers) >= 1, "At least one container must be defined"
        return containers[0]

    def test_container_name(self, container):
        assert container["name"] == "insuretech-app", (
            "Container name must be 'insuretech-app'"
        )

    def test_container_image(self, container):
        assert container["image"] == "registry.k8s.io/e2e-test-images/resource-consumer:1.13", (
            "Container image must be 'registry.k8s.io/e2e-test-images/resource-consumer:1.13'"
        )

    def test_container_port_defined(self, container):
        ports = container.get("ports", [])
        assert len(ports) >= 1, "Container must expose at least one port"

    def test_container_port_8080(self, container):
        ports = container.get("ports", [])
        port_numbers = [p["containerPort"] for p in ports]
        assert 8080 in port_numbers, "Container must expose port 8080"

    def test_resources_defined(self, container):
        assert "resources" in container, (
            "Container must define resource requests/limits"
        )

    def test_resource_requests_memory(self, container, parse_mem):
        mem_str = container["resources"]["requests"]["memory"]
        mem_mi = parse_mem(mem_str)
        assert mem_mi == 15.0, (
            f"Memory request must be 15Mi, got {mem_str!r}"
        )

    def test_resource_requests_cpu(self, container, parse_cpu):
        cpu_str = container["resources"]["requests"]["cpu"]
        cpu_m = parse_cpu(cpu_str)
        assert cpu_m == 50.0, (
            f"CPU request must be 50m, got {cpu_str!r}"
        )

    def test_resource_limits_memory(self, container, parse_mem):
        mem_str = container["resources"]["limits"]["memory"]
        mem_mi = parse_mem(mem_str)
        assert mem_mi == 30.0, (
            f"Memory limit must be 30Mi, got {mem_str!r}"
        )

    def test_resource_limits_cpu(self, container, parse_cpu):
        cpu_str = container["resources"]["limits"]["cpu"]
        cpu_m = parse_cpu(cpu_str)
        assert cpu_m == 200.0, (
            f"CPU limit must be 200m, got {cpu_str!r}"
        )

    def test_requests_not_exceed_limits_memory(self, container, parse_mem):
        req = parse_mem(container["resources"]["requests"]["memory"])
        lim = parse_mem(container["resources"]["limits"]["memory"])
        assert req <= lim, (
            f"Memory request ({req}Mi) must not exceed limit ({lim}Mi)"
        )

    def test_requests_not_exceed_limits_cpu(self, container, parse_cpu):
        req = parse_cpu(container["resources"]["requests"]["cpu"])
        lim = parse_cpu(container["resources"]["limits"]["cpu"])
        assert req <= lim, (
            f"CPU request ({req}m) must not exceed limit ({lim}m)"
        )

    def test_memory_limit_reasonable(self, container, parse_mem):
        """Memory limit should be in a reasonable range for a small service."""
        mem_mi = parse_mem(container["resources"]["limits"]["memory"])
        assert 10 <= mem_mi <= 512, (
            f"Memory limit {mem_mi}Mi is outside expected range [10Mi, 512Mi]"
        )

    def test_memory_request_is_half_of_limit(self, container, parse_mem):
        """Request should be 50% of limit (15Mi / 30Mi = 0.5)."""
        req = parse_mem(container["resources"]["requests"]["memory"])
        lim = parse_mem(container["resources"]["limits"]["memory"])
        ratio = req / lim
        assert abs(ratio - 0.5) < 1e-9, (
            f"Memory request/limit ratio must be 0.5, got {ratio:.4f}"
        )
