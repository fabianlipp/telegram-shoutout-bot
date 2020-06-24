from abc import ABC, abstractmethod

from telegram import Message, Bot, ParseMode

# The following case distinction is similar to the one in
# https://github.com/91DarioDev/forwardscoverbot/blob/master/forwardscoverbot/messages.py


class MyMessage(ABC):
    @staticmethod
    def get_mymessage_object(message: Message):
        if message.text:
            return TextMessage(message)
        elif message.photo:
            return PhotoMessage(message)
        elif message.sticker:
            return StickerMessage(message)
        elif message.video:
            return VideoMessage(message)
        # TODO: other possibilities (cf. resend_message)
        # Not handled so far: voice, document, audio, contact, venue, location, video_note, game

    @abstractmethod
    def send(self, chat_id, bot: Bot):
        pass


class TextMessage(MyMessage):
    def __init__(self, message: Message):
        self.text = message.text_html

    def send(self, chat_id, bot: Bot):
        bot.send_message(
            chat_id=chat_id,
            text=self.text,
            parse_mode=ParseMode.HTML
        )


class PhotoMessage(MyMessage):
    def __init__(self, message: Message):
        self.photo = message.photo[-1].file_id
        self.caption = message.caption

    def send(self, chat_id, bot: Bot):
        bot.send_message(
            chat_id=chat_id,
            photo=self.photo,
            caption=self.caption,
            parse_mode=ParseMode.HTML
        )


class StickerMessage(MyMessage):
    def __init__(self, message: Message):
        self.sticker = message.sticker.file_id

    def send(self, chat_id, bot: Bot):
        bot.send_message(
            chat_id=chat_id,
            sticker=self.sticker
        )


class VideoMessage(MyMessage):
    def __init__(self, message: Message):
        self.video = message.video.file_id
        self.duration = message.video.duration
        self.caption = message.caption

    def send(self, chat_id, bot: Bot):
        bot.send_message(
            chat_id=chat_id,
            video=self.video,
            duration=self.duration,
            caption=self.caption,
            parse_mode=ParseMode.HTML
        )
