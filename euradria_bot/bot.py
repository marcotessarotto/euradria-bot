import os
from datetime import datetime, timedelta
from django.utils import timezone
from more_itertools import take

from telegram import Bot, ReplyKeyboardMarkup, ChatAction
from telegram.error import Unauthorized, BadRequest, TimedOut, NetworkError, ChatMigrated, TelegramError

from telegram.ext import messagequeue as mq, Updater, ConversationHandler, CommandHandler, MessageHandler, Filters, \
    CallbackQueryHandler, run_async

from backoffice.definitions import UI_PRIVACY_COMMAND, UI_START_COMMAND, UI_START_COMMAND_ALT, \
    UI_bot_presentation_message, UI_HELLO, UI_message_read_and_accept_privacy_rules_as_follows, UI_ACCEPT_UC, \
    UI_NOT_ACCEPT_UC, UI_message_you_have_accepted_privacy_rules_on_this_day, DATE_FORMAT_STR, UI_PRIVACY_message, \
    UI_message_error_accepting_privacy_rules, UI_message_thank_you_for_accepting_privacy_rules, \
    UI_message_you_have_not_accepted_privacy_rules_cannot_continue, UI_message_what_is_your_age, UI_message_cheers, \
    UI_message_you_have_provided_your_age, UI_message_what_is_your_educational_level, \
    UI_message_enter_custom_educational_level, UI_message_you_have_provided_your_education_level, UI_HELP_COMMAND, \
    UI_bot_help_message, UI_HELP_COMMAND_ALT, help_keyword_list
from euradria_bot.ormlayer import orm_user_blocks_bot, orm_add_telegram_user, orm_get_telegram_user, \
    orm_change_user_privacy_setting, orm_parse_user_age, EDUCATIONAL_LEVELS, orm_set_telegram_user_educational_level, \
    orm_get_user_expected_input, orm_get_current_user_context, orm_save_ai_log
from euradria_bot.user_utils import check_if_user_is_disabled, standard_user_checks
from .log_utils import main_logger as logger, debug_update, log_user_input, benchmark_decorator

global_bot_instance: Bot = None

CALLBACK_PRIVACY, CALLBACK_AGE, CALLBACK_EDUCATIONAL_LEVEL, CALLBACK_CUSTOM_EDUCATIONAL_LEVEL = range(4)


def send_message_to_log_group(text, disable_notification=False):
    """send bot log message to dedicated chat"""
    if not text or not global_bot_instance:
        return

    try:

        global_bot_instance.send_message(
            chat_id=BOT_LOGS_CHAT_ID,
            text=text,
            disable_notification=disable_notification
        )
    except Exception:
        logger.error("send_message_to_log_group")


def respond_to_user(update, context, telegram_user_id, telegram_user, message_text):
    # generic user utterance
    # orm_store_free_text(message_text, telegram_user)

    res = naive_sentence_similarity_web_client(message_text, '10.4.100.2')

    import json
    nss_result = json.loads(res)

    logger.info(f"*** naive_sentence_similarity_web_client returns {nss_result}")

    suggested_action = nss_result["similarity_ws"][0]
    confidence = nss_result["similarity_ws"][1]

    if suggested_action is None:
        suggested_action = ''

    od = nss_result["similarity_ws"][2]  # dictionary
    n_items = take(6, od.items())  # first n items of dictionary
    content = ''

    first_value = None

    for k, v in n_items:
        ks = format(float(k), '.3f')  # key is confidence
        content += f"{v}=>{ks}\n"
        if not first_value:
            first_value = v

    current_user_context = orm_get_current_user_context(telegram_user.user_id)

    # vacancy_code = get_valid_vacancy_code_from_str(message_text)
    # if vacancy_code:
    #     logger.info(f"respond_to_user: user has specified a valid vacancy code: {vacancy_code}. modify current_user_context")
    #     current_user_context = orm_set_current_user_context(telegram_user.user_id, orm_find_ai_context('VACANCY'), vacancy_code)

    content += f'\ncurrent context: {current_user_context}'

    if telegram_user.is_admin and telegram_user.debug_msgs:
        update.message.reply_text(
            f'AI says: {content}',
            parse_mode='HTML'
        )

    ai_answer = perform_suggested_action(update, context, telegram_user, current_user_context, message_text, nss_result)

    orm_save_ai_log(telegram_user,
                    current_user_context.item if current_user_context is not None and current_user_context.item is not None and type(current_user_context.item) == NewsItem else None,
                    message_text,
                    suggested_action,
                    current_user_context,
                    confidence,
                    first_value[0],
                    ai_answer)


