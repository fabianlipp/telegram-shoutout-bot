#!/usr/bin/python3
import telegram.bot
from telegram import Update
from telegram.ext import messagequeue as mq
from telegram.ext import Updater, ConversationHandler, CallbackContext
from telegram.ext import CommandHandler
from telegram.ext import MessageHandler, Filters

from telegram_shoutout_bot_conf import BotConf
import db
from senddata import SendData

import logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                     level=logging.INFO)
logger = logging.getLogger(__name__)

# TODO: Log all (admin) queries

CHANNEL, MESSAGE, CONFIRMATION = range(3)


class TelegramShoutoutBot:
    user_database = None  # type: db.UserDatabase
    channel_database = None  # type: db.ChannelDatabase

    def cmd_start(self, update: Update, context: CallbackContext):
        chat = update.effective_chat
        self.user_database.add_user(chat.id, chat.username, chat.first_name, chat.last_name)
        context.bot.send_message(chat_id=chat.id, text="I'm a bot, please talk to me!")

    # TODO: DEBUG ONLY
    def cmd_echo(self, update: Update, context: CallbackContext):
        context.bot.send_message(chat_id=update.effective_chat.id, text=update.message.text)

    def cmd_admin(self, update: Update, context: CallbackContext):
        user = self.user_database.get_by_chat_id(update.effective_chat.id)
        if user.is_admin:
            answer = "Du bist Admin."
        else:
            answer = "Du bist derzeit kein Admin. Wende dich mit deiner Chat ID {0} ans Webteam.".format(update.effective_chat.id)
        context.bot.send_message(chat_id=update.effective_chat.id, text=answer)

    # Starting here: Functions for conv_send_handler
    def cmd_send(self, update: Update, context: CallbackContext):
        answer = "Kanal eingeben, an den die Nachricht gesendet werden soll.\nVerfügbare Kanäle:"
        context.bot.send_message(chat_id=update.effective_chat.id, text=answer)
        answer = ""
        for channelId, channel in self.channel_database.channels.items():
            answer += "{0} - {1}\n".format(channel.name, channel.description)
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
        send_data.messages.append(update.message)
        answer = "Weitere Nachrichten anfügen, abschließen mit /done oder Abbrechen mit /cancel."
        context.bot.send_message(chat_id=update.effective_chat.id, text=answer)
        # no return statement (stay in same state)

    def answer_done(self, update: Update, context: CallbackContext):
        send_data = context.user_data["send"]  # type: SendData
        answer = "Diese Daten sind gespeichert:"
        context.bot.send_message(chat_id=update.effective_chat.id, text=answer)
        answer = "Kanalname: {0}".format(send_data.channel)
        context.bot.send_message(chat_id=update.effective_chat.id, text=answer)
        # TODO Muss hier die verschiedenen Nachrichten-Typen unterscheiden (Bilder usw.)
        #  Ggf. auch schon beim Speichern der Nachrichten in answer_message beachten
        #  https://github.com/91DarioDev/ForwardsCoverBot
        for message in send_data.messages:
            context.bot.send_message(chat_id=update.effective_chat.id, text=message.text)
        answer = "Versand bestätigen mit /confirm oder Abbrechen mit /cancel."
        context.bot.send_message(chat_id=update.effective_chat.id, text=answer)
        return CONFIRMATION

    def answer_confirm(self, update: Update, context: CallbackContext):
        send_data = context.user_data["send"]  # type: SendData
        for user in self.user_database.users.values():
            # TODO: Check if user is member of channel
            for message in send_data.messages:
                context.bot.send_message(chat_id=user.chat_id, text=message.text)
        return ConversationHandler.END

    def answer_await_confirm(self, update: Update, context: CallbackContext):
        answer = "Versand bestätigen mit /confirm oder Abbrechen mit /cancel."
        context.bot.send_message(chat_id=update.effective_chat.id, text=answer)
        # no return statement (stay in same state)

    def cancel_send(self, update: Update, context: CallbackContext):
        context.user_data["send"] = None
        context.bot.send_message(chat_id=update.effective_chat.id, text="Nachrichtenversand abgebrochen.")
        return ConversationHandler.END

    def error(self, update: Update, context: CallbackContext):
        """Log Errors caused by Updates."""
        logger.warning('Update "%s" caused error "%s"', update, context.error)

    def __init__(self):
        from telegram.utils.request import Request

        my_database = db.MyDatabase(BotConf.database_file)
        self.user_database = db.UserDatabase(my_database)
        self.channel_database = db.ChannelDatabase(my_database)

        # recommended values for production: 29/1017
        q = mq.MessageQueue(all_burst_limit=3, all_time_limit_ms=3000)
        # set connection pool size for bot
        request = Request(con_pool_size=8)
        bot = MQBot(token=BotConf.bot_token, request=request, mqueue=q)
        updater = telegram.ext.updater.Updater(bot=bot, use_context=True)
        dispatcher = updater.dispatcher

        start_handler = CommandHandler('start', self.cmd_start)
        dispatcher.add_handler(start_handler)
        # TODO: Add a stop command to forget everything about a user (delete all data)
        admin_handler = CommandHandler('admin', self.cmd_admin)
        dispatcher.add_handler(admin_handler)

        conv_send_handler = ConversationHandler(
            entry_points=[CommandHandler('send', self.cmd_send)],
            states={
                CHANNEL: [MessageHandler(Filters.text, self.answer_channel)],
                MESSAGE: [CommandHandler('done', self.answer_done),
                          CommandHandler('cancel', self.cancel_send),
                          MessageHandler(Filters.all, self.answer_message)],
                CONFIRMATION: [CommandHandler('confirm', self.answer_confirm),
                               CommandHandler('cancel', self.cancel_send),
                               MessageHandler(Filters.all, self.answer_await_confirm)]
            },
            fallbacks=[CommandHandler('cancel', self.cancel_send)]
        )
        dispatcher.add_handler(conv_send_handler)

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


if __name__ == '__main__':
    bot = TelegramShoutoutBot()

