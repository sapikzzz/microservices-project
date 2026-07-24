from django.db import models


class ProcessedEvent(models.Model):
    event_id = models.CharField(max_length=100, unique=True)
    event_type = models.CharField(max_length=100)
    processed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-processed_at"]

    def __str__(self):
        return f"{self.event_type}:{self.event_id}"


class NotificationLog(models.Model):
    event_id = models.CharField(max_length=100)
    event_type = models.CharField(max_length=100)
    recipient_user_id = models.IntegerField()
    recipient_email = models.EmailField(blank=True)
    subject = models.CharField(max_length=255)
    status = models.CharField(max_length=30)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.event_type} -> {self.recipient_email or self.recipient_user_id}"