@debug_update
@log_user_input
def start_command_handler(update, context):
    logger.info(f"start args: {context.args}")  # parameter received through start command; max length: 64
    # example:
    # https://telegram.me/DCLavoroFvg_bot?start=12345

    # logger.info("update.message.from_user = " + str(update.message.from_user))

    telegram_user = orm_add_telegram_user(update.message.from_user)

    if check_if_user_is_disabled(telegram_user, update, context):
        return ConversationHandler.END

    bot_presentation = UI_bot_presentation_message

    name = update.message.from_user.first_name
    if not name:
        name = ""

    update.message.reply_text(
        f'{UI_HELLO} {update.message.from_user.first_name}! {bot_presentation}'
    )

    # if check_user_privacy_approval(telegram_user, update, context):
    if not telegram_user.has_accepted_privacy_rules:
        # privacy not yet approved by user
        return privacy_command_handler(update, context)

    return ConversationHandler.END


def privacy_command_handler(update, context):
    """ Ask user to accept privacy rules, if they were not yet accepted """

    telegram_user = orm_get_telegram_user(update.message.from_user.id)
    privacy_state = telegram_user.has_accepted_privacy_rules

    logger.info(f"privacy_command_handler - user id={telegram_user.id} privacy accepted: {privacy_state}")

    if not privacy_state:
        context.bot.send_message(
            chat_id=update.message.chat_id,
            text=UI_message_read_and_accept_privacy_rules_as_follows + UI_PRIVACY_message,
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[[UI_ACCEPT_UC, UI_NOT_ACCEPT_UC]],
                resize_keyboard=True,
                one_time_keyboard=True
            )
        )

        return CALLBACK_PRIVACY

    # https://stackoverflow.com/a/17311079/974287
    update.message.reply_text(
        text=UI_message_you_have_accepted_privacy_rules_on_this_day +
             telegram_user.privacy_acceptance_timestamp.strftime(DATE_FORMAT_STR) + '\n' +
             UI_PRIVACY_message,
        parse_mode='HTML'
    )

    return ConversationHandler.END


def callback_privacy(update, context):
    choice = update.message.text

    if choice == UI_ACCEPT_UC:
        privacy_setting = True
    elif choice == UI_NOT_ACCEPT_UC:
        privacy_setting = False
    else:
        context.bot.send_message(
            chat_id=update.message.chat_id,
            text=UI_message_error_accepting_privacy_rules.format(UI_ACCEPT_UC, UI_NOT_ACCEPT_UC),
            reply_markup=ReplyKeyboardMarkup(
                keyboard=[[UI_ACCEPT_UC, UI_NOT_ACCEPT_UC]],
                resize_keyboard=True,
                one_time_keyboard=True
            )
        )
        return CALLBACK_PRIVACY

    telegram_user_id = update.message.from_user.id
    orm_change_user_privacy_setting(telegram_user_id, privacy_setting)

    if privacy_setting:
        update.message.reply_text(UI_message_thank_you_for_accepting_privacy_rules)

        ask_age(update, context)
        return CALLBACK_AGE
    else:
        update.message.reply_text(UI_message_you_have_not_accepted_privacy_rules_cannot_continue)
        return ConversationHandler.END


def ask_age(update, context):
    """ Ask user to enter the age """

    update.message.reply_text(UI_message_what_is_your_age)
    return


