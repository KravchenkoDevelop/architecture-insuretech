"""
Integration tests — шаг 6 README:
  kubectl get pods --watch

Проверяем состояние подов в процессе работы кластера:
переходы фаз, отсутствие OOMKill, корректные лимиты ресурсов.
"""
import time
import pytest
from .conftest import kubectl, kubectl_json, wait_for_condition

APP_NAME  = "insuretech-app"
NAMESPACE = "default"


class TestPodWatch:
    """Наблюдение за состоянием подов (аналог kubectl get pods --watch)."""

    def test_all_pods_running(self):
        data = kubectl_json("get", "pods", "-l", f"app={APP_NAME}")
        pods = data["items"]
        assert pods, f"Нет подов с меткой app={APP_NAME}"
        for pod in pods:
            phase = pod["status"].get("phase")
            assert phase == "Running", (
                f"Pod {pod['metadata']['name']} в фазе '{phase}'"
            )

    def test_no_pods_in_crashloop(self):
        data = kubectl_json("get", "pods", "-l", f"app={APP_NAME}")
        for pod in data["items"]:
            for cs in pod["status"].get("containerStatuses", []):
                state = cs.get("state", {})
                waiting = state.get("waiting", {})
                assert "CrashLoop" not in waiting.get("reason", ""), (
                    f"Pod {pod['metadata']['name']} в CrashLoopBackOff"
                )

    def test_no_oomkilled_pods(self):
        """Ни один под не был убит из-за превышения лимита памяти."""
        data = kubectl_json("get", "pods", "-l", f"app={APP_NAME}")
        for pod in data["items"]:
            for cs in pod["status"].get("containerStatuses", []):
                last = cs.get("lastState", {}).get("terminated", {})
                assert last.get("reason") != "OOMKilled", (
                    f"Pod {pod['metadata']['name']} был OOMKilled. "
                    "Возможно, нужно увеличить limits.memory в deployment.yaml"
                )

    def test_pod_names_contain_app_name(self):
        data = kubectl_json("get", "pods", "-l", f"app={APP_NAME}")
        for pod in data["items"]:
            name = pod["metadata"]["name"]
            assert name.startswith(APP_NAME), (
                f"Неожиданное имя пода: {name}"
            )

    def test_pods_have_correct_labels(self):
        data = kubectl_json("get", "pods", "-l", f"app={APP_NAME}")
        for pod in data["items"]:
            labels = pod["metadata"].get("labels", {})
            assert labels.get("app") == APP_NAME, (
                f"Pod {pod['metadata']['name']} не имеет метки app={APP_NAME}"
            )

    def test_pods_have_resource_limits(self):
        data = kubectl_json("get", "pods", "-l", f"app={APP_NAME}")
        for pod in data["items"]:
            for c in pod["spec"]["containers"]:
                assert "resources" in c, (
                    f"Контейнер {c['name']} не имеет секции resources"
                )
                assert c["resources"].get("limits"), (
                    f"Контейнер {c['name']} не имеет limits"
                )
                assert c["resources"].get("requests"), (
                    f"Контейнер {c['name']} не имеет requests"
                )

    def test_pod_count_within_hpa_bounds(self):
        """Количество подов находится в пределах minReplicas..maxReplicas."""
        pod_count = len(kubectl_json("get", "pods", "-l", f"app={APP_NAME}")["items"])
        hpa_data  = kubectl_json("get", "hpa", "insuretech-app-hpa")
        min_r = hpa_data["spec"]["minReplicas"]
        max_r = hpa_data["spec"]["maxReplicas"]
        assert min_r <= pod_count <= max_r, (
            f"pod count={pod_count} вне диапазона [{min_r}, {max_r}]"
        )

    def test_pod_status_snapshot(self, capsys):
        """
        Делает 3 снимка состояния подов с интервалом 5 сек
        (имитация --watch для скриншота).
        """
        for i in range(3):
            result = kubectl("get", "pods", "-l", f"app={APP_NAME}")
            print(f"\n--- Снимок {i+1} ---\n{result.stdout}")
            if i < 2:
                time.sleep(5)

        captured = capsys.readouterr()
        assert "Running" in captured.out

    def test_hpa_status_snapshot(self, capsys):
        """
        Делает 3 снимка состояния HPA с интервалом 5 сек
        (имитация kubectl get hpa --watch).
        """
        for i in range(3):
            result = kubectl("get", "hpa", "insuretech-app-hpa")
            print(f"\n--- HPA снимок {i+1} ---\n{result.stdout}")
            if i < 2:
                time.sleep(5)

        captured = capsys.readouterr()
        assert "insuretech-app-hpa" in captured.out
