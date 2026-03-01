"""
Tests for Task2/hpa.yaml — Kubernetes HorizontalPodAutoscaler manifest.
"""
import pytest


class TestHPATopLevel:
    """Validate top-level fields of the HPA manifest."""

    def test_api_version(self, hpa):
        assert hpa["apiVersion"] == "autoscaling/v2", (
            "HPA must use apiVersion 'autoscaling/v2'"
        )

    def test_kind(self, hpa):
        assert hpa["kind"] == "HorizontalPodAutoscaler", (
            "Resource kind must be 'HorizontalPodAutoscaler'"
        )

    def test_metadata_exists(self, hpa):
        assert "metadata" in hpa, "HPA must have 'metadata' section"

    def test_metadata_name(self, hpa):
        assert hpa["metadata"]["name"] == "insuretech-app-hpa", (
            "HPA name must be 'insuretech-app-hpa'"
        )


class TestHPASpec:
    """Validate spec of the HPA manifest."""

    def test_spec_exists(self, hpa):
        assert "spec" in hpa, "HPA must have a 'spec' section"

    def test_scale_target_ref_exists(self, hpa):
        assert "scaleTargetRef" in hpa["spec"], (
            "HPA spec must define 'scaleTargetRef'"
        )

    def test_scale_target_ref_api_version(self, hpa):
        ref = hpa["spec"]["scaleTargetRef"]
        assert ref.get("apiVersion") == "apps/v1", (
            "scaleTargetRef.apiVersion must be 'apps/v1'"
        )

    def test_scale_target_ref_kind(self, hpa):
        ref = hpa["spec"]["scaleTargetRef"]
        assert ref.get("kind") == "Deployment", (
            "scaleTargetRef.kind must be 'Deployment'"
        )

    def test_scale_target_ref_name(self, hpa):
        ref = hpa["spec"]["scaleTargetRef"]
        assert ref.get("name") == "insuretech-app", (
            "scaleTargetRef.name must be 'insuretech-app'"
        )

    def test_min_replicas(self, hpa):
        assert hpa["spec"]["minReplicas"] == 1, (
            "minReplicas must be 1"
        )

    def test_max_replicas(self, hpa):
        assert hpa["spec"]["maxReplicas"] == 10, (
            "maxReplicas must be 10"
        )

    def test_min_less_than_max(self, hpa):
        assert hpa["spec"]["minReplicas"] < hpa["spec"]["maxReplicas"], (
            "minReplicas must be strictly less than maxReplicas"
        )

    def test_max_replicas_reasonable(self, hpa):
        """maxReplicas should be in a reasonable operational range."""
        max_r = hpa["spec"]["maxReplicas"]
        assert 2 <= max_r <= 100, (
            f"maxReplicas={max_r} is outside expected range [2, 100]"
        )

    def test_metrics_defined(self, hpa):
        metrics = hpa["spec"].get("metrics", [])
        assert len(metrics) >= 1, "HPA spec must define at least one metric"


class TestHPAMemoryMetric:
    """Validate the memory metric configuration in the HPA."""

    @pytest.fixture(scope="class")
    def memory_metric(self, hpa):
        metrics = hpa["spec"]["metrics"]
        mem = [m for m in metrics if m.get("resource", {}).get("name") == "memory"]
        assert mem, "HPA must have a memory resource metric"
        return mem[0]

    def test_metric_type_resource(self, memory_metric):
        assert memory_metric["type"] == "Resource", (
            "Memory metric type must be 'Resource'"
        )

    def test_metric_resource_name(self, memory_metric):
        assert memory_metric["resource"]["name"] == "memory", (
            "Resource metric name must be 'memory'"
        )

    def test_metric_target_type_utilization(self, memory_metric):
        target = memory_metric["resource"]["target"]
        assert target["type"] == "Utilization", (
            "Memory metric target type must be 'Utilization'"
        )

    def test_metric_average_utilization(self, memory_metric):
        util = memory_metric["resource"]["target"]["averageUtilization"]
        assert util == 80, (
            f"averageUtilization must be 80, got {util}"
        )

    def test_utilization_in_safe_range(self, memory_metric):
        """Utilization target should be within a practical operating range."""
        util = memory_metric["resource"]["target"]["averageUtilization"]
        assert 50 <= util <= 90, (
            f"averageUtilization={util}% is outside practical range [50%, 90%]"
        )


class TestHPAMemoryThreshold:
    """
    Business logic: verify that the effective memory threshold matches
    the formula: limit * averageUtilization / 100.
    Expected: 30Mi * 80% = 24Mi.
    """

    def test_memory_scale_trigger_threshold_mib(self, hpa, deployment, parse_mem):
        mem_limit_str = (
            deployment["spec"]["template"]["spec"]["containers"][0]
            ["resources"]["limits"]["memory"]
        )
        limit_mi = parse_mem(mem_limit_str)

        util = hpa["spec"]["metrics"][0]["resource"]["target"]["averageUtilization"]
        trigger_mi = limit_mi * util / 100

        assert trigger_mi == pytest.approx(24.0), (
            f"Scale trigger threshold must be 24Mi (30Mi * 80%), got {trigger_mi}Mi"
        )
