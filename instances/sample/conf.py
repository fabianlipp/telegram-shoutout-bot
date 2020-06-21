class Conf:
    bot_token = '123456789:shiec2nai3joy3alee7ohduz3eiH5nahb7yu'
    database_url = 'sqlite:////database/testdb.sqlite'
    # Variant for MySQL:
    # database_url = 'mysql+pymysql://user:password@172.18.1.1/database'
    ldap_base_group_filter = "(&(objectclass=person)(memberOf=cn=telegram,ou=group,dc=example,dc=com))"
    ldap_server = 'ldaps://example.com'
    ldap_user = "userid=telegram,ou=user,dc=example,dc=com"
    ldap_password = ""
    ldap_username_template = "cn={0},ou=People,dc=example,dc=com"
    error_log = '/log/error.log'
    admin_log = '/log/admin.log'
    user_log = '/log/user.log'
    web_log = '/log/web.log'
    bot_devs = [123456789]
    url_libs = '/libs/'
    url_host = 'https://example.com'
    url_path = '/telegram/'
    url_impressum = 'https://www.example.com/impressum.html'
