from flask import Flask, request, render_template
import db
import bot_ldap
from telegram_shoutout_bot_conf import BotConf

app = Flask(__name__)

my_database = db.MyDatabase(BotConf.database_file)
ldap_access = bot_ldap.LdapAccess(BotConf.ldap_server, BotConf.ldap_user,
                                  BotConf.ldap_password, BotConf.ldap_base_group_filter)


@app.route('/')
def hello_world():
    return 'Hello, World!'


@app.route('/register/<chat_id>')
def register(chat_id):
    token = request.args.get('token')
    return render_template('register_form.html', url_path=BotConf.url_path, chat_id=chat_id, token=token)


@app.route('/register/<chat_id>/login', methods=['POST'])
def register_login(chat_id):
    token = request.form['token']
    username = request.form['username']
    password = request.form['password']
    ldap_account = BotConf.ldap_username_template.format(username)
    if not ldap_access.check_credentials(ldap_account, password):
        return render_template('register_login_fail.html', reason="ldap", url_path=BotConf.url_path,
                               chat_id=chat_id, token=token)
    with db.my_session_scope(my_database) as session:  # type: db.MyDatabaseSession
        user = session.get_user_by_chat_id(chat_id)
        if user is None:
            return render_template('register_login_fail.html', reason="chat_id", url_path=BotConf.url_path,
                                   chat_id=chat_id, token=token)
        if user.ldap_register_token != token:
            return render_template('register_login_fail.html', reason="token", url_path=BotConf.url_path,
                                   chat_id=chat_id, token=token)
        user.ldap_account = ldap_account
        user.ldap_register_token = None
        session.commit()
    return render_template('register_login_success.html', chat_id=chat_id, token=token, username=username,
                           password=password)
