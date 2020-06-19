from flask import Flask, g, request, render_template
import logging
import db
import ldap
from conf import Conf

# Log for web actions
webLogger = logging.getLogger('TelegramShoutoutBot.web')
webLogger.setLevel(logging.INFO)
web_file_handler = logging.FileHandler(Conf.web_log)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
web_file_handler.setFormatter(formatter)
webLogger.addHandler(web_file_handler)

app = Flask(__name__)

my_database = db.MyDatabase(Conf.database_url)
ldap_access = ldap.LdapAccess(Conf.ldap_server, Conf.ldap_user,
                              Conf.ldap_password, Conf.ldap_base_group_filter)


@app.before_request
def before_request():
    g.url_libs = Conf.url_libs
    g.url_path = Conf.url_path


@app.route('/')
def hello_world():
    return 'Hello, World!'


@app.route('/register/<chat_id>')
def register(chat_id):
    token = request.args.get('token')
    return render_template('register_form.html', chat_id=chat_id, token=token)


@app.route('/register/<chat_id>/login', methods=['POST'])
def register_login(chat_id):
    token = request.form['token']
    username = request.form['username']
    password = request.form['password']
    ldap_account = Conf.ldap_username_template.format(username)
    if not ldap_access.check_credentials(ldap_account, password):
        return render_template('register_login_fail.html', reason="ldap", chat_id=chat_id, token=token)
    with db.my_session_scope(my_database) as session:  # type: db.MyDatabaseSession
        user = session.get_user_by_chat_id(chat_id)
        if user is None:
            return render_template('register_login_fail.html', reason="chat_id",
                                   chat_id=chat_id, token=token)
        if user.ldap_register_token != token:
            return render_template('register_login_fail.html', reason="token",
                                   chat_id=chat_id, token=token)
        user.ldap_account = ldap_account
        user.ldap_register_token = None
        session.commit()
        log_message_format = "Registered chat_id {0} with token {1} for LDAP-User {2}"
        webLogger.info(log_message_format.format(chat_id, token, username))
    return render_template('register_login_success.html', chat_id=chat_id, token=token, username=username)
