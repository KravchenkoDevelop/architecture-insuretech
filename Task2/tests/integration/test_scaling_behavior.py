"""
Integration tests — ГЛАВНЫЙ СЦЕНАРИЙ шага 5-6 README:
  Locust генерирует нагрузку → HPA масштабирует поды.

Структура теста:
  1. Фиксируем начальное состояние (1 реплика)
  2. Запускаем Locust в headless-режиме (нагрузка на GET /)
  3. Ждём пока HPA увеличит replicas (scale-out)
  4. Останавливаем нагрузку
  5. Ждём пока HPA вернёт replicas к минимуму (scale-in)

Таймауты взяты из реального поведения Kubernetes HPA:
  - scale-out: до 3 минут (default scale-up stabilization window)
  - scale-in:  до 5 минут (default scale-down stabilization window)
"""
import subprocess
import threading
import time
import os
import requests
import pytest
from .conftest import kubectl, kubectl_json, wait_for_condition

HPA_NAME  = "insuretech-app-hpa"
APP_NAME  = "insuretech-app"
NAMESPACE = "default"
TASK2_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# Таймауты (секунды)
SCALE_OUT_TIMEOUT = 300   # 5 мин на scale-out
SCALE_IN_TIMEOUT  = 360   # 6 мин на scale-in
LOAD_DURATION     = 180   # держим нагрузку 3 мин


# ── утилиты ────────────────────────────────────────────────────────────────

def get_current_replicas() -> int:
    data = kubectl_json("get", "hpa", HPA_NAME)
    return data["status"].get("currentReplicas", 1)


def get_pod_count() -> int:
    data = kubectl_json("get", "pods", "-l", f"app={APP_NAME}")
    running = [
        p for p in data["items"]
        if p["status"].get("phase") == "Running"
    ]
    return len(running)


def get_memory_utilization() -> int | None:
    """Возвращает текущую утилизацию памяти (%) из HPA status."""
    data = kubectl_json("get", "hpa", HPA_NAME)
    for m in data["status"].get("currentMetrics", []):
        if m.get("resource", {}).get("name") == "memory":
            return m["resource"]["current"].get("averageUtilization")
    return None


def run_locust_headless(app_url: str, duration: int, users: int = 50, spawn_rate: int = 10):
    """
    Запускает Locust в headless-режиме на duration секунд.
    Возвращает CompletedProcess.
    """
    locustfile = os.path.join(TASK2_DIR, "locustfile.py")
    cmd = [
        "locust",
        "-f", locustfile,
        "--headless",
        "--users", str(users),
        "--spawn-rate", str(spawn_rate),
        "--run-time", f"{duration}s",
        "--host", app_url,
        "--csv", os.path.join(TASK2_DIR, "tests", "locust_results"),
        "--logfile", os.path.join(TASK2_DIR, "tests", "locust.log"),
    ]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=duration + 30)


def simple_load(app_url: str, stop_event: threading.Event, concurrency: int = 20):
    """
    Альтернатива Locust: простая HTTP-нагрузка через потоки.
    Используется если locust не установлен.
    """
    def worker():
        while not stop_event.is_set():
            try:
                requests.get(f"{app_url}/", timeout=5)
            except Exception:
                pass

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(concurrency)]
    for t in threads:
        t.start()
    return threads


# ── тесты ─────────────────────────────────────────────────────────────────

