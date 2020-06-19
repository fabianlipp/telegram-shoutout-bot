#!/bin/sh

cp /config/conf.py /app/

/usr/bin/supervisord -c /etc/supervisord.conf
