# Telegram Shoutout Bot

This python script will enable a telegram bot to handle subscriptions and shoutouts in one or multiple channels.

You need to obtain a `bot_token` by chatting with [BotFather](https://t.me/BotFather) that is entered in your `conf.py`.


## Deploying without Docker

### Python

```
pip3 install -r bot/requirements.txt
pip3 install pymysql # if you use a MySQL database
cp instances/sample/conf.py bot/
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
The easiest way to deploy the container is to copy the example configuration directory, adapt the configuration and start the container:
```shell script
cp -r instances/{sample,botty}
cd instaces/botty
editor conf.py
docker-compose up -d --build
```

### Database usage
The docker image contains the pymysql package for Python so that connections to mysql databases are possible.
You need to use an url starting with ```mysql+pymysql://``` to use this connector.
