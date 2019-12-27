#!/usr/bin/python3
import telegram.bot
from telegram import Message, ParseMode
from telegram import Update
from telegram.ext import messagequeue as mq
from telegram.ext import Updater, ConversationHandler, CallbackContext
from telegram.ext import CommandHandler
from telegram.ext import MessageHandler, Filters

from telegram_shoutout_bot_conf import BotConf
import db
import bot_ldap
from senddata import SendData

import logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                     level=logging.INFO)
logger = logging.getLogger(__name__)

# TODO: Log all (admin) queries

# States for send conversation
CHANNEL, MESSAGE, CONFIRMATION = range(3)
SUBSCRIBE_CHANNEL = range(1)
UNSUBSCRIBE_CHANNEL = range(1)


# TODO: Implement /help and /settings (standard commands according to Telegram documentation)
# TODO: Not checking for admin permissions in the required places so far


class TelegramShoutoutBot:
    user_database = None  # type: db.UserDatabase
    channel_database = None  # type: db.ChannelDatabase
    ldap_access = None  # type: bot_ldap.LdapAccess

    def cmd_start(self, update: Update, context: CallbackContext):
        chat = update.effective_chat
        self.user_database.add_user(chat.id, chat.username, chat.first_name, chat.last_name)
        context.bot.send_message(chat_id=chat.id, text="Herzlich willkommen!")

    def cmd_stop(self, update: Update, context: CallbackContext):
        chat_id = update.effective_chat.id
        self.user_database.delete_user(chat_id)
        answer = "Alle Daten gelöscht. Der Bot wird keine weiteren Nachrichten schicken.\n" \
                 "Falls du wieder Nachrichten erhalten möchtest, schreibe /start."
        context.bot.send_message(chat_id=chat_id, text=answer)

    def cmd_help(self, update: Update, context: CallbackContext):
        chat_id = update.effective_chat.id
        answer = "Verfügbare Kommandos:\n" \
                 "/start\n" \
                 "/stop\n" \
                 "/help\n" \
                 "/admin\n" \
                 "/send\n" \
                 "/subscribe\n" \
                 "/unsubscribe\n"
        context.bot.send_message(chat_id=chat_id, text=answer)

    # TODO: DEBUG ONLY
    def cmd_echo(self, update: Update, context: CallbackContext):
        context.bot.send_message(chat_id=update.effective_chat.id, text=update.message.text)

    def cmd_admin(self, update: Update, context: CallbackContext):
        chat_id = update.effective_chat.id
        user = self.user_database.get_by_chat_id(update.effective_chat.id)
        if user.ldap_account is None:
            answer = "Du hast keinen DPSG-Account mit deinem Telegram-Zugang verbunden."
        elif self.ldap_access.check_usergroup(user.ldap_account):
            answer = "Du hast einen DPSG-Account mit deinem Telegram-Zugang verbunden " \
                     "und hast Admin-Rechte in Telegram."
        else:
            answer = "Du hast einen DPSG-Account mit deinem Telegram-Zugang verbunden," \
                     "hast aber noch keine Admin-Rechte in Telegram.\n" \
                     "Wende dich mit deiner Chat-ID {0} ans Webteam um Admin-Rechte zu erhalten.".format(chat_id)
        context.bot.send_message(chat_id=chat_id, text=answer)

    # Starting here: Functions for conv_send_handler
    def cmd_send(self, update: Update, context: CallbackContext):
        answer = "Kanal eingeben, an den die Nachricht gesendet werden soll.\n" \
                 "Verfügbare Kanäle:\n" + self.get_all_channel_list()
        context.bot.send_message(chat_id=update.effective_chat.id, text=answer)
        return CHANNEL

    def answer_channel(self, update: Update, context: CallbackContext):
        requested_channel = update.message.text
        if requested_channel in self.channel_database.channels_by_name:
            send_data = SendData()
            context.user_data["send"] = send_data
            send_data.channel = requested_channel
            answer = "Nachricht eingeben, die gesendet werden soll."
            context.bot.send_message(chat_id=update.effective_chat.id, text=answer)
            return MESSAGE
        else:
            answer = "Kanal nicht vorhanden. Bitte anderen Kanal eingeben."
            context.bot.send_message(chat_id=update.effective_chat.id, text=answer)
            # no return statement (stay in same state)

    def answer_message(self, update: Update, context: CallbackContext):
        send_data = context.user_data["send"]  # type: SendData
        if send_data.messages is None:
            send_data.messages = []
        if self.message_valid(update.message):
            send_data.messages.append(update.message)
            answer = "Weitere Nachrichten anfügen, abschließen mit /done oder Abbrechen mit /cancel."
            context.bot.send_message(chat_id=update.effective_chat.id, text=answer)
        else:
            answer = "Dieses Nachrichtenformat wird nicht unterstützt.\n" \
                     "Bitte neue Nachricht eingeben."
            context.bot.send_message(chat_id=update.effective_chat.id, text=answer)
        # no return statement (stay in same state)

    def answer_done(self, update: Update, context: CallbackContext):
        chat_id = update.effective_chat.id
        send_data = context.user_data["send"]  # type: SendData
        if send_data.messages is None or len(send_data.messages) < 1:
            answer = "Bitte mindestens eine Nachricht eingeben oder Abbrechen mit /cancel."
            context.bot.send_message(chat_id=chat_id, text=answer)
            return None
        answer = "Diese Daten sind gespeichert:"
        context.bot.send_message(chat_id=chat_id, text=answer)
        answer = "Kanalname: {0}".format(send_data.channel)
        context.bot.send_message(chat_id=chat_id, text=answer)
        for message in send_data.messages:  # type: Message
            self.resend_message(update.effective_chat.id, message, context)
        answer = "Versand bestätigen mit /confirm oder Abbrechen mit /cancel."
        context.bot.send_message(chat_id=chat_id, text=answer)
        return CONFIRMATION

    def answer_confirm(self, update: Update, context: CallbackContext):
        answer = "Nachricht wird versendet."
        context.bot.send_message(chat_id=update.effective_chat.id, text=answer)
        send_data = context.user_data["send"]  # type: SendData
        channel = send_data.channel
        for user in self.user_database.users.values():
            if channel in user.channels:
                for message in send_data.messages:
                    self.resend_message(user.chat_id, message, context)
        return ConversationHandler.END

    def answer_await_confirm(self, update: Update, context: CallbackContext):
        answer = "Versand bestätigen mit /confirm oder Abbrechen mit /cancel."
        context.bot.send_message(chat_id=update.effective_chat.id, text=answer)
        # no return statement (stay in same state)

    def cancel_send(self, update: Update, context: CallbackContext):
        context.user_data["send"] = None
        context.bot.send_message(chat_id=update.effective_chat.id, text="Nachrichtenversand abgebrochen.")
        return ConversationHandler.END

    # Starting here: Functions for conv_subscribe_handler
    def cmd_subscribe(self, update: Update, context: CallbackContext):
        chat_id = update.effective_chat.id
        answer = "Kanal eingeben, der abonniert werden soll.\n" \
                 "Bereits abonnierte Kanäle:\n" + self.get_subscribed_channel_list(chat_id) + \
                 "Alle verfügbaren Kanäle:\n" + self.get_all_channel_list()
        context.bot.send_message(chat_id=chat_id, text=answer)
        return SUBSCRIBE_CHANNEL

    def answer_subscribe_channel(self, update: Update, context: CallbackContext):
        chat_id = update.effective_chat.id
        channel_name = update.message.text
        if channel_name in self.channel_database.channels_by_name:
            self.user_database.add_channel(chat_id, channel_name)
            answer = "Kanal abonniert: " + channel_name
            context.bot.send_message(chat_id=chat_id, text=answer)
            return ConversationHandler.END
        else:
            answer = "Kanal nicht vorhanden. Bitte anderen Kanal eingeben."
            context.bot.send_message(chat_id=chat_id, text=answer)
            # no return statement (stay in same state)

    def cancel_subscribe(self, update: Update, context: CallbackContext):
        answer = "Subscribe abgebrochen."
        context.bot.send_message(chat_id=update.effective_chat.id, text=answer)
        return ConversationHandler.END

    # Starting here: Functions for conv_unsubscribe_handler
    def cmd_unsubscribe(self, update: Update, context: CallbackContext):
        chat_id = update.effective_chat.id
        answer = "Kanal eingeben, der deabonniert werden soll.\n" \
                 "Bereits abonnierte Kanäle:\n" + self.get_subscribed_channel_list(chat_id)
        context.bot.send_message(chat_id=chat_id, text=answer)
        return UNSUBSCRIBE_CHANNEL

    def answer_unsubscribe_channel(self, update: Update, context: CallbackContext):
        chat_id = update.effective_chat.id
        channel_name = update.message.text
        user = self.user_database.get_by_chat_id(chat_id)
        if channel_name not in self.channel_database.channels_by_name:
            answer = "Kanal nicht vorhanden." \
                     "Bitte anderen Kanal eingeben oder Abbrechen mit /cancel."
            context.bot.send_message(chat_id=chat_id, text=answer)
            # no return statement (stay in same state)
        elif channel_name not in user.channels:
            answer = "Kanal nicht abonniert." \
                     "Bitte anderen Kanal eingeben oder Abbrechen mit /cancel."
            context.bot.send_message(chat_id=chat_id, text=answer)
            # no return statement (stay in same state)
        else:
            self.user_database.remove_channel(chat_id, channel_name)
            answer = "Kanal deabonniert: " + channel_name
            context.bot.send_message(chat_id=chat_id, text=answer)
            return ConversationHandler.END

    def cancel_unsubscribe(self, update: Update, context: CallbackContext):
        answer = "Unsubscribe abgebrochen."
        context.bot.send_message(chat_id=update.effective_chat.id, text=answer)
        return ConversationHandler.END

    def error(self, update: Update, context: CallbackContext):
        """Log Errors caused by Updates."""
        logger.warning('Update "%s" caused error "%s"', update, context.error)

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

    def get_all_channel_list(self) -> str:
        answer = ""
        for channelId, channel in self.channel_database.channels.items():
            answer += "{0} - {1}\n".format(channel.name, channel.description)
        return answer

    def get_subscribed_channel_list(self, chat_id) -> str:
        answer = ""
        user = self.user_database.get_by_chat_id(chat_id)
        for channel in user.channels.values():
            answer += "{0} - {1}\n".format(channel.name, channel.description)
        return answer

    def __init__(self):
        from telegram.utils.request import Request

        my_database = db.MyDatabase(BotConf.database_file)
        self.user_database = db.UserDatabase(my_database)
        self.channel_database = db.ChannelDatabase(my_database)

        self.ldap_access = bot_ldap.LdapAccess(BotConf.ldap_server, BotConf.ldap_user,
                                               BotConf.ldap_password, BotConf.ldap_base_group_filter)

        # recommended values for production: 29/1017
        q = mq.MessageQueue(all_burst_limit=3, all_time_limit_ms=3000)
        # set connection pool size for bot
        request = Request(con_pool_size=8)
        mqbot = MQBot(token=BotConf.bot_token, request=request, mqueue=q)
        updater = telegram.ext.updater.Updater(bot=mqbot, use_context=True)
        dispatcher = updater.dispatcher

        start_handler = CommandHandler('start', self.cmd_start)
        dispatcher.add_handler(start_handler)
        stop_handler = CommandHandler('stop', self.cmd_stop)
        dispatcher.add_handler(stop_handler)
        help_handler = CommandHandler('help', self.cmd_help)
        dispatcher.add_handler(help_handler)
        admin_handler = CommandHandler('admin', self.cmd_admin)
        dispatcher.add_handler(admin_handler)

        send_cancel_handler = CommandHandler('cancel', self.cancel_send)
        conv_send_handler = ConversationHandler(
            entry_points=[CommandHandler('send', self.cmd_send)],
            states={
                CHANNEL: [MessageHandler(Filters.text, self.answer_channel)],
                MESSAGE: [CommandHandler('done', self.answer_done),
                          send_cancel_handler,
                          # TODO More restrictive filter here?
                          # TODO Handler for non-matched messages?
                          MessageHandler(Filters.all & (~ Filters.command), self.answer_message)],
                CONFIRMATION: [CommandHandler('confirm', self.answer_confirm),
                               send_cancel_handler,
                               MessageHandler(Filters.all, self.answer_await_confirm)]
            },
            fallbacks=[send_cancel_handler]
        )
        dispatcher.add_handler(conv_send_handler)

        subscribe_cancel_handler = CommandHandler('cancel', self.cancel_subscribe)
        conv_subscribe_handler = ConversationHandler(
            entry_points=[CommandHandler('subscribe', self.cmd_subscribe)],
            states={
                SUBSCRIBE_CHANNEL: [MessageHandler(Filters.text, self.answer_subscribe_channel)]
            },
            fallbacks=[subscribe_cancel_handler]
        )
        dispatcher.add_handler(conv_subscribe_handler)

        unsubscribe_cancel_handler = CommandHandler('cancel', self.cancel_unsubscribe)
        conv_unsubscribe_handler = ConversationHandler(
            entry_points=[CommandHandler('unsubscribe', self.cmd_unsubscribe)],
            states={
                UNSUBSCRIBE_CHANNEL: [MessageHandler(Filters.text, self.answer_unsubscribe_channel)]
            },
            fallbacks=[unsubscribe_cancel_handler]
        )
        dispatcher.add_handler(conv_unsubscribe_handler)

        #echo_handler = MessageHandler(Filters.text, self.cmd_echo)
        #dispatcher.add_handler(echo_handler)

        # log all errors
        dispatcher.add_error_handler(self.error)

        updater.start_polling()
        updater.idle()


class MQBot(telegram.bot.Bot):
    """A subclass of Bot which delegates send method handling to MQ"""
    def __init__(self, *args, is_queued_def=True, mqueue=None, **kwargs):
        super(MQBot, self).__init__(*args, **kwargs)
        # below 2 attributes should be provided for decorator usage
        self._is_messages_queued_default = is_queued_def
        self._msg_queue = mqueue or mq.MessageQueue()

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
    def send_photo(self, *args, **kwargs):
        return super(MQBot, self).send_photo(*args, **kwargs)

    @mq.queuedmessage
    def send_sticker(self, *args, **kwargs):
        return super(MQBot, self).send_sticker(*args, **kwargs)


if __name__ == '__main__':
    bot = TelegramShoutoutBot()

