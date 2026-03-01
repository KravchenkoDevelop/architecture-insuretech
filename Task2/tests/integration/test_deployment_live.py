"""
Integration tests — шаги 2-4 README:
  Deployment и Service применены, приложение отвечает на запросы.
"""
import time
import requests
import pytest
from .conftest import kubectl, kubectl_json, wait_for_condition

APP_NAME  = "insuretech-app"
NAMESPACE = "default"


class TestDeploymentLive:
    """Deployment существует и поды запущены."""

    def test_deployment_exists(self):
        result = kubectl("get", "deployment", APP_NAME, check=False)
        assert result.returncode == 0, (
            f"Deployment '{APP_NAME}' не найден. Запустите: kubectl apply -f deployment.yaml"
        )

    def test_deployment_available_replicas(self):
        data = kubectl_json("get", "deployment", APP_NAME)
        status = data["status"]
        available = status.get("availableReplicas", 0)
        assert available >= 1, (
            f"Ожидается минимум 1 доступная реплика, получено {available}"
        )

    def test_pods_are_running(self):
        data = kubectl_json("get", "pods", "-l", f"app={APP_NAME}")
        pods = data["items"]
        assert pods, f"Нет подов с меткой app={APP_NAME}"
        for pod in pods:
            phase = pod["status"].get("phase")
            assert phase == "Running", (
                f"Pod {pod['metadata']['name']} в фазе {phase}, ожидается Running"
            )

    def test_pods_containers_ready(self):
        data = kubectl_json("get", "pods", "-l", f"app={APP_NAME}")
        for pod in data["items"]:
            for cs in pod["status"].get("containerStatuses", []):
                assert cs["ready"], (
                    f"Контейнер {cs['name']} в поде {pod['metadata']['name']} не Ready"
                )

    def test_pod_restart_count_is_low(self):
        """Частые рестарты указывают на OOMKill или crashloop."""
        data = kubectl_json("get", "pods", "-l", f"app={APP_NAME}")
        for pod in data["items"]:
            for cs in pod["status"].get("containerStatuses", []):
                restarts = cs.get("restartCount", 0)
                assert restarts < 5, (
                    f"Pod {pod['metadata']['name']} имеет {restarts} рестартов — возможен OOMKill"
                )

    def test_wait_for_deployment_ready(self):
        """kubectl rollout status должен завершиться успешно."""
        result = kubectl(
            "rollout", "status", "deployment", APP_NAME,
            "--timeout=120s"
        )
        assert result.returncode == 0, (
            f"Deployment не стал Ready за 120 сек:\n{result.stderr}"
        )


class TestServiceLive:
    """Service существует и маршрутизирует трафик."""

    def test_service_exists(self):
        result = kubectl("get", "svc", APP_NAME, check=False)
        assert result.returncode == 0, (
            f"Service '{APP_NAME}' не найден. Запустите: kubectl apply -f service.yaml"
        )

    def test_service_has_endpoints(self):
        data = kubectl_json("get", "endpoints", APP_NAME)
        subsets = data.get("subsets", [])
        assert subsets, (
            f"Service '{APP_NAME}' не имеет endpoints — поды не прошли readiness check"
        )
        addresses = subsets[0].get("addresses", [])
        assert addresses, "Нет доступных адресов в endpoints"

    def test_app_responds_on_root(self, app_url):
        """GET / возвращает HTTP 200."""
        resp = requests.get(f"{app_url}/", timeout=10)
        assert resp.status_code == 200, (
            f"GET / вернул {resp.status_code}, ожидается 200"
        )

    def test_app_responds_within_1s(self, app_url):
        """Приложение отвечает менее чем за 1 секунду (без нагрузки)."""
        resp = requests.get(f"{app_url}/", timeout=10)
        assert resp.elapsed.total_seconds() < 1.0, (
            f"Время ответа {resp.elapsed.total_seconds():.3f}s > 1s"
        )

    def test_app_responds_10_consecutive(self, app_url):
        """10 последовательных запросов — все успешны."""
        for i in range(10):
            resp = requests.get(f"{app_url}/", timeout=10)
            assert resp.status_code == 200, (
                f"Запрос #{i+1} вернул {resp.status_code}"
            )
