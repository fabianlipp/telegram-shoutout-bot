import time
from contextlib import contextmanager

from sqlalchemy import Table, Column, Integer, String, Boolean, ForeignKey, event, create_engine
import sqlalchemy.engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, selectinload, Session  # , scoped_session
from sqlalchemy.orm.collections import attribute_mapped_collection

from sqlite3 import Connection as SQLite3Connection

Base = declarative_base()

user_channels = Table('user_channels', Base.metadata,
                      Column('chat_id', ForeignKey('users.chat_id', ondelete='CASCADE'), primary_key=True),
                      Column('channel_id', ForeignKey('channels.id', ondelete='CASCADE'), primary_key=True)
                      )


class User(Base):
    __tablename__ = "users"
    chat_id = Column(Integer, primary_key=True)
    username = Column(String)
    first_name = Column(String)
    last_name = Column(String)
    time_start = Column(Integer)
    last_msg = Column(String)
    ldap_account = Column(String)

    channels = relationship('Channel',
                            collection_class=attribute_mapped_collection('name'),
                            secondary=user_channels,
                            back_populates='users',
                            cascade='all, delete')  # type: dict

    def __init__(self, chat_id, username, first_name, last_name, time_start=None):
        self.chat_id = chat_id
        self.username = username
        self.first_name = first_name
        self.last_name = last_name

        if time_start is not None:
            self.time_start = time_start
        else:
            self.time_start = int(time.time())
        self.last_msg = None

    def __repr__(self):
        return "<User(chat_id='%s', username='%s', first_name='%s', last_name='%s')>" \
               % (self.chat_id, self.username, self.first_name, self.last_name)


class Channel(Base):
    __tablename__ = "channels"
    id = Column(Integer, primary_key=True)
    name = Column(String(collation='NOCASE'), unique=True)
    description = Column(String)
    default = Column(Boolean, default=False)
    ldap_filter = Column(String)

    users = relationship('User',
                         secondary=user_channels,
                         back_populates='channels',
                         cascade='all, delete')


class MyDatabaseSession:
    session = None

    def __init__(self, session: Session):
        self.session = session

    def commit(self):
        self.session.commit()

    def close(self):
        self.session.close()

    def rollback(self):
        self.session.rollback()

    def get_user_by_chat_id(self, chat_id) -> User:
        return self.session.query(User).filter(User.chat_id.is_(chat_id)).first()

    def get_users(self):
        return self.session.query(User).all()

    def add_user(self, chat_id, username, first_name, last_name):
        if self.get_user_by_chat_id(chat_id) is None:
            user = User(chat_id, username, first_name, last_name)
            # Add user to default channels
            for channel in self.session.query(Channel).filter(Channel.default.is_(True)).all():
                user.channels[channel.name] = channel
            self.session.add(user)

    def delete_user(self, chat_id):
        self.session.query(User).filter(User.chat_id.is_(chat_id)).delete()

    def add_channel(self, chat_id, channel: Channel):
        user = self.session.query(User).filter(User.chat_id.is_(chat_id)).one()
        user.channels[channel.name] = channel

    def remove_channel(self, chat_id, channel: Channel):
        user = self.session.query(User).filter(User.chat_id.is_(chat_id)).one()
        del user.channels[channel.name]

    def remove_ldap(self, chat_id):
        user = self.session.query(User).filter(User.chat_id.is_(chat_id)).one()
        user.ldap_account = None

    def get_channel_by_name(self, name):
        return self.session.query(Channel).filter(Channel.name.is_(name)).first()

    def get_channels(self):
        return self.session.query(Channel).all()


class MyDatabase:
    db_engine = None

    def __init__(self, filename):
        self.db_engine = create_engine('sqlite:///' + filename, echo=True)
        try:
            # TODO: Check whether schema is correct if it already exists
            Base.metadata.create_all(self.db_engine)
            #print("Tables created")
        except Exception as e:
            print("Error occurred during Table creation!")
            print(e)
        self.Session = sessionmaker(bind=self.db_engine)

    def get_session(self) -> MyDatabaseSession:
        return MyDatabaseSession(self.Session())


@contextmanager
def my_session_scope(db: MyDatabase):
    """Provide a transactional scope around a series of operations."""
    session = db.get_session()
    try:
        yield session
        session.commit()
    except:
        session.rollback()
        raise
    finally:
        session.close()


@event.listens_for(sqlalchemy.engine.Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    if isinstance(dbapi_connection, SQLite3Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.close()
