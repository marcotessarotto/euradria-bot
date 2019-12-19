import threading
from datetime import datetime, timedelta

from euradria_bot.log_utils import orm_logger as logger, benchmark_decorator

from django.core.cache import cache
from django.utils.timezone import now

from backoffice.models import *


# https://docs.djangoproject.com/en/2.2/topics/cache/#the-low-level-cache-api
use_cache = True


def _update_user_in_cache(telegram_user):
    if use_cache:
        key_name = "user" + str(telegram_user.user_id)
        cache.set(key_name, telegram_user, timeout=60)


def orm_get_obj_from_cache(obj_name: str):
    """get generic object from django cache"""

    cache_key = "cacheobj" + obj_name

    result = cache.get(cache_key)

    return result


def orm_set_obj_in_cache(obj_name: str, obj_instance, timeout=60*60*12):
    """store object in django cache, default duration is 12 hours"""
    cache_key = "cacheobj" + obj_name

    cache.set(cache_key, obj_instance, timeout=timeout)


@benchmark_decorator
def orm_get_telegram_user(telegram_user_id) -> TelegramUser:
    """ Restituisce l'oggetto user associato a un determinato utente; istanza di tipo TelegramUser
    :rtype: TelegramUser
    """

    def _orm_get_telegram_user():

        queryset_user = TelegramUser.objects.filter(user_id=telegram_user_id)

        if len(queryset_user) == 0:
            res = None
        else:
            res = queryset_user[0]

        return res

    def _orm_get_telegram_user_cache():

        key_name = f"user{telegram_user_id}"

        res = cache.get(key_name)

        if res is None:
            res = _orm_get_telegram_user()
            cache.set(key_name, res, timeout=60)

        return res

    if use_cache:
        result = _orm_get_telegram_user_cache()
    else:
        result = _orm_get_telegram_user()

    # if result is None:
    #     result = orm_add_telegram_user(...)
    #     _update_user_in_cache(result)

    return result


def orm_update_telegram_user(telegram_user: TelegramUser):
    logger.debug(f"orm_update_telegram_user {telegram_user.user_id}")
    if telegram_user is not None:
        telegram_user.save()
        _update_user_in_cache(telegram_user)


def orm_user_blocks_bot(chat_id):

    logger.info(f"orm_user_blocks_bot: user {chat_id}")

    telegram_user = orm_get_telegram_user(chat_id)

    if not telegram_user:
        logger.info(f"orm_user_blocks_bot: telegram_user not found!")
        return

    telegram_user.has_user_blocked_bot = True
    telegram_user.when_user_blocked_bot_timestamp = now()
    orm_update_telegram_user(telegram_user)


def orm_add_telegram_log_group(telegram_user_id):
    new_telegram_user = TelegramUser()
    new_telegram_user.user_id = telegram_user_id
    new_telegram_user.username = "BOT LOGS - private group"
    new_telegram_user.has_accepted_privacy_rules = True
    new_telegram_user.save()
    return new_telegram_user


def orm_add_telegram_user(user):
    """ creates a new user, if not existing; returns instance of user """

    telegram_user = orm_get_telegram_user(user.id)

    if telegram_user is None:  # telegram user has not been registered yet
        new_telegram_user = TelegramUser()
        new_telegram_user.user_id = user.id
        new_telegram_user.username = user.username
        new_telegram_user.first_name = user.first_name
        new_telegram_user.last_name = user.last_name
        new_telegram_user.language_code = user.language_code
        new_telegram_user.save()

        # # new users: should they have all news categories selected? or none?
        # if orm_get_system_parameter(CREATE_USER_WITH_ALL_CATEGORIES_SELECTED) == "True":
        #     # (select all news categories)
        #     for k in Category.objects.all():
        #         new_telegram_user.categories.add(k)

        new_telegram_user.save()

        _update_user_in_cache(new_telegram_user)
        logger.info(f"orm_add_telegram_user: new user {new_telegram_user.user_id}")

        return new_telegram_user
    else:
        logger.info(f"orm_add_telegram_user: existing user {telegram_user.user_id}")

        telegram_user.has_user_blocked_bot = False

        telegram_user.save()

        _update_user_in_cache(telegram_user)

        return telegram_user


def orm_change_user_privacy_setting(telegram_user_id, privacy_setting):
    telegram_user = orm_get_telegram_user(telegram_user_id)

    telegram_user.has_accepted_privacy_rules = privacy_setting
    telegram_user.privacy_acceptance_mechanism = 'U'

    if privacy_setting:
        telegram_user.privacy_acceptance_timestamp = now()
    else:
        telegram_user.privacy_acceptance_timestamp = None

    telegram_user.save()

    _update_user_in_cache(telegram_user)


