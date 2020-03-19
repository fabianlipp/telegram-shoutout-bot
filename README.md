# Telegram Shoutout Bot

This python script will enable a telegram bot to handle subscriptions and shoutouts in one or multiple channels.

## Usage

Copy `telegram_shoutout_bot_conf.py.template` to `telegram_shoutout_bot_conf.py` and adapt the settings.
You need to obtain a `bot_token` by chatting with [BotFather](https://t.me/BotFather).


## Needed dependencies


### Python

```
pip3 install ldap3 python-telegram-bot sqlalchemy
```

(virtual environment can be used to prevent conflicts)

A webserver with support for wsgi is needed.


### Sample configuration for webserver with wsgi (Linux + Apache2)

```
apt install python3-pip apache2 libapache2-mod-wsgi-py3
a2enmod wsgi
```

Presumed your URL is https://example.com/telegram/ the apache configuration needs the following lines in the vhost part:

```
<VirtualHost *:443>
  ServerName example.com
  …

  WSGIDaemonProcess telegram user=www-data group=www-data threads=1 python-path=/…/telegram-shoutout-bot/webinterface:/…/telegram-shoutout-bot
  WSGIScriptAlias /telegram /…/telegram-shoutout-bot/webinterface/telegram.wsgi
  <Directory /…/telegram-shoutout-bot/webinterface>
    WSGIProcessGroup telegram
    WSGIApplicationGroup %{GLOBAL}
  </Directory>
</VirtualHost>
```

## Deploying using Docker

### Building image
Run the following command in the root directory:
```shell script
docker build --tag telegram-shoutout-bot -f docker/Dockerfile .
```

### Deploying image
The easiest way to deploy the container is to use docker-compose.
In the following, we present an example configuration file.
You need to adapt the paths (```/path/to/*```) in the volume section:
With the first line you can choose a directory to store the log files, with the second file you specify a configuration
file to use (which is read in entrypoint script when starting the container).
```yaml
version: '3.5'

services:
  ptb-test:
    image: telegram-shoutout-bot
    container_name: tsb
    networks:
      - telegram-network
    ports:
      - 127.0.0.1:10050:8000
    volumes:
      - /path/to/log:/log
      - /path/to/telegram_shoutout_bot_conf.py:/config/telegram_shoutout_bot_conf.py
    restart: unless-stopped

networks:
  telegram-network:
    driver: bridge
    driver_opts:
      com.docker.network.bridge.name: "telegram-net"
    ipam:
      driver: default
      config:
        - subnet: 172.18.1.0/24
    name: telegram-network
```

### Database usage
The docker image contains the pymysql package for Python so that connections to mysql databases are possible.
You need to use an url starting with ```mysql+pymysql://``` to use this connector.
