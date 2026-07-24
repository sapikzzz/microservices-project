from django.urls import path
from . import views

app_name = 'deliveries'

urlpatterns = [
    # Collection
    path('deliveries/', views.DeliveryListCreateView.as_view(), name='list-create'),

    # Single delivery — detail
    path('deliveries/<str:order_id>/', views.DeliveryDetailView.as_view(), name='detail'),

    # Update client location (allowed at any active status)
    path('deliveries/<str:order_id>/client-location/', views.UpdateClientLocationView.as_view(), name='client-location'),

    # Lifecycle transitions
    path('deliveries/<str:order_id>/pickup/', views.DeliveryPickupView.as_view(), name='pickup'),
    path('deliveries/<str:order_id>/dropoff/', views.DeliveryDropoffView.as_view(), name='dropoff'),
    path('deliveries/<str:order_id>/complete/', views.DeliveryCompleteView.as_view(), name='complete'),
    path('deliveries/<str:order_id>/cancel/', views.DeliveryCancelView.as_view(), name='cancel'),

    # Route data
    path('deliveries/<str:order_id>/route/', views.DeliveryRouteView.as_view(), name='route'),
]
