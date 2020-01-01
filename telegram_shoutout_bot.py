#!/usr/bin/python3
import logging
import random
import string
import sys
import traceback
import warnings
from queue import Queue, Empty

import telegram.bot
from telegram import Message, ParseMode, InlineKeyboardButton, InlineKeyboardMarkup
from telegram import Update
from telegram.ext import messagequeue as mq, CallbackQueryHandler
from telegram.ext import ConversationHandler, CallbackContext
from telegram.ext import CommandHandler
from telegram.ext import MessageHandler, Filters

from db import MyDatabaseSession
from db import my_session_scope
from telegram_shoutout_bot_conf import BotConf
import db
import bot_ldap
from senddata import SendData

rootLogger = logging.getLogger('')
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
file_handler = logging.FileHandler(BotConf.log_file)
stream_handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
stream_handler.setFormatter(formatter)
rootLogger.addHandler(file_handler)
rootLogger.addHandler(stream_handler)


# TODO: Log all (admin) queries

# States for conversation
SEND_CHANNEL, SEND_MESSAGE, SEND_CONFIRMATION, SUBSCRIBE_CHANNEL, UNSUBSCRIBE_CHANNEL = range(0, 5)

# Keyboard callback data
CB_SEND_DONE, CB_SEND_CONFIRM, CB_SEND_CANCEL, CB_SUBSCRIBE_CANCEL, CB_UNSUBSCRIBE_CANCEL = map(str, range(5, 10))
CB_CHANNEL_PREFIX = 'CH'
CB_CHANNEL_REGEX = r"^" + CB_CHANNEL_PREFIX + r"(\d+)"

# TODO: Implement /help and /settings (standard commands according to Telegram documentation)
# TODO: Not checking for admin permissions in the required places so far: /send
# TODO: Exception Handling (e.g., for database queries)
# TODO: Show channel name above sent messages
# TODO: Persistence for conversations (including keyboad_message_queue/list)
# TODO: Alternative for deletion of keyboards: check in every call if there is an outdated keyboard for the current user
#  (every keyboard if there was a message afterwards?)


