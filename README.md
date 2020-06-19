# Telegram Shoutout Bot

This python script will enable a telegram bot to handle subscriptions and shoutouts in one or multiple channels.

## Usage

Copy `cp bot/conf.py{.template,}` and adapt the settings.
You need to obtain a `bot_token` by chatting with [BotFather](https://t.me/BotFather).


## Deploying without Docker


### Python

```
pip3 install -r bot/requirements.txt
pip3 install pymysql # if you use a MySQL database
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
The easiest way to deploy the container is to use docker-compose. Copy `cp docker-compose.yml{.template,}` the example configuration file.
You need to adapt the paths (```/path/to/*```) in the volume section:
With the first line you can choose a directory to store the log files, with the second file you specify a configuration
file to use (which is read in entrypoint script when starting the container). The configuration file can be mounted
readonly.

### Database usage
The docker image contains the pymysql package for Python so that connections to mysql databases are possible.
You need to use an url starting with ```mysql+pymysql://``` to use this connector.
