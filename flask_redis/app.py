import socket
import time

import redis
from flask import Flask, make_response

app = Flask(__name__)

# В Docker Compose и Kubernetes имя redis разрешается через DNS.
# В Kubernetes это будет имя Service.
# Поэтому тут не IP-адрес, а просто имя сервиса redis.
cache = redis.Redis(
    host="redis",
    port=6379,
)


def get_hit_count() -> int:
    """Прочитать счётчик без его увеличения."""

    # Если ключа hits еще нет, Redis вернет None. Тогда считаем, что просмотров 0.
    return int(cache.get("hits") or 0)


def incr_hit_count() -> int:
    """Увеличить счётчик, повторяя подключение при временной ошибке."""

    # Redis может стартовать чуть дольше Flask, поэтому даю приложению несколько попыток.
    retries = 5

    while True:
        try:
            # incr сам увеличивает число в Redis и сразу возвращает новое значение.
            return cache.incr("hits")

        except redis.exceptions.ConnectionError as exc:
            if retries == 0:
                raise exc

            retries -= 1
            # Маленькая пауза, чтобы не долбить Redis бесконечно быстро.
            time.sleep(0.5)


@app.route("/metrics")
def metrics():
    # Prometheus читает этот endpoint регулярно, поэтому тут только get_hit_count().
    # Если вызвать incr_hit_count(), мониторинг сам накручивал бы счетчик посещений.
    metrics_text = f"""# HELP view_count Flask-Redis-App visit counter
# TYPE view_count counter
view_count{{service="Flask-Redis-App"}} {get_hit_count()}
"""

    response = make_response(metrics_text, 200)
    # Prometheus ожидает обычный текстовый формат метрик.
    response.mimetype = "text/plain"
    return response


@app.route("/")
def index():
    # Главная страница считается настоящим посещением, поэтому увеличиваем hits.
    count = incr_hit_count()
    # В Kubernetes hostname обычно равен имени Pod, так видно балансировку между репликами.
    pod_name = socket.gethostname()

    response_text = (
        "Hello from Kubernetes!\n"
        f"Pod: {pod_name}\n"
        f"Visits: {count}\n"
        "This is a version 2 of APP. Updated by rolling update"
    )

    response = make_response(response_text, 200)
    # Возвращаю plain text, чтобы curl показывал ответ без HTML.
    response.mimetype = "text/plain"
    return response
