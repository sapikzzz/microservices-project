from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView
from .views import RegisterView, UserTokenObtainPairView, InternalUserDetailView, AddressViewSet, FavoriteViewSet

router = DefaultRouter()
router.register(r'addresses', AddressViewSet, basename='address')
router.register(r'favorites', FavoriteViewSet, basename='favorite')

urlpatterns = [
    path('register/', RegisterView.as_view(), name='auth_register'),
    path('login/', UserTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('internal/<int:user_id>/', InternalUserDetailView.as_view(), name='internal_user_detail'),
    path('', include(router.urls)),
]
