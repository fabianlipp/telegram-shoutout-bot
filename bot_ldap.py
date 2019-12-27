from ldap3 import Server, Connection, RESTARTABLE


class LdapAccess:
    base_group_filter = None

    def __init__(self, server_url, user, password, base_group_filter):
        self.base_group_filter = base_group_filter
        server = Server(server_url)
        conn = Connection(server,
                          user=user,
                          password=password,
                          client_strategy=RESTARTABLE)
        conn.bind()
        self.conn = conn

    def check_usergroup(self, username) -> bool:
        # Use the username as base to decide whether it belongs to group
        self.conn.search(username, self.base_group_filter)
        return len(self.conn.response) == 1
