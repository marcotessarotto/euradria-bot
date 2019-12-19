import csv

from django.contrib import admin
from django.forms import (
    CheckboxSelectMultiple,
    TextInput
)
from django.db import models
from django.http import HttpResponse

from backoffice.models import *


admin.site.site_header = 'backoffice EuradriaBot'


# https://books.agiliq.com/projects/django-admin-cookbook/en/latest/export.html
class ExportCsvMixin:
    def export_as_csv(self, request, queryset):

        meta = self.model._meta
        field_names = [field.name for field in meta.fields]

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename={}.csv'.format(meta)
        writer = csv.writer(response)

        writer.writerow(field_names)
        for obj in queryset:
            row = writer.writerow([getattr(obj, field) for field in field_names])

        return response

    export_as_csv.short_description = "Export Selected"



@admin.register(AiQAActivityLog)
class AiQAActivityLogAdmin(admin.ModelAdmin):
    list_display = ('id', 'telegram_user', 'user_question', 'naive_sentence_similarity_action', 'naive_sentence_similarity_confidence', 'context')
    ordering = ('-id',)

    formfield_overrides = {
        # https://stackoverflow.com/questions/910169/resize-fields-in-django-admin
        models.CharField: {'widget': TextInput(attrs={'size': '80'})},
        #        models.TextField: {'widget': Textarea(attrs={'rows':4, 'cols':40})},

    }


@admin.register(NaiveSentenceSimilarityDb)
class NaiveSentenceSimilarityDbAdmin(admin.ModelAdmin, ExportCsvMixin):
    list_display = ('id', 'reference_sentence', 'action', 'context', 'enabled', )
    ordering = ('-id', 'reference_sentence', 'action', 'context')
    search_fields = ('reference_sentence', 'action__action', 'context__context')
    actions = ["export_as_csv"]
    # TODO: add import csv command
    # https://books.agiliq.com/projects/django-admin-cookbook/en/latest/import.html

    formfield_overrides = {
        # https://stackoverflow.com/questions/910169/resize-fields-in-django-admin
        models.CharField: {'widget': TextInput(attrs={'size': '80'})},
        #        models.TextField: {'widget': Textarea(attrs={'rows':4, 'cols':40})},

    }


admin.site.register(AiContext)


@admin.register(AiAction)
class AiActionAdmin(admin.ModelAdmin, ExportCsvMixin):
    list_display = ('id', 'action',)
    actions = ["export_as_csv"]
    ordering = ('-id', 'action')

    formfield_overrides = {
        # https://stackoverflow.com/questions/910169/resize-fields-in-django-admin
        models.CharField: {'widget': TextInput(attrs={'size': '80'})},
        #        models.TextField: {'widget': Textarea(attrs={'rows':4, 'cols':40})},

    }


@admin.register(TelegramUser)
class TelegramUserAdmin(admin.ModelAdmin, ExportCsvMixin):
    list_display = ('username', 'first_name', 'last_name', 'user_id', 'is_admin', 'has_accepted_privacy_rules')
    ordering = ('id',)
    list_filter = ('has_accepted_privacy_rules', )
    search_fields = ('username', 'first_name', 'last_name', 'user_id')
    actions = ["export_as_csv"]

    formfield_overrides = {
        models.ManyToManyField: {'widget': CheckboxSelectMultiple},

        # https://stackoverflow.com/questions/910169/resize-fields-in-django-admin
        models.CharField: {'widget': TextInput(attrs={'size': '80'})},
        #        models.TextField: {'widget': Textarea(attrs={'rows':4, 'cols':40})},

    }


