# Flask + Redis: Kustomize и monitoring: Helm stack

Лабораторный проект показывает один и тот же стек в нескольких вариантах:

- Kustomize создаёт отдельные конфигурации `dev` и `prod` для flask и redis
- Prometheus, Grafana и Blackbox Exporter запускаются через Helm.

## Структура

```text
k8s_kustomize/
├── flask_redis/
│   ├── app.py
│   ├── compose.yml
│   ├── Dockerfile
│   └── requirements.txt
├── flask_redis_k8s/
│   ├── base/                 # общие Deployment и Service
│   ├── dev/                  # 1 реплика, dev-префикс, порт 8001
│   └── prod/                 # 3 реплики, prod-префикс, порт 8002
├── monitoring/
│   ├── compose.yml
│   ├── prometheus/
│   ├── grafana/
│   ├── blackbox/
│   └── promgra/              # Helm chart, созданный через Kompose
├── results/                  # результаты проверки развёрнутого стенда
│   ├── helm_status.txt
│   ├── kubectl_get_all.txt
│   ├── kubectl_get_deploy.txt
│   └── kubectl_get_endpoints.txt
└── README.md
```

## Результаты

Папка `results` содержит сохранённый вывод команд проверки развёрнутого стенда:

- `helm_status.txt` — состояние Helm release `promgra`;
- `kubectl_get_all.txt` — Pod, Service, Deployment и ReplicaSet;
- `kubectl_get_deploy.txt` — готовность Deployment окружений `dev` и `prod`;
- `kubectl_get_endpoints.txt` — адреса Pod, выбранных Kubernetes Service.

Файлы подтверждают, что Flask и Redis запущены в обоих окружениях, в `dev`
работает одна реплика Flask, в `prod` — три, а monitoring установлен через Helm.

## Приложение

Flask подключается к Redis по адресу из `REDIS_HOST`. По умолчанию используется
DNS-имя `redis`.

Доступные endpoints:

- `GET /` — увеличивает счётчик `hits` и возвращает имя контейнера/Pod и окружение;
- `GET /metrics` — читает счётчик без увеличения и отдаёт метрику `view_count`.

Пример метрики:

```text
# HELP view_count Flask-Redis-App visit counter
# TYPE view_count counter
view_count{service="Flask-Redis-App"} 5
```

## Kubernetes и Kustomize

Базовые ресурсы находятся в `flask_redis_k8s/base`:

- `flask.yml` — Deployment Flask с образом `flask:v5`;
- `flask-service.yml` — LoadBalancer Service приложения;
- `redis.yml` — Deployment Redis;
- `redis-service.yml` — внутренний ClusterIP Service с DNS-именем `redis`.

Overlays изменяют базовую конфигурацию:

| Окружение | Ресурсы | Реплики Flask | Service port | `REDIS_HOST` |
| --- | --- | ---: | ---: | --- |
| dev | префикс `dev-`, label `env=dev` | 1 | 8001 | `dev-redis` |
| prod | префикс `prod-`, label `env=prod` | 3 | 8002 | `prod-redis` |

### Подготовка образа в Minikube

Тег образа должен совпадать с `image` в
`flask_redis_k8s/base/flask.yml`.

```bash
cd /home/ops/projects/k8s_kustomize/flask_redis
minikube image build -t flask:v5 .
```

### Просмотр итоговых манифестов

```bash
cd /home/ops/projects/k8s_kustomize
kubectl kustomize flask_redis_k8s/dev
kubectl kustomize flask_redis_k8s/prod
```

### Развёртывание

Можно запустить оба окружения одновременно:

```bash
kubectl apply -k flask_redis_k8s/dev
kubectl apply -k flask_redis_k8s/prod
kubectl get deployments,pods,services
```

Для локального кластера LoadBalancer-адреса обычно предоставляет:

```bash
minikube tunnel
```

Если LoadBalancer недоступен, используйте port-forward:

```bash
# команды в разных терминалах.
kubectl port-forward service/dev-service-devops 8001:8001
kubectl port-forward service/prod-service-devops 8002:8002
```

Проверка:

```bash
curl http://127.0.0.1:8001/
curl http://127.0.0.1:8001/metrics
curl http://127.0.0.1:8002/
```

Удаление:

```bash
kubectl delete -k flask_redis_k8s/dev
kubectl delete -k flask_redis_k8s/prod
```

## Обновление приложения

После изменения `app.py` нужно пересобирать образ. При повторном использовании того
же тега перезапустить Deployment:

```bash
cd /home/ops/projects/k8s_kustomize/flask_redis
minikube image build -t flask:v5 .

kubectl rollout restart deployment/dev-flask-app
kubectl rollout restart deployment/prod-flask-app
kubectl rollout status deployment/dev-flask-app
kubectl rollout status deployment/prod-flask-app
```

Для более предсказуемых обновлений лучше создавать новый тег образа и менять
его в base-манифесте.

## Monitoring через Docker Compose

```bash
cd /home/ops/projects/k8s_kustomize/monitoring
docker compose up -d
```

Интерфейсы:

- Prometheus — <http://localhost:9090>;
- Grafana — <http://localhost:3000>, логин `admin`, пароль `grafana`;
- Blackbox Exporter — <http://localhost:9115>.

Prometheus собирает:

- собственные метрики;
- `view_count` с `host.docker.internal:8000/metrics`;
- результаты HTTP-проверок через Blackbox Exporter.

Полезные PromQL-запросы:

```promql
view_count{job="view_total"}
rate(view_count{job="view_total"}[30s])
probe_success
```

Для Blackbox реальную доступность цели показывает `probe_success`. Метрика
`up` сообщает только о том, смог ли Prometheus получить ответ от exporter.

В `monitoring/compose.yml` для Blackbox указан DNS-сервер `192.168.1.57`.
Это настройка конкретной лабораторной сети; при запуске в другой сети её нужно
заменить или удалить.

Остановка:

```bash
docker compose down
```

Named volumes `prom_data` и `grafana_data` сохраняются. Удаление контейнеров
вместе с данными:

```bash
docker compose down -v
```

## Monitoring через Helm

Chart `monitoring/promgra` создан из Compose с помощью Kompose и разворачивает
Prometheus, Grafana и Blackbox Exporter в Kubernetes.

Перед установкой проверить `monitoring/promgra/values.yaml`:

- `EXTERNAL_IP` — адрес для публикации Grafana;
- `EXTERNAL_PORT` — внешний порт Grafana;
- `GF_ADMIN_PASSWORD` — учебный пароль администратора.

Проверка и рендеринг:

```bash
helm lint monitoring/promgra
helm template promgra monitoring/promgra
```

Установка:

```bash
helm upgrade --install promgra monitoring/promgra
kubectl get pods,services,pvc
```

Для Minikube может понадобиться отдельный процесс:

```bash
minikube tunnel
```

Удаление release:

```bash
helm uninstall promgra
```

## Проверка после изменений

```bash
docker compose -f flask_redis/compose.yml config
docker compose -f monitoring/compose.yml config
kubectl kustomize flask_redis_k8s/dev
kubectl kustomize flask_redis_k8s/prod
helm lint monitoring/promgra
```

После изменения конфигов monitoring:

```bash
cd /home/ops/projects/k8s_kustomize/monitoring
docker compose restart prometheus
docker compose restart blackbox
```
