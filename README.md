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
