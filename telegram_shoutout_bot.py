#!/usr/bin/python3
from telegram import Update
from telegram.ext import Updater, ConversationHandler, CallbackContext
from telegram.ext import CommandHandler
from telegram.ext import MessageHandler, Filters

from telegram_shoutout_bot_conf import BotConf
import db

import logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                     level=logging.INFO)
logger = logging.getLogger(__name__)

# TODO: Log all queries

CHANNEL, MESSAGE, CONFIRMATION = range(3)


class TelegramShoutoutBot:
    user_database = None  # type: db.UserDatabase
    channel_database = None  # type: db.ChannelDatabase

    def cmd_start(self, update: Update, context: CallbackContext):
        chat = update.effective_chat
        self.user_database.add_user(chat.id, chat.username, chat.first_name, chat.last_name)
        context.bot.send_message(chat_id=chat.id, text="I'm a bot, please talk to me!")

    def cmd_echo(self, update: Update, context: CallbackContext):
        # TODO: DEBUG ONLY
        context.bot.send_message(chat_id=update.effective_chat.id, text=update.message.text)

    def cmd_admin(self, update: Update, context: CallbackContext):
        user = self.user_database.get_by_chat_id(update.effective_chat.id)
        if user.is_admin:
            answer = "Du bist Admin."
        else:
            answer = "Du bist derzeit kein Admin. Wende dich mit deiner Chat ID {0} ans Webteam.".format(update.effective_chat.id)
        context.bot.send_message(chat_id=update.effective_chat.id, text=answer)

    def cmd_send(self, update: Update, context: CallbackContext):
        answer = "Kanal eingeben, an den die Nachricht gesendet werden soll.\nVerfügbare Kanäle:"
        context.bot.send_message(chat_id=update.effective_chat.id, text=answer)
        answer = ""
        for channelId, channel in self.channel_database.channels.items():
            answer += "{0} - {1}\n".format(channel.name, channel.description)
        context.bot.send_message(chat_id=update.effective_chat.id, text=answer)
        return CHANNEL

    def answer_channel(self, update: Update, context: CallbackContext):
        # TODO Validate Answer
        context.user_data["send"] = {}
        context.user_data["send"]["channel"] = update.message.text
        answer = "Nachricht eingeben, die gesendet werden soll."
        context.bot.send_message(chat_id=update.effective_chat.id, text=answer)
        return MESSAGE

    def answer_message(self, update: Update, context: CallbackContext):
        # TODO Store answer
        context.user_data["send"]["message"] = update.message
        # TODO: Möglichkeit mehrere Nachrichten einzugeben (im Moment wird immer nur die letzte gespeichert)
        answer = "Weitere Nachrichten anfügen, abschließen mit /done oder Abbrechen mit /cancel."
        context.bot.send_message(chat_id=update.effective_chat.id, text=answer)
        #return CONFIRMATION # Stay in same state

    def answer_done(self, update: Update, context: CallbackContext):
        answer = "Diese Daten waren gespeichert:"
        context.bot.send_message(chat_id=update.effective_chat.id, text=answer)
        answer = "Kanalname: {0}".format(context.user_data["send"]["channel"])
        context.bot.send_message(chat_id=update.effective_chat.id, text=answer)
        # TODO Muss hier die verschiedenen Nachrichten-Typen unterscheiden (Bilder usw.)
        #  https://github.com/91DarioDev/ForwardsCoverBot
        message = context.user_data["send"]["message"]
        context.bot.send_message(chat_id=update.effective_chat.id, text=message.text)
        message = "Versand bestätigen mit /confirm oder Abbrechen mit /cancel."
        context.bot.send_message(chat_id=update.effective_chat.id, text=message.text)
        return CONFIRMATION

    def answer_confirm(self, update: Update, context: CallbackContext):
        # TODO: Prüfe, dass tatsächlich /confirm eingegeben wurde (oder nutze CommandHandler stattdessen)
        # TODO: Nachricht an alle versenden
        return ConversationHandler.END

    def cancel_send(self, update: Update, context: CallbackContext):
        # TODO
        context.bot.send_message(chat_id=update.effective_chat.id, text="Received cancel")
        pass

    def error(self, update: Update, context: CallbackContext):
        """Log Errors caused by Updates."""
        logger.warning('Update "%s" caused error "%s"', update, context.error)

    def __init__(self):
        my_database = db.MyDatabase(BotConf.database_file)
        self.user_database = db.UserDatabase(my_database)
        self.channel_database = db.ChannelDatabase(my_database)

        updater = Updater(token=BotConf.bot_token, use_context=True)
        dispatcher = updater.dispatcher

        start_handler = CommandHandler('start', self.cmd_start)
        dispatcher.add_handler(start_handler)
        admin_handler = CommandHandler('admin', self.cmd_admin)
        dispatcher.add_handler(admin_handler)

        conv_send_handler = ConversationHandler(
            entry_points=[CommandHandler('send', self.cmd_send)],
            states={
                CHANNEL: [MessageHandler(Filters.text, self.answer_channel)],
                MESSAGE: [CommandHandler('done', self.answer_done),
                          MessageHandler(Filters.all, self.answer_message)],
                CONFIRMATION: [MessageHandler(Filters.text, self.answer_confirm)]
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


if __name__ == '__main__':
    bot = TelegramShoutoutBot()

