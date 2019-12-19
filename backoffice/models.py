from django.db import models

from backoffice.definitions import UI_telegram_user, UI_telegram_users

APP_LABEL = "backoffice"  # DO NOT MODIFY; necessary to telegram bot for import of django models

EDUCATIONAL_LEVELS = (
    ('-', 'non dichiarato'),
    ('0', 'nessun titolo di studio'),
    ('a', 'scuola elementare'),
    ('b', 'scuola media'),
    ('c', 'scuola superiore'),
    ('d', 'corsi pre-universitari/brevi corsi professionali'),
    ('e', 'laurea/laurea magistrale'),
    ('f', 'dottorato di ricerca'),
    ('g', 'altro')
)


class AiQAActivityLog(models.Model):
    """log of activity by AI on question/answers with users"""

    telegram_user = models.ForeignKey('TelegramUser', on_delete=models.CASCADE)
    # news_item = models.ForeignKey('NewsItem', blank=True, null=True, on_delete=models.CASCADE) # optional
    job_offer_id = models.CharField(max_length=256, blank=True, null=True)
    event_id = models.CharField(max_length=256, blank=True, null=True)

    user_question = models.CharField(max_length=1024)

    naive_sentence_similarity_action = models.ForeignKey('AiAction', on_delete=models.PROTECT,  blank=True, null=True, related_name='naive_action') # models.CharField(max_length=1024, verbose_name="AI action")
    naive_sentence_similarity_confidence = models.FloatField(default=0, verbose_name="AI confidence")
    naive_most_similar_sentence = models.CharField(max_length=1024)
    ai_answer = models.CharField(max_length=1024, default="", blank=True, null=True,)

    context = models.ForeignKey('AiContext', on_delete=models.PROTECT, blank=True, null=True)

    supervisor_evaluation = models.FloatField(default=-1, verbose_name="supervisore - valutazione")

    supervisor_suggested_action = models.ForeignKey('AiAction', on_delete=models.PROTECT,  blank=True, null=True, related_name='sup_action')

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "AI - log QA con utente"
        verbose_name_plural = "AI - log attività QA con utenti"
        app_label = APP_LABEL


class AiContext(models.Model):
    context = models.CharField(max_length=1024)
    description = models.CharField(max_length=1024, blank=True, default="")

    class Meta:
        verbose_name = "AI - Context"
        # verbose_name_plural = "AI - "
        app_label = APP_LABEL

    def __str__(self):
        if self.description:
            return f"{self.id} - {self.context} ({self.description})"
        else:
            return f"{self.id} - {self.context} "


class AiAction(models.Model):
    action = models.CharField(max_length=1024)
    description = models.CharField(max_length=1024, blank=True, default="")

    class Meta:
        verbose_name = "AI - Action"
        # verbose_name_plural = "AI - "
        app_label = APP_LABEL

    def __str__(self):
        if self.description:
            return f"{self.id} - {self.action} ({self.description})"
        else:
            return f"{self.id} - {self.action} "


class NaiveSentenceSimilarityDb(models.Model):
    reference_sentence = models.CharField(max_length=1024)
    action = models.ForeignKey('AiAction', on_delete=models.PROTECT,  blank=True, null=True)
    context = models.ForeignKey('AiContext', on_delete=models.PROTECT,  blank=True, null=True)
    multiplier = models.FloatField(default=1, verbose_name="moltiplicatore (per naive s.s.)")

    enabled = models.BooleanField(default=True)

    lang = models.CharField(max_length=4, default="it")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "AI - Naive Sentence Similarity Db"
        # verbose_name_plural = "AI - "
        app_label = APP_LABEL


class TelegramUser(models.Model):
    user_id = models.BigIntegerField(
        verbose_name="telegram user id")  # Telegram used id (information provided by Telegram)

    age = models.IntegerField(default=-1, verbose_name="età")

    educational_level = models.CharField(max_length=1, choices=EDUCATIONAL_LEVELS, default='-',
                                         verbose_name="titolo di studio più elevato")

    chat_state = models.CharField(max_length=1, default='-', blank=True, editable=False)

    regionefvg_id = models.BigIntegerField(default=-1, verbose_name="internal use", editable=False)  # for internal use

    has_accepted_privacy_rules = models.BooleanField(default=False, verbose_name="ha accettato il regolamento privacy?")
    # L : through a parameter passed to /start
    # U : user has accepted privacy rules through bot UI
    privacy_acceptance_mechanism = models.CharField(max_length=1, blank=True, null=True, editable=False,
                                                    verbose_name="meccanismo di accettazione privacy (U: tramite il bot)")
    privacy_acceptance_timestamp = models.DateTimeField(blank=True, null=True)

    username = models.CharField(max_length=32, blank=True, null=True)  # information provided by Telegram

    first_name = models.CharField(max_length=50, blank=True, null=True, verbose_name="Nome")
    last_name = models.CharField(max_length=50, blank=True, null=True, verbose_name="Cognome")

    is_bot = models.BooleanField(default=False, verbose_name="è un bot?")  # information provided by Telegram

    language_code = models.CharField(max_length=2, blank=True, null=True)  # information provided by Telegram

    # categories = models.ManyToManyField(Category, blank=True, verbose_name="categorie")

    number_of_received_news_items = models.BigIntegerField(default=0, verbose_name="numero di news ricevute")

    is_text_to_speech_enabled = models.BooleanField(default=False, verbose_name='text to speech abilitato?')

    def categories_str(self):
        result = ''
        for cat in self.categories.all().order_by('key'):
            if cat.emoji is not None:
                result += '- ' + cat.name + '  ' + cat.emoji + '\n'
            else:
                result += '- ' + cat.name + '\n'
        return result

    enabled = models.BooleanField(default=True,
                                  verbose_name="utente abilitato all'uso del bot")  # user can be disabled by bot admins

    # when loading TelegramUser, use defer()
    # https://docs.djangoproject.com/en/2.2/ref/models/querysets/#defer
    # news_item_sent_to_user = models.ManyToManyField(NewsItemSentToUser, blank=True)

    is_admin = models.BooleanField(default=False, verbose_name="amministratore del bot")  # is bot admin?

    email = models.CharField(max_length=256, blank=True, null=True)

    has_user_blocked_bot = models.BooleanField(default=False, verbose_name="l'utente ha bloccato il bot?")
    when_user_blocked_bot_timestamp = models.DateTimeField(blank=True, null=True, verbose_name="quando l'utente ha bloccato il bot")

    debug_msgs = models.BooleanField(default=False, verbose_name="riceve messaggi di debug?")  # only for admins

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def educational_level_verbose(self):
        return dict(EDUCATIONAL_LEVELS)[self.educational_level]

    class Meta:
        verbose_name = UI_telegram_user
        verbose_name_plural = UI_telegram_users
        app_label = APP_LABEL

    def __str__(self):
        return 'user ' + str(self.user_id) + ' (' + \
               str(self.first_name) + ' ' + str(self.last_name) + ')'


