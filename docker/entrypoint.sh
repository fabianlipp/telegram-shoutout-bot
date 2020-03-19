#!/bin/sh

cp /config/telegram_shoutout_bot_conf.py /app/

/usr/bin/supervisord -c /etc/supervisord.conf
