





def orm_user_blocks_bot(chat_id):

    logger.info(f"orm_user_blocks_bot: user {chat_id}")

    telegram_user = orm_get_telegram_user(chat_id)

    if not telegram_user:
        logger.info(f"orm_user_blocks_bot: telegram_user not found!")
        return

    telegram_user.has_user_blocked_bot = True
    telegram_user.when_user_blocked_bot_timestamp = now()
    orm_update_telegram_user(telegram_user)

