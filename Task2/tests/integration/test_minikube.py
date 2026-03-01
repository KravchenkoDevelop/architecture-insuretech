"""
Integration tests — шаги 1-2 README:
  Minikube запущен, metrics-server включён, манифесты применены.
"""
import subprocess
import pytest
from .conftest import minikube, kubectl, kubectl_json


class TestMinikubeCluster:
    """Minikube запущен и доступен."""

    def test_minikube_is_running(self):
        result = minikube("status", check=False)
        assert "Running" in result.stdout, (
            f"Minikube не запущен:\n{result.stdout}"
        )

    def test_kubectl_can_connect(self):
        result = kubectl("cluster-info", check=False)
        assert result.returncode == 0, (
            f"kubectl не может подключиться к кластеру:\n{result.stderr}"
        )

    def test_metrics_server_addon_enabled(self):
        result = minikube("addons", "list")
        assert "metrics-server" in result.stdout and "enabled" in result.stdout.lower(), (
            "metrics-server addon не включён. Запустите: minikube addons enable metrics-server"
        )

    def test_nodes_are_ready(self):
        data = kubectl_json("get", "nodes")
        nodes = data["items"]
        assert nodes, "В кластере нет нод"
        for node in nodes:
            conditions = node["status"]["conditions"]
            ready = next((c for c in conditions if c["type"] == "Ready"), None)
            assert ready and ready["status"] == "True", (
                f"Нода {node['metadata']['name']} не в состоянии Ready"
            )

    def test_metrics_server_pod_running(self):
        result = subprocess.run(
            ["kubectl", "-n", "kube-system", "get", "pods",
             "-l", "k8s-app=metrics-server", "-o", "json"],
            capture_output=True, text=True, check=True
        )
        import json
        pods = json.loads(result.stdout)["items"]
        assert pods, "metrics-server pod не найден в kube-system"
        for pod in pods:
            phase = pod["status"].get("phase")
            assert phase == "Running", (
                f"metrics-server pod в фазе {phase}, ожидается Running"
            )
