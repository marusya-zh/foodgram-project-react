from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (IngredientViewSet,
                    RecipeViewSet,
                    SubscriptionViewSet,
                    TagViewSet,
                    UserViewSet)

router = DefaultRouter()
router.register('users/subscriptions', SubscriptionViewSet,
                basename='subscription')
router.register(r'users', UserViewSet, basename='user')
router.register(r'tags', TagViewSet)
router.register(r'recipes', RecipeViewSet, basename='recipe')
router.register(r'ingredients', IngredientViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('auth/', include('djoser.urls.authtoken')),
]
