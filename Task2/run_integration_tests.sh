#!/usr/bin/env bash
# Запуск ИНТЕГРАЦИОННЫХ тестов против живого Minikube-кластера.
#
# Предварительные требования:
#   minikube start
#   minikube addons enable metrics-server
#   kubectl apply -f deployment.yaml -f service.yaml -f hpa.yaml
#
# Использование:
#   cd Task2
#   bash run_integration_tests.sh
#
# Пропустить scaling-тесты (быстрый прогон без нагрузки):
#   bash run_integration_tests.sh --skip-scaling

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG_FILE="tests/integration-run-${TIMESTAMP}.log"
SKIP_SCALING=${1:-""}

echo "=============================================="
echo "  Task2 — Integration Tests (live Minikube)"
echo "  $(date)"
echo "=============================================="

# Проверка Prerequisites
echo ""
echo "[CHECK] minikube status..."
minikube status | grep -E "Running|host|kubelet|apiserver" || {
    echo "[ERROR] Minikube не запущен. Запустите: minikube start"
    exit 1
}

echo "[CHECK] kubectl cluster-info..."
kubectl cluster-info --request-timeout=5s > /dev/null 2>&1 || {
    echo "[ERROR] kubectl не может подключиться к кластеру"
    exit 1
}

echo "[CHECK] Manifests applied..."
kubectl get deployment insuretech-app -n default > /dev/null 2>&1 || {
    echo "[ERROR] Deployment не найден. Запустите:"
    echo "  kubectl apply -f deployment.yaml -f service.yaml -f hpa.yaml"
    exit 1
}

echo ""
echo "[INFO] Все prerequisite-проверки пройдены."
echo ""

# Установка зависимостей
if ! python -c "import pytest" 2>/dev/null && ! python3 -c "import pytest" 2>/dev/null; then
    echo "[INFO] Установка зависимостей..."
    pip install -r requirements-test.txt locust requests 2>&1 | tail -5
fi

# Выбор тестов
if [[ "$SKIP_SCALING" == "--skip-scaling" ]]; then
    TEST_DIRS="tests/integration/test_minikube.py tests/integration/test_deployment_live.py tests/integration/test_hpa_live.py tests/integration/test_pod_watch.py"
    echo "[INFO] Режим: без scaling-тестов (быстрый)"
else
    TEST_DIRS="tests/integration/"
    echo "[INFO] Режим: полный прогон включая scale-out/scale-in"
    echo "[WARN] Тест scale-in может занять до 6 минут (HPA stabilization window)"
fi

echo ""
echo "[INFO] Запуск тестов..."
echo ""

python -m pytest $TEST_DIRS \
    -v \
    --color=yes \
    --tb=short \
    -s \
    --log-cli-level=INFO \
    --log-file="$LOG_FILE" \
    --log-file-level=DEBUG \
    2>&1 | tee "${LOG_FILE%.log}-console.log"

EXIT_CODE=${PIPESTATUS[0]}

echo ""
echo "=============================================="
echo "  Лог выполнения : $LOG_FILE"
echo "  Console log    : ${LOG_FILE%.log}-console.log"
echo "  Exit code      : $EXIT_CODE"
echo "=============================================="

exit $EXIT_CODE
