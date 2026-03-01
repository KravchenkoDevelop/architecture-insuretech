"""
Cross-manifest consistency tests for Task2.

These tests verify that the three Kubernetes manifests
(Deployment, Service, HPA) form a coherent, self-consistent configuration.
"""
import pytest


class TestDeploymentServiceConsistency:
    """Service must route traffic to the pods described in Deployment."""

    def test_service_selector_targets_deployment_pods(self, deployment, service):
        """Every Service selector label must appear in the pod template labels."""
        service_selector = service["spec"]["selector"]
        pod_labels = deployment["spec"]["template"]["metadata"]["labels"]
        for key, val in service_selector.items():
            assert pod_labels.get(key) == val, (
                f"Service selector '{key}={val}' does not match "
                f"pod template label '{key}={pod_labels.get(key)}'"
            )

    def test_service_port_matches_container_port(self, deployment, service):
        """Service targetPort must match a containerPort exposed in Deployment."""
        container_ports = {
            p["containerPort"]
            for p in deployment["spec"]["template"]["spec"]["containers"][0].get("ports", [])
        }
        for svc_port in service["spec"]["ports"]:
            tp = svc_port["targetPort"]
            assert tp in container_ports, (
                f"Service targetPort {tp} is not exposed by any container "
                f"(containerPorts: {container_ports})"
            )

    def test_service_and_deployment_share_name(self, deployment, service):
        """Service and Deployment should share the same application name."""
        assert deployment["metadata"]["name"] == service["metadata"]["name"], (
            "Service and Deployment should have the same metadata.name "
            f"({service['metadata']['name']!r} vs {deployment['metadata']['name']!r})"
        )

    def test_service_selector_not_empty(self, service):
        selector = service["spec"].get("selector", {})
        assert selector, "Service selector must not be empty"


class TestDeploymentHPAConsistency:
    """HPA must reference the exact Deployment it is intended to scale."""

    def test_hpa_targets_correct_deployment_name(self, deployment, hpa):
        dep_name = deployment["metadata"]["name"]
        hpa_target = hpa["spec"]["scaleTargetRef"]["name"]
        assert hpa_target == dep_name, (
            f"HPA scaleTargetRef.name '{hpa_target}' does not match "
            f"Deployment name '{dep_name}'"
        )

    def test_hpa_targets_correct_api_version(self, deployment, hpa):
        dep_api = deployment["apiVersion"]
        hpa_api = hpa["spec"]["scaleTargetRef"]["apiVersion"]
        assert hpa_api == dep_api, (
            f"HPA scaleTargetRef.apiVersion '{hpa_api}' does not match "
            f"Deployment apiVersion '{dep_api}'"
        )

    def test_hpa_targets_deployment_kind(self, hpa):
        assert hpa["spec"]["scaleTargetRef"]["kind"] == "Deployment", (
            "HPA must target a Deployment kind"
        )

    def test_hpa_min_replicas_matches_deployment_replicas(self, deployment, hpa):
        """Initial replicas must equal HPA minReplicas — otherwise HPA would
        immediately scale down on first reconciliation."""
        dep_replicas = deployment["spec"]["replicas"]
        hpa_min = hpa["spec"]["minReplicas"]
        assert dep_replicas == hpa_min, (
            f"Deployment replicas ({dep_replicas}) must equal "
            f"HPA minReplicas ({hpa_min})"
        )

    def test_hpa_max_replicas_greater_than_initial(self, deployment, hpa):
        """maxReplicas must allow scaling beyond the initial replica count."""
        dep_replicas = deployment["spec"]["replicas"]
        hpa_max = hpa["spec"]["maxReplicas"]
        assert hpa_max > dep_replicas, (
            f"HPA maxReplicas ({hpa_max}) must be greater than "
            f"initial replicas ({dep_replicas})"
        )


class TestThreeManifestNamingConsistency:
    """All three manifests must refer to the same application name."""

    def test_all_manifests_share_app_label(self, deployment, service, hpa):
        dep_label = deployment["metadata"]["labels"]["app"]
        svc_label = service["metadata"]["labels"]["app"]
        # HPA may not have an app label, so only check deployment and service
        assert dep_label == svc_label, (
            f"app label mismatch: Deployment='{dep_label}', Service='{svc_label}'"
        )

    def test_hpa_name_references_app(self, deployment, hpa):
        dep_name = deployment["metadata"]["name"]
        hpa_name = hpa["metadata"]["name"]
        assert dep_name in hpa_name, (
            f"HPA name '{hpa_name}' should contain Deployment name '{dep_name}'"
        )


class TestResourceBudget:
    """Validate that HPA scale-out stays within reasonable resource bounds."""

    def test_max_replicas_total_memory_limit(self, deployment, hpa, parse_mem):
        """
        At maxReplicas the total memory ceiling must not exceed a
        reasonable cluster budget (example: 300Mi for a small dev cluster).
        """
        limit_mi = parse_mem(
            deployment["spec"]["template"]["spec"]["containers"][0]
            ["resources"]["limits"]["memory"]
        )
        max_r = hpa["spec"]["maxReplicas"]
        total_mi = limit_mi * max_r
        # 300Mi is a reasonable dev-cluster guard-rail
        assert total_mi <= 300, (
            f"At maxReplicas={max_r}, total memory limit is {total_mi}Mi "
            f"which exceeds 300Mi guard-rail"
        )

    def test_max_replicas_total_cpu_limit(self, deployment, hpa, parse_cpu):
        """Total CPU ceiling at maxReplicas must be <= 2000m (2 cores)."""
        cpu_m = parse_cpu(
            deployment["spec"]["template"]["spec"]["containers"][0]
            ["resources"]["limits"]["cpu"]
        )
        max_r = hpa["spec"]["maxReplicas"]
        total_m = cpu_m * max_r
        assert total_m <= 2000, (
            f"At maxReplicas={max_r}, total CPU limit is {total_m}m "
            f"which exceeds 2000m guard-rail"
        )
