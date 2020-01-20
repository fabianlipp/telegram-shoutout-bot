from ldap3 import Server, Connection, RESTARTABLE, SYNC


class LdapAccess:
    base_group_filter = None

    def __init__(self, server_url, user, password, base_group_filter):
        self.base_group_filter = base_group_filter
        self.server = Server(server_url)
        conn = Connection(self.server,
                          user=user,
                          password=password,
                          client_strategy=RESTARTABLE)
        conn.bind()
        self.conn = conn

    def check_usergroup(self, username) -> bool:
        return self.check_filter(username, self.base_group_filter)

    def check_filter(self, username, ldap_filter) -> bool:
        if ldap_filter is None:
            return False
        # Use the username as base to decide whether it belongs to group
        self.conn.search(username, ldap_filter)
        return len(self.conn.response) == 1

    def check_credentials(self, username, password) -> bool:
        credential_conn = Connection(self.server,
                                     user=username,
                                     password=password,
                                     client_strategy=SYNC)
        ret = credential_conn.bind()
        credential_conn.unbind()
        return ret
