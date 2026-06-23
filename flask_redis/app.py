import socket
import time
import os
import redis
from flask import Flask, make_response

app = Flask(__name__)


# Ранее host зашит как redis, надо заменить на переменную окружения
DB_HOST = os.getenv("REDIS_HOST", "redis")
# Дополнительно вводим значение текущего окружения
MY_ENV = os.getenv("ENV", "unknown")

cache = redis.Redis(host=DB_HOST, port=6379)


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
def hello():
    count = incr_hit_count()
    return "Hello World! I have been seen {} times. My name is: {} My env: {}\n".format(
        count,
        socket.gethostname(),
        MY_ENV,
    )
