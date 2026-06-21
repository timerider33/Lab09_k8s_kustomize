# k8s-basics

Запуск простого Flask-приложения с Redis сначала через Docker Compose, а потом через Kubernetes. Дополнительно рядом лежит стек мониторинга: Prometheus, Grafana и Blackbox Exporter.

Манифесты K8s лежат в папке flask_redis_k8s

Главная идея:

- Flask считает посещения главной страницы.
- Redis хранит счетчик `hits`.
- Endpoint `/metrics` отдает значение счетчика в формате Prometheus.
- Prometheus забирает метрики приложения и проверки Blackbox.
- Grafana подключается к Prometheus и показывает графики.

## Структура проекта

```text
k8s-basics/
├── flask_redis/
│   ├── app.py
│   ├── compose.yml
│   ├── dockerfile
│   └── requirements.txt
├── flask_redis_k8s/
│   ├── flask.yml
│   ├── flask-service.yml
│   ├── redis.yml
│   └── redis-service.yml
├── monitoring/
│   ├── compose.yml
│   ├── blackbox/
│   │   └── blackbox.yml
│   ├── grafana/
│   │   └── datasource.yml
│   └── prometheus/
│       └── prometheus.yml
└── README.md
```

## Flask + Redis

Папка: `flask_redis`.

Сервисы Docker Compose:

- `web` - Flask-приложение, собирается из локального `dockerfile`.
- `redis` - Redis из образа `redis:alpine`.

Приложение доступно на хосте:

```text
http://localhost:8000
```

Внутри контейнера Flask слушает порт `5000`, а наружу проброшен порт `8000`:

```yaml
ports:
  - "8000:5000"
```

Flask подключается к Redis по имени сервиса:

```python
redis.Redis(host="redis", port=6379)
```

В Docker Compose и Kubernetes имя `redis` разрешается через внутренний DNS, поэтому приложению не нужен IP-адрес контейнера или Pod.

## Endpoint приложения

Главная страница:

```text
GET /
```

Увеличивает счетчик `hits` в Redis и возвращает текст с именем Pod/контейнера:

```text
Hello from Kubernetes!
Pod: <hostname>
Visits: N
This is a version 2 of APP. Updated by rolling update
```

Метрики:

```text
GET /metrics
```

Возвращает метрику Prometheus:

```text
# HELP view_count Flask-Redis-App visit counter
# TYPE view_count counter
view_count{service="Flask-Redis-App"} N
```

`/metrics` только читает счетчик и не увеличивает его. Иначе Prometheus сам накручивал бы просмотры при каждом опросе.

## Запуск через Docker Compose

```bash
cd /home/ops/projects/k8s-basics/flask_redis
docker compose up -d --build
```

`--build` нужен, если менялись `app.py`, `requirements.txt` или `dockerfile`.

Проверка:

```bash
curl http://127.0.0.1:8000/
curl http://127.0.0.1:8000/metrics
```

Остановка (чтоб запустить через K8s):

```bash
docker compose down
```

## Запуск через Kubernetes

Папка: `flask_redis_k8s`.

Манифесты:

- `redis.yml` - Deployment с одним Pod Redis.
- `redis-service.yml` - ClusterIP Service с именем `redis`.
- `flask.yml` - Deployment Flask-приложения на 5 реплик.
- `flask-service.yml` - Service для доступа к Flask снаружи кластера.

Перед применением манифестов нужен локальный Docker-образ:

```bash
cd /home/ops/projects/k8s-basics/flask_redis
docker build -t flask:v1 -f dockerfile .
```

Применить Kubernetes-манифесты:

```bash
cd /home/ops/projects/k8s-basics/flask_redis_k8s
kubectl apply -f redis.yml
kubectl apply -f redis-service.yml
kubectl apply -f flask.yml
kubectl apply -f flask-service.yml
```

Проверить ресурсы:

```bash
kubectl get pods
kubectl get deployments
kubectl get services
```

В `flask-service.yml` указан Service `service-devops` с портом `8000`, который перенаправляет запросы в контейнер Flask на порт `5000`.

Если кластер не поддерживает `LoadBalancer`, для лабораторной проверки можно использовать port-forward:

```bash
kubectl port-forward service/service-devops 8000:8000
```

После этого проверка такая же:

```bash
curl http://127.0.0.1:8000/
curl http://127.0.0.1:8000/metrics
```

Удаление ресурсов:

```bash
kubectl delete -f flask-service.yml
kubectl delete -f flask.yml
kubectl delete -f redis-service.yml
kubectl delete -f redis.yml
```

## Rolling update

В `app.py` сейчас в ответе есть строка:

```text
This is a version 2 of APP. Updated by rolling update
```

Это состояние уже после update через kubectl set image deployment/flask-app flask=flask:v2
В манифесте все еще старая версия приложения flask:v1

