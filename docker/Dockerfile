FROM python:alpine3.7
COPY bot/requirements.txt /
RUN apk add --no-cache --virtual .build-deps gcc musl-dev libffi-dev openssl-dev \
 && pip install -r /requirements.txt \
 && pip install pymysql \
 && pip install gunicorn \
 && apk del .build-deps \
 && apk add --no-cache supervisor
COPY bot /app
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
COPY docker/supervisord.conf /etc/supervisor.d/telegram-shoutout-bot.ini
WORKDIR /app
EXPOSE 8000
#VOLUME /log /database /config/conf.py
ENTRYPOINT /entrypoint.sh
