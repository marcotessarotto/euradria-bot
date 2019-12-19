from datetime import datetime

from telegram import Bot
from telegram.error import Unauthorized, BadRequest, TimedOut, NetworkError, ChatMigrated, TelegramError

from .log_utils import main_logger as logger


class MQBot(Bot):
    """A subclass of Bot which delegates send method handling to MQ"""

    def __init__(self, *args, is_queued_def=True, mqueue=None, **kwargs):
        super(MQBot, self).__init__(*args, **kwargs)
        # below 2 attributes should be provided for decorator usage
        self._is_messages_queued_default = is_queued_def
        self._msg_queue = mqueue or mq.MessageQueue()

    def __del__(self):
        try:
            logger.info("MQBot - __del__")
            self._msg_queue.stop()
        except Exception as error:
            logger.error(f"error in MQBot.__del__ : {error}")
            pass

    @mq.queuedmessage
    def send_message(self, chat_id, *args, **kwargs):
        """Wrapped method would accept new `queued` and `isgroup`
        OPTIONAL arguments"""

        e = None
        try:
            return super(MQBot, self).send_message(chat_id, *args, **kwargs)
        except Unauthorized as error:
            # remove chat_id from conversation list
            orm_user_blocks_bot(chat_id)
            e = error
        except BadRequest as error:
            # handle malformed requests - read more below!
            logger.error("BadRequest")
            e = error
        except TimedOut as error:
            # handle slow connection problems
            logger.error("TimedOut")
            e = error
        except NetworkError as error:
            # handle other connection problems
            logger.error("NetworkError")
            e = error
        except ChatMigrated as error:
            # the chat_id of a group has changed, use e.new_chat_id instead
            logger.error("ChatMigrated")
            e = error
        except TelegramError as error:
            # handle all other telegram related errors
            logger.error("TelegramError")
            e = error

        if e:
            now = datetime.datetime.now()
            # send_message_to_log_group(f"bot exception\n{now}\n{error}")

            raise e

