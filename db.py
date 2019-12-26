import time

from sqlalchemy import Table, Column, Integer, String, Boolean, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, selectinload  # , scoped_session
from sqlalchemy import create_engine
from sqlalchemy.orm.collections import attribute_mapped_collection

Base = declarative_base()


user_channels = Table('user_channels', Base.metadata,
                      Column('chat_id', ForeignKey('users.chat_id'), primary_key=True),
                      Column('channel_id', ForeignKey('channels.id'), primary_key=True)
                      )


class User(Base):
    __tablename__ = "users"
    chat_id = Column(Integer, primary_key=True)
    username = Column(String)
    first_name = Column(String)
    last_name = Column(String)
    time_start = Column(Integer)
    last_msg = Column(String)
    is_admin = Column(Boolean)

    channels = relationship('Channel',
                            collection_class=attribute_mapped_collection('name'),
                            secondary=user_channels,
                            back_populates='users')

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
        return "<User(chat_id='%s', username='%s', first_name='%s', last_name='%s', time_start='%s', last_msg='%s')>" %(self.chat_id, self.username, self.first_name, self.last_name, self.time_start, self.last_msg)


class Channel(Base):
    __tablename__ = "channels"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    description = Column(String)

    users = relationship('User', secondary=user_channels, back_populates='channels')


class MyDatabase:
    db_engine = None

    def __init__(self, filename):
        self.db_engine = create_engine('sqlite:///' + filename)
        try:
            # TODO: Check if schema correct if already existing
            Base.metadata.create_all(self.db_engine)
            #print("Tables created")
        except Exception as e:
            print("Error occurred during Table creation!")
            print(e)
        self.Session = sessionmaker(bind=self.db_engine)

    def get_session(self):
        return self.Session()


class UserDatabase:
    db = None
    users = None

    def __init__(self, db):
        self.db = db
        session = self.db.get_session()
        db_users = session.query(User).options(selectinload(User.channels)).all()
        self.users = {user.chat_id: user for user in db_users}
        session.close()

    def add_user(self, chat_id, username, first_name, last_name):
        if chat_id not in self.users:
            user = User(chat_id, username, first_name, last_name)
            session = self.db.get_session()
            session.add(user)
            self.users[chat_id] = user
            session.commit()
            session.close()

    def delete_user(self, chat_id):
        session = self.db.get_session()
        session.query(User).filter(User.chat_id == chat_id).delete()
        del self.users[chat_id]
        session.commit()
        session.close()

    def get_by_chat_id(self, chat_id):
        return self.users.get(chat_id, None)


class ChannelDatabase:
    db = None
    channels = None
    channels_by_name = None

    def __init__(self, db):
        self.db = db
        session = self.db.get_session()
        db_channels = session.query(Channel).all()
        self.channels = {channel.id: channel for channel in db_channels}
        self.channels_by_name = {channel.name: channel for channel in db_channels}
        session.close()