class TelegramShoutoutBot:
    my_database = None  # type: db.MyDatabase
    ldap_access = None  # type: bot_ldap.LdapAccess
    # We use the following queue to store chat ids and message ids of messages containing inline keyboards, so that
    # those can be deleted when not needed anymore (as they could have unwanted side effects). This queue has to be
    # thread-safe as it is filled by the asynchronous calls triggered by the message queue.
    keyboard_message_queue = Queue()
    # The message ids are stored in the following dictionary by user when they are read from the queue. This dictionary
    # is only accessed from the main thread, so it does not need to be handled in a thread-safe way.
    keyboard_message_user_lists = {}

    def cmd_start(self, update: Update, context: CallbackContext):
        self.remove_all_inline_keyboards(update, context)
        chat = update.effective_chat
        with my_session_scope(self.my_database) as session:  # type: MyDatabaseSession
            session.add_user(chat.id, chat.username, chat.first_name, chat.last_name)
            context.bot.send_message(chat_id=chat.id, text="Herzlich willkommen!")

    def cmd_stop(self, update: Update, context: CallbackContext):
        self.remove_all_inline_keyboards(update, context)
        chat_id = update.effective_chat.id
        with my_session_scope(self.my_database) as session:
            session.delete_user(chat_id)
            answer = "Alle Daten gelöscht. Der Bot wird keine weiteren Nachrichten schicken.\n" \
                     "Falls du wieder Nachrichten erhalten möchtest, schreibe /start."
            context.bot.send_message(chat_id=chat_id, text=answer)

    def cmd_help(self, update: Update, context: CallbackContext):
        self.remove_all_inline_keyboards(update, context)
        chat_id = update.effective_chat.id
        answer = "Verfügbare Kommandos:\n" \
                 "/start - Shoutout starten.\n" \
                 "/stop - Alle Nachrichten deaktivieren, Daten werden vom Server gelöscht.\n" \
                 "/help - Diese Hilfenachricht anzeigen.\n" \
                 "/subscribe - Zusätzlichen Kanal abonnieren.\n" \
                 "/unsubscribe - Einzelnen Kanal abbestellen.\n" \
                 "\n" \
                 "Befehle für Administratoren\n" \
                 "/admin - Eigenen Admin-Status anzeigen.\n" \
                 "/register - Eigenen Account mit einem DPSG-Account verknüpfen.\n" \
                 "/unregister - Verknüpfung zum DPSG-Account lösen.\n" \
                 "/send - Nachricht an Abonnenten senden.\n"
        context.bot.send_message(chat_id=chat_id, text=answer)

    def cmd_admin(self, update: Update, context: CallbackContext):
        self.remove_all_inline_keyboards(update, context)
        chat_id = update.effective_chat.id
        with my_session_scope(self.my_database) as session:  # type: MyDatabaseSession
            user = session.get_user_by_chat_id(chat_id)
            if user is None:
                answer = self.get_message_user_not_known()
            elif user.ldap_account is None:
                answer = "Du hast keinen DPSG-Account mit deinem Telegram-Zugang verbunden."
            elif self.ldap_access.check_usergroup(user.ldap_account):
                answer = "Du hast einen DPSG-Account mit deinem Telegram-Zugang verbunden " \
                         "und hast Admin-Rechte in Telegram."
            else:
                answer = "Du hast einen DPSG-Account mit deinem Telegram-Zugang verbunden," \
                         "hast aber noch keine Admin-Rechte in Telegram.\n" \
                         "Wende dich mit deiner Chat-ID {0} ans Webteam um Admin-Rechte zu erhalten.".format(chat_id)
            context.bot.send_message(chat_id=chat_id, text=answer)

    def cmd_register(self, update: Update, context: CallbackContext):
        self.remove_all_inline_keyboards(update, context)
        chat_id = update.effective_chat.id
        with my_session_scope(self.my_database) as session:  # type: MyDatabaseSession
            user = session.get_user_by_chat_id(chat_id)
            if user is None:
                answer = self.get_message_user_not_known()
            else:
                letters_and_digits = string.ascii_letters + string.digits
                token = ''.join(random.choice(letters_and_digits) for i in range(20))
                user.ldap_register_token = token
                session.commit()
                # TODO: Write webpage and output link here
                answer = "Chat ID: {0}, Token: {1}".format(chat_id, token)
        context.bot.send_message(chat_id=chat_id, text=answer)

    def cmd_unregister(self, update: Update, context: CallbackContext):
        self.remove_all_inline_keyboards(update, context)
        chat_id = update.effective_chat.id
        with my_session_scope(self.my_database) as session:  # type: MyDatabaseSession
            user = session.get_user_by_chat_id(chat_id)
            if user is None:
                context.bot.send_message(chat_id=chat_id, text=self.get_message_user_not_known())
            else:
                session.remove_ldap(chat_id)
                context.bot.send_message(chat_id=chat_id, text="Account-Zuordnung entfernt")

    # Starting here: Functions for conv_send_handler
    def cmd_send(self, update: Update, context: CallbackContext):
        self.remove_all_inline_keyboards(update, context)
        chat_id = update.effective_chat.id
        with my_session_scope(self.my_database) as session:  # type: MyDatabaseSession
            user = session.get_user_by_chat_id(chat_id)
            if user is None:
                context.bot.send_message(chat_id=chat_id, text=self.get_message_user_not_known())
                return ConversationHandler.END
            elif user.ldap_account is not None and self.ldap_access.check_usergroup(user.ldap_account):
                answer = "Kanal eingeben, an den die Nachricht gesendet werden soll.\n" \
                         "Verfügbare Kanäle:\n" + self.get_all_channel_list(session)
                reply_markup = self.get_all_channel_keyboard(session, CB_SEND_CANCEL)
                context.bot.send_message_keyboard(chat_id=chat_id, text=answer, reply_markup=reply_markup)
                return SEND_CHANNEL
            else:
                answer = "Du hast keine Admin-Rechte um Nachrichten zu verschicken."
                context.bot.send_message(chat_id=chat_id, text=answer)
                return ConversationHandler.END

    def answer_channel(self, update: Update, context: CallbackContext):
        self.remove_all_inline_keyboards(update, context)
        chat_id = update.effective_chat.id
        with my_session_scope(self.my_database) as session:  # type: MyDatabaseSession
            user = session.get_user_by_chat_id(chat_id)
            channel = self.get_channel_from_update(session, update, context)
            if user is None:
                context.bot.send_message(chat_id=chat_id, text=self.get_message_user_not_known())
                return ConversationHandler.END
            elif channel is None:
                answer = "Kanal nicht vorhanden. Bitte anderen Kanal eingeben."
                context.bot.send_message(chat_id=chat_id, text=answer)
                # no return statement (stay in same state)
            else:
                # TODO: Handle case, when there is no LDAP filter defined for this channel
                if self.ldap_access.check_filter(user.ldap_account, channel.ldap_filter):
                    send_data = SendData()
                    context.user_data["send"] = send_data
                    send_data.channel = channel.name
                    answer = "Nachricht eingeben, die gesendet werden soll."
                    context.bot.send_message(chat_id=chat_id, text=answer)
                    return SEND_MESSAGE
                else:
                    answer = "Du hast keine Berechtigung an diesen Kanal zu schreiben."
                    reply_markup = self.get_all_channel_keyboard(session, CB_SEND_CANCEL)
                    context.bot.send_message_keyboard(chat_id=chat_id, text=answer, reply_markup=reply_markup)
                    # no return statement (stay in same state)

    def answer_message(self, update: Update, context: CallbackContext):
        self.remove_all_inline_keyboards(update, context)
        chat_id = update.effective_chat.id
        send_data = context.user_data["send"]  # type: SendData
        if send_data.messages is None:
            send_data.messages = []
        if self.message_valid(update.message):
            send_data.messages.append(update.message)
            answer = "Weitere Nachrichten anfügen, abschließen mit /done oder Abbrechen mit /cancel."
            keyboard = [[InlineKeyboardButton("Done", callback_data=CB_SEND_DONE)],
                        [InlineKeyboardButton("Cancel", callback_data=CB_SEND_CANCEL)]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            context.bot.send_message_keyboard(chat_id=chat_id, text=answer, reply_markup=reply_markup)
        else:
            answer = "Dieses Nachrichtenformat wird nicht unterstützt.\n" \
                     "Bitte neue Nachricht eingeben."
            context.bot.send_message(chat_id=chat_id, text=answer)
        # no return statement (stay in same state)

    def answer_done(self, update: Update, context: CallbackContext):
        self.remove_all_inline_keyboards(update, context)
        chat_id = update.effective_chat.id
        send_data = context.user_data["send"]  # type: SendData
        if send_data.messages is None or len(send_data.messages) < 1:
            answer = "Bitte mindestens eine Nachricht eingeben oder Abbrechen mit /cancel."
            context.bot.send_message(chat_id=chat_id, text=answer)
            return None

        # Send saved data to user
        answer = "Diese Daten sind gespeichert:"
        context.bot.send_message(chat_id=chat_id, text=answer)
        answer = "Kanalname: {0}".format(send_data.channel)
        context.bot.send_message(chat_id=chat_id, text=answer)
        for message in send_data.messages:  # type: Message
            self.resend_message(update.effective_chat.id, message, context)

        # Message asking for confirmation
        answer = "Versand bestätigen mit /confirm oder Abbrechen mit /cancel."
        keyboard = [[InlineKeyboardButton("Confirm", callback_data=CB_SEND_CONFIRM)],
                    [InlineKeyboardButton("Cancel", callback_data=CB_SEND_CANCEL)]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        context.bot.send_message_keyboard(chat_id=chat_id, text=answer, reply_markup=reply_markup)
        return SEND_CONFIRMATION

    def answer_confirm(self, update: Update, context: CallbackContext):
        # TODO: Verify sufficient permissions here again?
        self.remove_all_inline_keyboards(update, context)
        answer = "Nachricht wird versendet."
        context.bot.send_message(chat_id=update.effective_chat.id, text=answer)
        send_data = context.user_data["send"]  # type: SendData
        channel_name = send_data.channel
        with my_session_scope(self.my_database) as session:  # type: MyDatabaseSession
            for user in session.get_users():
                if channel_name in user.channels:
                    for message in send_data.messages:
                        self.resend_message(user.chat_id, message, context)
            return ConversationHandler.END

    def cancel_send(self, update: Update, context: CallbackContext):
        self.remove_all_inline_keyboards(update, context)
        chat_id = update.effective_chat.id
        context.user_data["send"] = None
        context.bot.send_message(chat_id=chat_id, text="Nachrichtenversand abgebrochen.")
        return ConversationHandler.END

    # Starting here: Functions for conv_subscribe_handler
    def cmd_subscribe(self, update: Update, context: CallbackContext):
        self.remove_all_inline_keyboards(update, context)
        chat_id = update.effective_chat.id
        with my_session_scope(self.my_database) as session:  # type: MyDatabaseSession
            user = session.get_user_by_chat_id(chat_id)
            if user is None:
                context.bot.send_message(chat_id=chat_id, text=self.get_message_user_not_known())
                return ConversationHandler.END
            else:
                answer = "Kanal eingeben, der abonniert werden soll oder Abbrechen mit /cancel.\n" \
                         "Bereits abonnierte Kanäle:\n" + self.get_subscribed_channel_list(session, chat_id) + \
                         "Alle verfügbaren Kanäle:\n" + self.get_all_channel_list(session)
                reply_markup = self.get_all_channel_keyboard(session, CB_SUBSCRIBE_CANCEL)
                context.bot.send_message_keyboard(chat_id=chat_id, text=answer, reply_markup=reply_markup)
                return SUBSCRIBE_CHANNEL

    def answer_subscribe_channel(self, update: Update, context: CallbackContext):
        # TODO: Prüfe, dass Kanal noch nicht abonniert ist
        self.remove_all_inline_keyboards(update, context)
        chat_id = update.effective_chat.id
        with my_session_scope(self.my_database) as session:  # type: MyDatabaseSession
            user = session.get_user_by_chat_id(chat_id)
            channel = self.get_channel_from_update(session, update, context)
            if user is None:
                context.bot.send_message(chat_id=chat_id, text=self.get_message_user_not_known())
                return ConversationHandler.END
            elif channel is not None:
                session.add_channel(chat_id, channel)
                answer = "Kanal abonniert: " + channel.name
                context.bot.send_message(chat_id=chat_id, text=answer)
                return ConversationHandler.END
            else:
                answer = "Kanal nicht vorhanden. Bitte anderen Kanal eingeben."
                context.bot.send_message(chat_id=chat_id, text=answer)
                # no return statement (stay in same state)

    def cancel_subscribe(self, update: Update, context: CallbackContext):
        self.remove_all_inline_keyboards(update, context)
        answer = "Subscribe abgebrochen."
        context.bot.send_message(chat_id=update.effective_chat.id, text=answer)
        return ConversationHandler.END

    # Starting here: Functions for conv_unsubscribe_handler
    def cmd_unsubscribe(self, update: Update, context: CallbackContext):
        self.remove_all_inline_keyboards(update, context)
        chat_id = update.effective_chat.id
        with my_session_scope(self.my_database) as session:  # type: MyDatabaseSession
            user = session.get_user_by_chat_id(chat_id)
            if user is None:
                context.bot.send_message(chat_id=chat_id, text=self.get_message_user_not_known())
                return ConversationHandler.END
            else:
                answer = "Kanal eingeben, der deabonniert werden soll oder Abbrechen mit /cancel.\n" \
                         "Bereits abonnierte Kanäle:\n" + self.get_subscribed_channel_list(session, chat_id)
                reply_markup = self.get_subscribed_channel_keyboard(session, chat_id, CB_UNSUBSCRIBE_CANCEL)
                context.bot.send_message_keyboard(chat_id=chat_id, text=answer, reply_markup=reply_markup)
                return UNSUBSCRIBE_CHANNEL

    def answer_unsubscribe_channel(self, update: Update, context: CallbackContext):
        self.remove_all_inline_keyboards(update, context)
        chat_id = update.effective_chat.id
        with my_session_scope(self.my_database) as session:  # type: MyDatabaseSession
            user = session.get_user_by_chat_id(chat_id)
            channel = self.get_channel_from_update(session, update, context)
            if user is None:
                context.bot.send_message(chat_id=chat_id, text=self.get_message_user_not_known())
                return ConversationHandler.END
            elif channel is None:
                answer = "Kanal nicht vorhanden." \
                         "Bitte anderen Kanal eingeben oder Abbrechen mit /cancel."
                context.bot.send_message(chat_id=chat_id, text=answer)
                # no return statement (stay in same state)
            elif channel not in user.channels.values():
                answer = "Kanal nicht abonniert." \
                         "Bitte anderen Kanal eingeben oder Abbrechen mit /cancel."
                context.bot.send_message(chat_id=chat_id, text=answer)
                # no return statement (stay in same state)
            else:
                session.remove_channel(chat_id, channel)
                answer = "Kanal deabonniert: " + channel.name
                context.bot.send_message(chat_id=chat_id, text=answer)
                return ConversationHandler.END

    def cancel_unsubscribe(self, update: Update, context: CallbackContext):
        self.remove_all_inline_keyboards(update, context)
        answer = "Unsubscribe abgebrochen."
        context.bot.send_message(chat_id=update.effective_chat.id, text=answer)
        return ConversationHandler.END

    def answer_invalid_cancel(self, update: Update, context: CallbackContext):
        answer = "Du befindest dich bereits im Hauptmenü und kannst gerade nichts abbrechen."
        context.bot.send_message(chat_id=update.effective_chat.id, text=answer)

    def answer_invalid_cmd(self, update: Update, context: CallbackContext):
        answer = "Du kannst dieses Kommando gerade nicht anwenden.\n" \
                 "Vermutlich musst du das vorherige Kommando mit /cancel abbrechen."
        context.bot.send_message(chat_id=update.effective_chat.id, text=answer)

    def answer_invalid_msg(self, update: Update, context: CallbackContext):
        answer = "Ich verstehe diese Nachricht gerade nicht.\n" \
                 "Benutze /help für eine Liste der vefügbaren Kommandos."
        context.bot.send_message(chat_id=update.effective_chat.id, text=answer)

    def error(self, update: Update, context: CallbackContext):
        """Log Errors caused by Updates."""
        # we want to notify the user of this problem. This will always work, but not notify users if the update is an
        # callback or inline query, or a poll update. In case you want this, keep in mind that sending the message
        # could fail
        if update.effective_message:
            text = "Bei deiner Anfrage ist leider ein Fehler aufgetreten."
            update.effective_message.reply_text(text)
        # This traceback is created with accessing the traceback object from the sys.exc_info, which is returned as the
        # third value of the returned tuple. Then we use the traceback.format_tb to get the traceback as a string, which
        # for a weird reason separates the line breaks in a list, but keeps the linebreaks itself. So just joining an
        # empty string works fine.
        trace = "".join(traceback.format_tb(sys.exc_info()[2]))
        # lets try to get as much information from the telegram update as possible
        payload = ""
        # normally, we always have an user. If not, its either a channel or a poll update.
        if update.effective_user:
            payload += ' with the user {0}'.format(update.effective_user.id)
        # there are more situations when you don't get a chat
        if update.effective_chat:
            payload += ' within the chat <i>{0}</i>'.format(update.effective_chat.title)
            if update.effective_chat.username:
                payload += ' (@{0})'.format(update.effective_chat.username)
        # but only one where you have an empty payload by now: A poll (buuuh)
        if update.poll:
            payload += ' with the poll id {0}.'.format(update.poll.id)
        # lets put this in a "well" formatted text
        text = "Hey.\n The error <code>{0}</code> happened{1}. The full traceback:\n\n<code>{2}" \
               "</code>".format(context.error, payload, trace)
        # and send it to the dev(s)
        for dev_id in BotConf.bot_devs:
            context.bot.send_message(dev_id, "An error occured in the bot and was logged.")
        # we raise the error again, so the logger module catches it. If you don't use the logger module, use it.
        logger.warning('Update "%s" caused error "%s".\nFull information: %s', update, context.error, text)

    @staticmethod
    def message_valid(message: Message):
        if message.text or message.photo or message.sticker:
            return True
        else:
            return False

    @staticmethod
    def resend_message(chat_id, message: Message, context: CallbackContext):
        # The following case distinction is similar to the one in
        # https://github.com/91DarioDev/forwardscoverbot/blob/master/forwardscoverbot/messages.py
        if message.text:
            context.bot.send_message(
                chat_id=chat_id,
                text=message.text_html,
                parse_mode=ParseMode.HTML)
        elif message.photo:
            media = message.photo[-1].file_id
            context.bot.send_photo(
                chat_id=chat_id,
                photo=media,
                parse_mode=ParseMode.HTML
            )
        elif message.sticker:
            media = message.sticker.file_id
            context.bot.send_sticker(
                chat_id=chat_id,
                sticker=media
            )
        # Not handled so far: voice, document, audio, video, contact, venue, location, video_note, game

    def get_all_channel_list(self, session: MyDatabaseSession) -> str:
        answer = ""
        for channel in session.get_channels():
            answer += "{0} - {1}\n".format(channel.name, channel.description)
        return answer

    def get_subscribed_channel_list(self, session: MyDatabaseSession, chat_id) -> str:
        answer = ""
        user = session.get_user_by_chat_id(chat_id)
        for channel in user.channels.values():
            answer += "{0} - {1}\n".format(channel.name, channel.description)
        return answer

    def get_all_channel_keyboard(self, session: MyDatabaseSession, cancel_callback_data: str) -> InlineKeyboardMarkup:
        keyboard = []
        for channel in session.get_channels():
            button_text = "{0} - {1}\n".format(channel.name, channel.description)
            callback_data = CB_CHANNEL_PREFIX + str(channel.id)
            keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
        keyboard.append([InlineKeyboardButton("Cancel", callback_data=cancel_callback_data)])
        return InlineKeyboardMarkup(keyboard)

    def get_subscribed_channel_keyboard(self, session: MyDatabaseSession, chat_id, cancel_callback_data: str)\
            -> InlineKeyboardMarkup:
        keyboard = []
        user = session.get_user_by_chat_id(chat_id)
        for channel in user.channels.values():
            button_text = "{0} - {1}\n".format(channel.name, channel.description)
            callback_data = CB_CHANNEL_PREFIX + str(channel.id)
            keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
        keyboard.append([InlineKeyboardButton("Cancel", callback_data=cancel_callback_data)])
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def get_message_user_not_known() -> str:
        return "Dein Telegram-Account ist nicht bekannt." \
               "Um mit dem Bot zu kommunizieren, musst du zunächst /start eingeben."

    def remove_all_inline_keyboards(self, update: Update, context: CallbackContext):
        # Read all items from the queue
        while True:
            try:
                (item_chat_id, item_msg_id) = self.keyboard_message_queue.get(block=False)
                if item_chat_id not in self.keyboard_message_user_lists:
                    self.keyboard_message_user_lists[item_chat_id] = []
                self.keyboard_message_user_lists[item_chat_id].append(item_msg_id)
            except Empty:
                break

        # Check list for the active user if there are keyboards to delete
        chat_id = update.effective_chat.id
        if chat_id in self.keyboard_message_user_lists:
            for msg_id in self.keyboard_message_user_lists[chat_id]:
                context.bot.edit_message_reply_markup(chat_id=chat_id,
                                                      message_id=msg_id,
                                                      reply_markup=None)
            del self.keyboard_message_user_lists[chat_id]

    def get_channel_from_update(self, session: MyDatabaseSession, update: Update, context: CallbackContext):
        # Channel name can be given as a string in the message or as a corresponding callback handler containing the id
        if update.message:
            requested_channel = update.message.text
            return session.get_channel_by_name(requested_channel)
        elif update.callback_query:
            requested_channel_id = int(context.match.group(1))
            return session.get_channel_by_id(requested_channel_id)

    def __init__(self):
        from telegram.utils.request import Request

        self.my_database = db.MyDatabase(BotConf.database_file)

        self.ldap_access = bot_ldap.LdapAccess(BotConf.ldap_server, BotConf.ldap_user,
                                               BotConf.ldap_password, BotConf.ldap_base_group_filter)

        # recommended values for production: 29/1017
        q = mq.MessageQueue(all_burst_limit=29, all_time_limit_ms=1017)
        # set connection pool size for bot
        request = Request(con_pool_size=8)
        mqbot = MQBot(token=BotConf.bot_token,
                      request=request,
                      mqueue=q,
                      keyboard_message_queue=self.keyboard_message_queue)
        updater = telegram.ext.updater.Updater(bot=mqbot, use_context=True)
        dispatcher = updater.dispatcher

        send_cancel_handler = CommandHandler('cancel', self.cancel_send)

        with warnings.catch_warnings():
            # We filter out a certain warning message by python-telegram-bot here
            warnings.filterwarnings('ignore', "If 'per_message=False', 'CallbackQueryHandler' will not be "
                                    "tracked for every message.")
            conversation_handler = ConversationHandler(
                entry_points=[
                    CommandHandler('start', self.cmd_start),
                    CommandHandler('stop', self.cmd_stop),
                    CommandHandler('help', self.cmd_help),
                    CommandHandler('admin', self.cmd_admin),
                    CommandHandler('register', self.cmd_register),
                    CommandHandler('unregister', self.cmd_unregister),
                    CommandHandler('send', self.cmd_send),
                    CommandHandler('subscribe', self.cmd_subscribe),
                    CommandHandler('unsubscribe', self.cmd_unsubscribe)
                ],
                states={
                    SEND_CHANNEL: [CallbackQueryHandler(pattern=CB_CHANNEL_REGEX, callback=self.answer_channel),
                                   CallbackQueryHandler(pattern=CB_SEND_CANCEL, callback=self.cancel_send),
                                   send_cancel_handler,
                                   MessageHandler(Filters.text, self.answer_channel)],
                    SEND_MESSAGE: [CallbackQueryHandler(pattern=CB_SEND_DONE, callback=self.answer_done),
                                   CallbackQueryHandler(pattern=CB_SEND_CANCEL, callback=self.cancel_send),
                                   CommandHandler('done', self.answer_done),
                                   send_cancel_handler,
                                   # TODO More restrictive filter here?
                                   # TODO Handler for non-matched messages?
                                   MessageHandler(Filters.all & (~ Filters.command), self.answer_message)],
                    SEND_CONFIRMATION: [CallbackQueryHandler(pattern=CB_SEND_CONFIRM, callback=self.answer_confirm),
                                        CallbackQueryHandler(pattern=CB_SEND_CANCEL, callback=self.cancel_send),
                                        CommandHandler('confirm', self.answer_confirm),
                                        send_cancel_handler],
                    SUBSCRIBE_CHANNEL: [CallbackQueryHandler(pattern=CB_CHANNEL_REGEX,
                                                             callback=self.answer_subscribe_channel),
                                        CallbackQueryHandler(pattern=CB_SUBSCRIBE_CANCEL,
                                                             callback=self.cancel_subscribe),
                                        CommandHandler('cancel', self.cancel_subscribe),
                                        MessageHandler(Filters.text, self.answer_subscribe_channel)],
                    UNSUBSCRIBE_CHANNEL: [CallbackQueryHandler(pattern=CB_CHANNEL_REGEX,
                                                               callback=self.answer_unsubscribe_channel),
                                          CallbackQueryHandler(pattern=CB_UNSUBSCRIBE_CANCEL,
                                                               callback=self.cancel_unsubscribe),
                                          CommandHandler('cancel', self.cancel_unsubscribe),
                                          MessageHandler(Filters.text, self.answer_unsubscribe_channel)]
                },
                fallbacks=[
                ]
            )
        dispatcher.add_handler(conversation_handler)

        fallback_cancel_handler = CommandHandler('cancel', self.answer_invalid_cancel)
        fallback_cmd_handler = MessageHandler(Filters.command, self.answer_invalid_cmd)
        fallback_msg_handler = MessageHandler(Filters.all, self.answer_invalid_msg)
        dispatcher.add_handler(fallback_cancel_handler)
        dispatcher.add_handler(fallback_cmd_handler)
        dispatcher.add_handler(fallback_msg_handler)

        # log all errors
        dispatcher.add_error_handler(self.error)

        updater.start_polling()
        updater.idle()


class MQBot(telegram.bot.Bot):
    """A subclass of Bot which delegates send method handling to MQ"""
    def __init__(self, *args, is_queued_def=True, mqueue=None, keyboard_message_queue=None, **kwargs):
        super(MQBot, self).__init__(*args, **kwargs)
        # below 2 attributes should be provided for decorator usage
        self._is_messages_queued_default = is_queued_def
        self._msg_queue = mqueue or mq.MessageQueue()
        self._keyboard_message_queue = keyboard_message_queue

    def __del__(self):
        try:
            self._msg_queue.stop()
        except:
            pass

    @mq.queuedmessage
    def send_message(self, *args, **kwargs):
        """Wrapped method would accept new `queued` and `isgroup`
        OPTIONAL arguments"""
        return super(MQBot, self).send_message(*args, **kwargs)

    @mq.queuedmessage
    def send_message_keyboard(self, *args, **kwargs):
        """Wrapped method would accept new `queued` and `isgroup`
        OPTIONAL arguments"""
        ret = super(MQBot, self).send_message(*args, **kwargs)
        if self._keyboard_message_queue is not None:
            self._keyboard_message_queue.put((ret.chat_id, ret.message_id))
        return ret

    @mq.queuedmessage
    def send_photo(self, *args, **kwargs):
        return super(MQBot, self).send_photo(*args, **kwargs)

    @mq.queuedmessage
    def send_sticker(self, *args, **kwargs):
        return super(MQBot, self).send_sticker(*args, **kwargs)

    @mq.queuedmessage
    def edit_message_reply_markup(self, *args, **kwargs):
        return super(MQBot, self).edit_message_reply_markup(*args, **kwargs)


if __name__ == '__main__':
    bot = TelegramShoutoutBot()