По ответам разных Pod видно, какая версия приложения сейчас обслуживает запросы.

Типовой сценарий:

```bash
cd /home/ops/projects/k8s-basics/flask_redis
docker build -t flask:v1 -f dockerfile .

kubectl rollout restart deployment/flask-app
kubectl rollout status deployment/flask-app
```

Если используется новый тег образа, его надо указать в `flask_redis_k8s/flask.yml` в поле `image`.

## Monitoring

Папка: `monitoring`.

Сервисы:

- `prometheus` - собирает и хранит метрики.
- `grafana` - показывает dashboards и графики.
- `blackbox` - проверяет доступность HTTP/HTTPS-сервисов.

Доступные URL:

```text
Prometheus:        http://localhost:9090
Grafana:           http://localhost:3000
Blackbox Exporter: http://localhost:9115
```

Логин Grafana по умолчанию:

```text
admin / grafana
```

Запуск:

```bash
cd /home/ops/projects/k8s-basics/monitoring
docker compose up -d
```

Остановка:

```bash
docker compose down
```

## Prometheus

Конфиг: `monitoring/prometheus/prometheus.yml`.

Prometheus собирает:

- собственные метрики Prometheus с `localhost:9090/metrics`;
- метрику Flask `view_count` с `host.docker.internal:8000/metrics`;
- HTTP-проверки через Blackbox Exporter.

`host.docker.internal` используется, чтобы контейнер Prometheus мог обращаться к сервису, опубликованному на хосте на порту `8000`.

Для скорости посещений в Grafana можно использовать PromQL:

```promql
rate(view_count{job="view_total"}[30s])
```

Для общего значения счетчика:

```promql
view_count{job="view_total"}
```

## Blackbox Exporter

Конфиг Blackbox: `monitoring/blackbox/blackbox.yml`.

В нем настроены два модуля:

- `http_2xx` - обычная HTTP/HTTPS-проверка с проверкой TLS-сертификата.
- `http_2xx_insecure` - учебная проверка HTTPS без строгой проверки TLS-сертификата.

Обычные цели проверяются job `blackbox-http`:

```text
http://host.docker.internal:8000/
https://etis.psu.ru/
https://ya.ru/
https://www.amazon.com/
```

Цель с проблемной TLS-цепочкой вынесена в отдельный job `blackbox-http-insecure`:

```text
https://student.psu.ru
```

Для доступности сайта в Grafana нужно смотреть:

```promql
probe_success
```

`up` для blackbox показывает, что Prometheus смог опросить сам Blackbox Exporter. Реальный результат HTTP-проверки сайта показывает именно `probe_success`.

## DNS Blackbox

В `monitoring/compose.yml` для `blackbox` явно задан DNS:

```yaml
dns:
  - 192.168.1.57
```

Это сделано из-за долгого DNS lookup при проверках внешних сайтов. Вероятно, это локальная особенность Docker DNS в лабораторном окружении.

## Grafana

Конфиг datasource: `monitoring/grafana/datasource.yml`.

Grafana автоматически подключает Prometheus:

```text
http://prometheus:9090
```

Это внутренний адрес Docker Compose. Контейнер Grafana обращается к контейнеру Prometheus по имени сервиса `prometheus`.

## Памятка по изменениям

Если изменился `flask_redis/app.py`, `requirements.txt` или `dockerfile`:

```bash
cd /home/ops/projects/k8s-basics/flask_redis
docker compose up -d --build
```

Если изменились Kubernetes-манифесты:

```bash
cd /home/ops/projects/k8s-basics/flask_redis_k8s
kubectl apply -f .
```

Если изменился `monitoring/prometheus/prometheus.yml`:

```bash
cd /home/ops/projects/k8s-basics/monitoring
docker compose restart prometheus
```

Если изменился `monitoring/blackbox/blackbox.yml`:

```bash
cd /home/ops/projects/k8s-basics/monitoring
docker compose restart blackbox
```

Если изменился `monitoring/compose.yml`:

```bash
cd /home/ops/projects/k8s-basics/monitoring
docker compose up -d
```

`docker compose up -d` читает compose-файл и создает или пересоздает контейнеры, если изменилась их конфигурация.

`docker compose restart <service>` просто перезапускает уже созданный контейнер, не меняя его конфигурацию.

## Volumes

В `monitoring/compose.yml` используются named volumes:

- `prom_data` - данные Prometheus: временные ряды, WAL, служебное состояние.
- `grafana_data` - данные Grafana: настройки, dashboards, плагины, локальная база.

Обычный `docker compose down` не удаляет эти volumes.

Команда ниже удалит контейнеры вместе с данными:

```bash
docker compose down -v
```

Это удалит историю Prometheus и локальные данные Grafana.
