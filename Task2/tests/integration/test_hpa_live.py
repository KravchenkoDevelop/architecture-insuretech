"""
Integration tests — шаг 6 README:
  kubectl get hpa insuretech-app-hpa --watch

Проверяем состояние HPA в кластере: наличие, конфигурацию,
текущие метрики и (при нагрузке) факт масштабирования.
"""
import time
import pytest
from .conftest import kubectl, kubectl_json, wait_for_condition

HPA_NAME  = "insuretech-app-hpa"
APP_NAME  = "insuretech-app"
NAMESPACE = "default"


class TestHPALive:
    """HPA существует и корректно сконфигурирован в кластере."""

    def test_hpa_exists(self):
        result = kubectl("get", "hpa", HPA_NAME, check=False)
        assert result.returncode == 0, (
            f"HPA '{HPA_NAME}' не найден. Запустите: kubectl apply -f hpa.yaml"
        )

    def test_hpa_targets_correct_deployment(self):
        data = kubectl_json("get", "hpa", HPA_NAME)
        ref = data["spec"]["scaleTargetRef"]
        assert ref["name"] == APP_NAME, (
            f"HPA таргетирует '{ref['name']}', ожидается '{APP_NAME}'"
        )
        assert ref["kind"] == "Deployment", (
            f"HPA таргетирует {ref['kind']}, ожидается Deployment"
        )

    def test_hpa_min_replicas(self):
        data = kubectl_json("get", "hpa", HPA_NAME)
        assert data["spec"]["minReplicas"] == 1, "minReplicas должен быть 1"

    def test_hpa_max_replicas(self):
        data = kubectl_json("get", "hpa", HPA_NAME)
        assert data["spec"]["maxReplicas"] == 10, "maxReplicas должен быть 10"

    def test_hpa_current_replicas_at_least_min(self):
        data = kubectl_json("get", "hpa", HPA_NAME)
        current = data["status"].get("currentReplicas", 0)
        min_r   = data["spec"]["minReplicas"]
        assert current >= min_r, (
            f"currentReplicas={current} < minReplicas={min_r}"
        )

    def test_hpa_has_memory_metric(self):
        data = kubectl_json("get", "hpa", HPA_NAME)
        metrics = data["spec"]["metrics"]
        mem = [m for m in metrics if m.get("resource", {}).get("name") == "memory"]
        assert mem, "HPA не имеет метрики memory"
        util = mem[0]["resource"]["target"]["averageUtilization"]
        assert util == 80, f"averageUtilization={util}, ожидается 80"

    def test_hpa_conditions_not_false(self):
        """
        Проверяем что HPA не застрял в ошибочных условиях
        (например, 'Unable to fetch metrics').
        """
        data = kubectl_json("get", "hpa", HPA_NAME)
        for cond in data["status"].get("conditions", []):
            if cond["status"] == "False" and cond["type"] in ("AbleToScale", "ScalingActive"):
                pytest.fail(
                    f"HPA condition '{cond['type']}' = False: {cond.get('message', '')}"
                )

    def test_hpa_metrics_server_provides_data(self):
        """
        Если metrics-server работает, HPA должен показывать currentMetrics.
        Ждём до 90 секунд пока метрики появятся.
        """
        def has_current_metrics():
            data = kubectl_json("get", "hpa", HPA_NAME)
            return bool(data["status"].get("currentMetrics"))

        wait_for_condition(
            has_current_metrics,
            timeout=90,
            interval=10,
            label="HPA currentMetrics populated",
        )

    def test_hpa_current_memory_utilization_reported(self):
        """currentMetrics содержит значение memory utilization."""
        data = kubectl_json("get", "hpa", HPA_NAME)
        current_metrics = data["status"].get("currentMetrics", [])
        mem = [m for m in current_metrics if m.get("resource", {}).get("name") == "memory"]
        assert mem, "HPA не сообщает currentMetrics для memory"
        util = (
            mem[0]["resource"]["current"].get("averageUtilization")
            or mem[0]["resource"]["current"].get("averageValue")
        )
        assert util is not None, "Значение memory utilization не определено"


class TestHPAWatch:
    """
    Симуляция 'kubectl get hpa --watch':
    наблюдаем за изменением replicaCount без нагрузки (базовое состояние).
    """

    def test_hpa_stable_at_min_replicas_without_load(self):
        """Без нагрузки HPA должен удерживать 1 реплику (minReplicas)."""
        # Снимаем 3 показания с интервалом 5 сек
        replica_counts = []
        for _ in range(3):
            data = kubectl_json("get", "hpa", HPA_NAME)
            replica_counts.append(data["status"].get("currentReplicas", 1))
            time.sleep(5)

        for count in replica_counts:
            assert count == 1, (
                f"Без нагрузки HPA изменил replicas до {count}, ожидается 1"
            )

    def test_kubectl_get_hpa_output_parseable(self):
        """'kubectl get hpa' возвращает читаемый вывод без ошибок."""
        result = kubectl("get", "hpa", HPA_NAME)
        assert result.returncode == 0
        assert HPA_NAME in result.stdout
        # Заголовки стандартного вывода HPA
        assert "MINPODS" in result.stdout or "MIN" in result.stdout
        assert "MAXPODS" in result.stdout or "MAX" in result.stdout

    def test_kubectl_get_pods_output_parseable(self):
        """'kubectl get pods' возвращает работающие поды приложения."""
        result = kubectl("get", "pods", "-l", f"app={APP_NAME}")
        assert result.returncode == 0
        assert "Running" in result.stdout, (
            f"Нет Running подов:\n{result.stdout}"
        )
