from django.contrib import admin

from .models import StripeEvent, Subscription


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("household", "status", "trial_ends_at", "paid_at")
    readonly_fields = ("created_at",)


@admin.register(StripeEvent)
class StripeEventAdmin(admin.ModelAdmin):
    list_display = ("type", "event_id", "received_at", "processed_at")
    readonly_fields = ("event_id", "type", "payload", "received_at", "processed_at")