def callback_age(update, context):
    telegram_user = orm_get_telegram_user(update.message.from_user.id)
    age = update.message.text

    age = orm_parse_user_age(telegram_user, age)
    if age >= 80:
        reply_text = UI_message_cheers
    else:
        reply_text = UI_message_you_have_provided_your_age

    update.message.reply_text(reply_text)

    # now ask educational level
    ask_educational_level(update, context)
    return CALLBACK_EDUCATIONAL_LEVEL


def ask_educational_level(update, context):
    """ Ask user to select the educational level """

    keyboard = []

    k_row = []
    for row in EDUCATIONAL_LEVELS:
        if len(k_row) == 2:
            keyboard.append(k_row)
            k_row = []
        k_row.append(row[1])
    if len(k_row) > 0:
        keyboard.append(k_row)

    # print(keyboard)

    context.bot.send_message(
        chat_id=update.message.chat.id,
        text=UI_message_what_is_your_educational_level,
        parse_mode='HTML',
        reply_markup=ReplyKeyboardMarkup(
            keyboard=keyboard,
            resize_keyboard=True,
            one_time_keyboard=True
        )
    )


def callback_education_level(update, context):
    choice = update.message.text

    if choice == EDUCATIONAL_LEVELS[-1][1]:
        update.message.reply_text(UI_message_enter_custom_educational_level)
        return CALLBACK_CUSTOM_EDUCATIONAL_LEVEL

    for line in EDUCATIONAL_LEVELS:
        if line[1] == choice:
            el = line[0]
            break

    telegram_user = orm_get_telegram_user(update.message.from_user.id)

    logger.info(f"callback_education_level:  {choice} {el}")

    update.message.reply_text(
        text=UI_message_you_have_provided_your_education_level.format(choice),
        parse_mode='HTML'
    )
    # update.message.reply_text(UI_message_now_you_can_choose_news_categories)

    orm_set_telegram_user_educational_level(telegram_user, el)
    return ConversationHandler.END


def callback_custom_education_level(update, context):
    """ Read the custom education level """

    choice = EDUCATIONAL_LEVELS[-1][0]
    el = EDUCATIONAL_LEVELS[-1][1]
    telegram_user = orm_get_telegram_user(update.message.from_user.id)

    # Change the models.py and the admin.py modules to register a custom educational level
    custom_education_level = update.message.text

    logger.info(f"callback_education_level:  {choice}")

    update.message.reply_text(UI_message_you_have_provided_your_education_level.format(custom_education_level))
    # update.message.reply_text(UI_message_now_you_can_choose_news_categories)

    orm_set_telegram_user_educational_level(telegram_user, choice)
    return ConversationHandler.END


def fallback_conversation_handler(update, context):
    text = update.message.text
    logger.info(f'fallback_conversation_handler {text}')
    return ConversationHandler.END


# @run_async
@benchmark_decorator
def callback_handler(update, context):
    """process callback data sent by inline_keyboards """

    data = update.callback_query.data.split()
    # I dati inviati dalle callback_query sono organizzati come segue:
    # il primo elemento contiente una stringa identificativa del contesto
    # il secondo elemento (e eventuali successivi) contiene i dati da passare

    keyword = data[0]

    logger.info(f"callback {keyword}")

    # if keyword == 'feedback':  # Callback per i feedback agli articoli
    #     callback_feedback(update, data[1:])
    #
    # elif keyword == 'comment':  # Callback per i commenti agli articoli
    #     callback_comment(update, context, data[1])
    #
    # elif keyword == 'choice':  # Callback per la scelta delle categorie
    #     callback_choice(update, data[1])


@benchmark_decorator
def help_command_handler(update, context):
    """ Show available bot commands"""

    update.message.reply_text(
        UI_bot_help_message,
        # +
        # "\n\n" +
        # help_on_supported_ai_questions(show_random_questions=True),
        disable_web_page_preview=True,
        parse_mode='HTML'
    )


