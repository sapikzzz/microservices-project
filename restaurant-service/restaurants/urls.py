from django.conf import settings
from django.urls import path

from restaurants.views import admin_views, internal_views, menu_views, order_views, restaurant_views

urlpatterns = [
    # Public
    path("restaurants/", restaurant_views.RestaurantListView.as_view(), name="restaurant-list"),
    path("restaurants/apply/", restaurant_views.RestaurantApplyView.as_view(), name="restaurant-apply"),
    path("restaurants/<int:pk>/", restaurant_views.RestaurantDetailView.as_view(), name="restaurant-detail"),
    path("restaurants/<int:pk>/menu/", restaurant_views.RestaurantMenuView.as_view(), name="restaurant-menu"),

    # Orders
    path("restaurants/<int:pk>/orders/", order_views.OrderListView.as_view(), name="order-list"),
    path("restaurants/<int:pk>/orders/<int:order_id>/accept/", order_views.OrderAcceptView.as_view()),
    path("restaurants/<int:pk>/orders/<int:order_id>/reject/", order_views.OrderRejectView.as_view()),
    path("restaurants/<int:pk>/orders/<int:order_id>/preparing/", order_views.OrderPreparingView.as_view()),
    path("restaurants/<int:pk>/orders/<int:order_id>/ready/", order_views.OrderReadyView.as_view()),

    # Menu management
    path("restaurants/<int:pk>/menus/", menu_views.MenuListCreateView.as_view(), name="menu-list-create"),
    path("restaurants/<int:pk>/menus/<int:menu_id>/", menu_views.MenuDetailView.as_view(), name="menu-detail"),
    path("restaurants/<int:pk>/menus/<int:menu_id>/items/", menu_views.MenuItemCreateView.as_view(), name="menuitem-create"),
    path("restaurants/<int:pk>/menus/<int:menu_id>/items/<int:item_id>/", menu_views.MenuItemDetailView.as_view(), name="menuitem-detail"),

    # Admin
    path("admin/restaurants/pending/", admin_views.PendingRestaurantsView.as_view(), name="admin-pending"),
    path("admin/restaurants/<int:pk>/", admin_views.AdminRestaurantDetailView.as_view(), name="admin-restaurant-detail"),
    path("admin/restaurants/<int:pk>/verify/", admin_views.AdminRestaurantVerifyView.as_view(), name="admin-verify"),

    # Internal
    path("internal/restaurants/<int:pk>/is-open/", internal_views.IsOpenView.as_view(), name="internal-is-open"),
    path("internal/restaurants/<int:pk>/covers-address/", internal_views.CoversAddressView.as_view(), name="internal-covers-address"),
    path("internal/restaurants/<int:pk>/menu-items/", internal_views.MenuItemsView.as_view(), name="internal-menu-items"),
]

if settings.DEBUG:
    from restaurants.views import dev_views
    urlpatterns += [
        path("dev/simulate/order-received/", dev_views.SimulateOrderReceivedView.as_view(), name="dev-order-received"),
    ]
