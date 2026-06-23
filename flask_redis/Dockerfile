# syntax=docker/dockerfile:1
# Берём лёгкий образ Linux с Python, чтобы контейнер был меньше.
FROM python:3.10-alpine

# Ставим внутри контейнера рабочую директорию /code.
WORKDIR /code

# Flask смотрит на эту переменную и понимает, какой файл запускать.
ENV FLASK_APP=app.py

# 0.0.0.0 значит слушать все сетевые интерфейсы контейнера, иначе снаружи не достучаться.
ENV FLASK_RUN_HOST=0.0.0.0

# Эти пакеты нужны, чтобы Python-зависимости могли собраться внутри Alpine.
RUN apk add --no-cache gcc musl-dev linux-headers

# Сначала копировать requirements отдельно, чтобы Docker мог кешировать установку зависимостей.
COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Копируем само приложение уже после установки зависимостей.
COPY app.py .

# Внутри контейнера приложение слушает порт 5000. EXPOSE только документирует это.
EXPOSE 5000

# Команда, которая стартует dev-сервер Flask в контейнере.
CMD ["flask", "run", "--debug"]
