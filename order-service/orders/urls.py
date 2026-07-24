from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import OrderViewSet, PayUWebhookView

router = DefaultRouter()
router.register('', OrderViewSet, basename='order')

urlpatterns = [
    path('payu-webhook/', PayUWebhookView.as_view(), name='payu-webhook'),
    path('', include(router.urls)),
]
