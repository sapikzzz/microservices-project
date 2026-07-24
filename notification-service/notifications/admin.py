from django.contrib import admin

from .models import NotificationLog, ProcessedEvent


@admin.register(ProcessedEvent)
class ProcessedEventAdmin(admin.ModelAdmin):
    list_display = ("event_id", "event_type", "processed_at")
    search_fields = ("event_id", "event_type")


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = ("event_type", "recipient_user_id", "recipient_email", "status", "created_at")
    search_fields = ("event_id", "event_type", "recipient_email")
    list_filter = ("event_type", "status")