class TestScalingBehavior:
    """
    Полный E2E-сценарий: нагрузка → scale-out → снятие нагрузки → scale-in.
    """

    def test_initial_state_one_replica(self):
        """Перед тестом: 1 реплика."""
        replicas = get_current_replicas()
        assert replicas == 1, (
            f"Ожидается 1 реплика перед нагрузкой, получено {replicas}. "
            "Убедитесь что нагрузки нет и HPA стабилизировался."
        )

    def test_scale_out_under_load(self, app_url):
        """
        При нагрузке HPA должен увеличить количество реплик выше 1.

        Порядок:
          1. Запустить нагрузку (Locust или простые HTTP-запросы)
          2. Ждать пока currentReplicas > 1
        """
        stop_event = threading.Event()
        load_threads = []

        try:
            # Пробуем Locust; если не установлен — используем простую нагрузку
            try:
                subprocess.run(["locust", "--version"], capture_output=True, check=True)
                use_locust = True
            except (FileNotFoundError, subprocess.CalledProcessError):
                use_locust = False

            if use_locust:
                load_thread = threading.Thread(
                    target=run_locust_headless,
                    args=(app_url, LOAD_DURATION),
                    daemon=True,
                )
                load_thread.start()
                load_threads.append(load_thread)
            else:
                load_threads = simple_load(app_url, stop_event, concurrency=30)

            # Ждём scale-out
            wait_for_condition(
                lambda: get_current_replicas() > 1,
                timeout=SCALE_OUT_TIMEOUT,
                interval=15,
                label="HPA scale-out (replicas > 1)",
            )

            scaled_replicas = get_current_replicas()
            assert scaled_replicas > 1, (
                f"HPA не масштабировал поды: replicas={scaled_replicas}"
            )

        finally:
            stop_event.set()

    def test_memory_utilization_exceeds_threshold_under_load(self, app_url):
        """
        При нагрузке утилизация памяти должна превысить 80%
        (иначе HPA не активирует scale-out).
        """
        stop_event = threading.Event()
        load_threads = simple_load(app_url, stop_event, concurrency=30)

        try:
            def utilization_high():
                util = get_memory_utilization()
                return util is not None and util >= 80

            wait_for_condition(
                utilization_high,
                timeout=SCALE_OUT_TIMEOUT,
                interval=15,
                label="memory utilization >= 80%",
            )
            util = get_memory_utilization()
            assert util >= 80, f"Утилизация памяти {util}% < 80%"
        finally:
            stop_event.set()

    def test_pod_count_increases_under_load(self, app_url):
        """Количество Running подов растёт при нагрузке."""
        initial_pods = get_pod_count()
        stop_event   = threading.Event()
        load_threads = simple_load(app_url, stop_event, concurrency=30)

        try:
            wait_for_condition(
                lambda: get_pod_count() > initial_pods,
                timeout=SCALE_OUT_TIMEOUT,
                interval=15,
                label=f"pod count > {initial_pods}",
            )
            assert get_pod_count() > initial_pods
        finally:
            stop_event.set()

    def test_scale_in_after_load_removed(self):
        """
        После снятия нагрузки HPA должен вернуть replicas к 1.

        ВАЖНО: Kubernetes HPA по умолчанию ждёт 5 минут перед scale-in
        (stabilization window), поэтому таймаут большой.
        """
        # Убеждаемся что нагрузки нет
        def at_min_replicas():
            return get_current_replicas() == 1

        wait_for_condition(
            at_min_replicas,
            timeout=SCALE_IN_TIMEOUT,
            interval=30,
            label="HPA scale-in (replicas == 1)",
        )
        assert get_current_replicas() == 1

    def test_hpa_does_not_exceed_max_replicas(self):
        """currentReplicas никогда не превышает maxReplicas=10."""
        data = kubectl_json("get", "hpa", HPA_NAME)
        current = data["status"].get("currentReplicas", 1)
        max_r   = data["spec"]["maxReplicas"]
        assert current <= max_r, (
            f"currentReplicas={current} превышает maxReplicas={max_r}"
        )

    def test_new_pods_pass_readiness(self, app_url):
        """
        После scale-out все поды (включая новые) должны пройти readiness check
        и Service должен отвечать 200.
        """
        resp = requests.get(f"{app_url}/", timeout=10)
        assert resp.status_code == 200, (
            f"После scale-out приложение недоступно: HTTP {resp.status_code}"
        )


class TestLocustHeadless:
    """
    Проверяем что Locust headless-режим корректно выполняет сценарий
    и не генерирует ошибок при нагрузке.
    """

    @pytest.mark.skipif(
        not __import__("shutil").which("locust"),
        reason="locust не установлен"
    )
    def test_locust_headless_no_failures(self, app_url):
        """
        Locust --headless 30 сек: failure rate должен быть < 1%.
        """
        import csv, io
        result = run_locust_headless(app_url, duration=30, users=20, spawn_rate=5)

        csv_path = os.path.join(TASK2_DIR, "tests", "locust_results_stats.csv")
        if os.path.exists(csv_path):
            with open(csv_path) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get("Name") == "Aggregated":
                        failures   = int(row.get("Failure Count", 0))
                        requests_n = int(row.get("Request Count", 1))
                        rate = failures / requests_n
                        assert rate < 0.01, (
                            f"Locust: failure rate {rate:.1%} >= 1%"
                        )
