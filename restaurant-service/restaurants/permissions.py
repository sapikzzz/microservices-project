from rest_framework.permissions import BasePermission


class IsAuthenticated(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.id is not None)


class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == "admin")


class IsRestaurantOwner(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.role == "restaurant")

    def has_object_permission(self, request, view, obj):
        from restaurants.models import Restaurant
        if isinstance(obj, Restaurant):
            return obj.owner_id == request.user.id
        if hasattr(obj, "restaurant"):
            return obj.restaurant.owner_id == request.user.id
        return False


class IsInternal(BasePermission):
    def has_permission(self, request, view):
        from django.conf import settings
        secret = request.META.get("HTTP_X_INTERNAL_SECRET")
        return secret == settings.INTERNAL_SECRET