def orm_parse_user_age(telegram_user: TelegramUser, message_text: str):
    """parse age from text sent by user; returns age, -1 for value error"""
    try:
        age = int(message_text)

        if age < 0:
            age = -1
    except ValueError:
        logger.error(f"wrong format for age! {message_text}")
        age = -1

    telegram_user.age = age
    telegram_user.save()
    _update_user_in_cache(telegram_user)
    logger.info(f"parse_user_age: age set for user {telegram_user.user_id} to {age}")

    return age


def orm_set_telegram_user_educational_level(telegram_user: TelegramUser, choice: str):

    telegram_user.educational_level = choice
    telegram_user.save()
    _update_user_in_cache(telegram_user)


def orm_get_user_expected_input(obj) -> str:
    """returns user's next expected input and resets it to 'no input expected'"""
    if obj is None:
        return None

    if hasattr(obj, '__dict__'):
        telegram_user = obj
    else:
        telegram_user = orm_get_telegram_user(obj)

    if telegram_user is not None:
        res = telegram_user.chat_state
        telegram_user.chat_state = '-'
        telegram_user.save()
        _update_user_in_cache(telegram_user)
    else:
        res = None

    logger.info(f"orm_get_user_expected_input({obj}): {res}")

    return res


# def orm_store_free_text(message_text, telegram_user):
#     user_free_text = UserFreeText()
#     user_free_text.text = message_text[:1024]
#     user_free_text.telegram_user = telegram_user
#     user_free_text.save()



def orm_find_ai_action(action: str):
    queryset = AiAction.objects.filter(action=action)

    if len(queryset) == 0:
        return None

    return queryset[0]


def orm_find_ai_context(context: str):
    queryset = AiContext.objects.filter(context=context)

    if len(queryset) == 0:
        return None

    return queryset[0]


def orm_reload_nss_reference_sentences():
    queryset = NaiveSentenceSimilarityDb.objects.filter(enabled=True)

    return queryset


def orm_get_all_sentences(action: str):

    ai_action = orm_find_ai_action(action)

    if not ai_action:
        return None

    queryset = NaiveSentenceSimilarityDb.objects.filter(action=ai_action).filter(enabled=True)

    result = []

    for item in queryset:
        result.append(item.reference_sentence)

    return result


nss_mutex = threading.Lock()


def orm_get_nss_reference_sentences():
    key_name = "nss_ref_sen"
    result = orm_get_obj_from_cache(key_name)

    if result is None or len(result) == 0:

        with nss_mutex:

            if result is None or len(result) == 0:
                result = orm_reload_nss_reference_sentences()
                orm_set_obj_in_cache(key_name, result, 60 * 1)

    return result


class CurrentUserContext(object):
    def __init__(self):
        self.current_ai_context = None  # AiContext
        self.item = None  # NewsItem or other types
        self.timestamp = datetime.now()

    def __str__(self):
        try:
            item_str = self.item.id if self.item is not None else None
        except AttributeError:
            item_str = self.item

        return f"CurrentUserContext: context='{self.current_ai_context}' item id={item_str} timestamp={self.timestamp}"
    pass


def orm_save_ai_log(telegram_user, news_item, message_text, suggested_action, current_user_context: CurrentUserContext, confidence, most_similar_sentence, ai_answer):
    ai_log = AiQAActivityLog()
    ai_log.telegram_user = telegram_user
    ai_log.news_item = news_item
    ai_log.user_question = message_text  # original text provided by user

    ai_log.naive_sentence_similarity_action = orm_find_ai_action(suggested_action)  # as suggested by naive s.s.
    ai_log.naive_sentence_similarity_confidence = confidence  # as suggested by naive s.s.
    ai_log.naive_most_similar_sentence = most_similar_sentence  # as suggested by naive s.s.

    ai_log.context = current_user_context.current_ai_context if current_user_context else None

    ai_log.ai_answer = ai_answer

    ai_log.save()


# _current_context_users = {}


def orm_set_current_user_context(telegram_user_id: int, current_ai_context: AiContext, item):
    # global _current_context_users

    obj = CurrentUserContext()
    obj.current_ai_context = current_ai_context
    obj.item = item

    # _current_context_users[telegram_user_id] = obj
    orm_set_obj_in_cache(f"_current_context_users_{telegram_user_id}", obj, 60*15)

    return obj


def orm_get_current_user_context(telegram_user_id: int) -> CurrentUserContext:
    # global _current_context_users

    obj = orm_get_obj_from_cache(f"_current_context_users_{telegram_user_id}")

    if obj:
        d = datetime.now() - timedelta(minutes=15)  # user context lasts 15 minutes

        if obj.timestamp < d:
            return None
        else:
            return obj

    return obj