@log_user_input
@standard_user_checks
@run_async
def generic_message_handler(update, context, telegram_user_id, telegram_user):

    try:
        message_text = update.message.text
    except AttributeError:
        try:
            message_text = update.edited_message.text
        except AttributeError:
            print(update)

    logger.info(f"generic_message_handler - message_text = {message_text}")

    expected_input = orm_get_user_expected_input(telegram_user)

    # TODO: check: is expected_input still used?
    if expected_input == 'a':  # expecting age from user
        callback_age(update, context, telegram_user, message_text)
        return

    if message_text.lower() in help_keyword_list or len(message_text) <= 2:

        help_command_handler(update, context)

    else:
        global_bot_instance.send_chat_action(chat_id=telegram_user_id, action=ChatAction.TYPING)

        send_message_to_log_group(
            f"source='generic_message_handler', user={telegram_user_id}, text='{message_text}'",
            disable_notification=True)

        respond_to_user(update, context, telegram_user_id, telegram_user, message_text)


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


def main():
    logger.info("starting euradria bot...")

    from telegram.utils.request import Request

    from pathlib import Path
    token_file = Path('token.txt')

    if not token_file.exists():
        token_file = Path('../../token.txt')

    token = os.environ.get('TOKEN') or open(token_file).read().strip()

    # https://github.com/python-telegram-bot/python-telegram-bot/wiki/Avoiding-flood-limits
    q = mq.MessageQueue(all_burst_limit=29, all_time_limit_ms=1017)  # 5% safety margin in messaging flood limits
    # set connection pool size for bot
    request = Request(con_pool_size=8)
    my_bot = MQBot(token, request=request, mqueue=q)

    global global_bot_instance
    global_bot_instance = my_bot

    updater = Updater(bot=my_bot, use_context=True)
    dp = updater.dispatcher

    # https://github.com/python-telegram-bot/python-telegram-bot/wiki/Exception-Handling
    # ISSUE: error_callback is not called byt dispatcher
    # dp.add_error_handler(error_callback)

    job_queue = updater.job_queue

    now_tz_aware = timezone.now()
    if now_tz_aware.minute == 0:
        minutes = 0
    elif now_tz_aware.minute <= 30:
        minutes = 30-now_tz_aware.minute
    else:
        minutes = 60-now_tz_aware.minute

    td = timedelta(minutes=minutes)

    # logger.info(f"news check period: {NEWS_CHECK_PERIOD} s")
    # job_minute = job_queue.run_repeating(news_dispatcher, interval=NEWS_CHECK_PERIOD, first=td)  # callback_minute

    # send_message_to_log_group(f"bot started! {now_tz_aware}\nnext news check in {td} minutes", disable_notification=True)

    # Handler to start user iteration
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler(UI_PRIVACY_COMMAND, privacy_command_handler),
            CommandHandler(UI_START_COMMAND, start_command_handler),
            CommandHandler(UI_START_COMMAND_ALT, start_command_handler)
        ],
        states={
            CALLBACK_PRIVACY: [MessageHandler(Filters.text, callback_privacy)],
            CALLBACK_AGE: [MessageHandler(Filters.text, callback_age)],
            CALLBACK_EDUCATIONAL_LEVEL: [MessageHandler(Filters.text, callback_education_level)],
            CALLBACK_CUSTOM_EDUCATIONAL_LEVEL: [MessageHandler(Filters.text, callback_custom_education_level)]
        },
        fallbacks=[
            MessageHandler(Filters.all, fallback_conversation_handler)
        ]
    )
    dp.add_handler(conv_handler)

    # Handler to serve categories, feedbacks and comments inline keboards
    dp.add_handler(CallbackQueryHandler(callback_handler))

    # Other handlers
    dp.add_handler(CommandHandler(UI_HELP_COMMAND, help_command_handler))
    if UI_HELP_COMMAND_ALT is not None:
        dp.add_handler(CommandHandler(UI_HELP_COMMAND_ALT, help_command_handler))

    # dp.add_handler(CommandHandler(UI_UNDO_PRIVACY_COMMAND, undo_privacy_command_handler))

    # These are 'standard' commands (add all categories / remove all categories)
    # dp.add_handler(CommandHandler(UI_ALL_CATEGORIES_COMMAND, set_all_categories_command_handler))
    # dp.add_handler(CommandHandler(UI_NO_CATEGORIES_COMMAND, set_no_categories_command_handler))
    #
    # dp.add_handler(CommandHandler(UI_ME_COMMAND, me_command_handler))

    # dp.add_handler(CommandHandler(UI_RESEND_LAST_NEWS_COMMAND, resend_last_processed_news_command_handler))

    # dp.add_handler(CommandHandler(UI_CHOOSE_CATEGORIES_COMMAND, choose_news_categories_command_handler))
    # dp.add_handler(CommandHandler(UI_SHOW_NEWS, show_news_command_handler))
    # dp.add_handler(MessageHandler(Filters.regex('^(/' + UI_SHOW_NEWS + '[\\d]+)$'), show_news_command_handler))
    # dp.add_handler(MessageHandler(Filters.regex('^(/' + UI_READ_NEWS + '[\\d]+)$'), read_news_item_command_handler))

    # dp.add_handler(CommandHandler(UI_CATEGORIES_HELP, help_categories_command_handler))
    #
    # dp.add_handler(CommandHandler(UI_FORCE_SEND_NEWS_COMMAND, force_send_news_command_handler))
    # dp.add_handler(CommandHandler(UI_DEBUG2_COMMAND, debug2_command_handler))
    # dp.add_handler(CommandHandler(UI_DEBUG3_COMMAND, debug3_command_handler))
    # dp.add_handler(CommandHandler(UI_DEBUG4_COMMAND, debug4_command_handler))
    #
    # dp.add_handler(CommandHandler(UI_DEBUG_MSGS_ON, debug_msgs_command_handler))
    # dp.add_handler(CommandHandler(UI_DEBUG_MSGS_OFF, debug_msgs_command_handler))
    #
    # dp.add_handler(CommandHandler(UI_PING_COMMAND, ping_command_handler))
    # dp.add_handler(CommandHandler(UI_SEND_NEWS_COMMAND, admin_send_command_handler))
    # dp.add_handler(CommandHandler(UI_CLEANUP_COMMAND, cleanup_command_handler))
    #
    # dp.add_handler(CommandHandler(UI_STATS_COMMAND, stats_command_handler))
    #
    # dp.add_handler(CommandHandler(UI_AUDIO_ON_COMMAND, audio_on_command_handler))
    # dp.add_handler(CommandHandler(UI_AUDIO_OFF_COMMAND, audio_off_command_handler))
    #
    # dp.add_handler(CommandHandler(UI_SHOW_PROFESSIONAL_CATEGORIES_COMMAND, show_professional_categories_command_handler))
    # dp.add_handler(CommandHandler(UI_SHOW_PROFESSIONAL_PROFILES_COMMAND, show_professional_profiles_command_handler))

    # catch all unknown commands (including custom commands associated to categories)
    dp.add_handler(MessageHandler(Filters.command, custom_command_handler))

    dp.add_handler(MessageHandler(Filters.reply, comment_handler))
    dp.add_handler(MessageHandler(Filters.text, generic_message_handler))

    # start updater
    updater.start_polling()

    # Stop the bot if you have pressed Ctrl + C or the process has received SIGINT, SIGTERM or SIGABRT
    updater.idle()

    logger.info("terminating bot")

    try:
        request.stop()
        q.stop()
        my_bot.__del__()
    except Exception as e:
        logger.error(e)

    # https://stackoverflow.com/a/40525942/974287
    logger.info("before os._exit")
    os._exit(0)


if __name__ == '__main__':
    main()
