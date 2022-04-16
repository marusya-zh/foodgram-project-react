import io

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db.models import Sum
from django.http import FileResponse
from django_filters.rest_framework import DjangoFilterBackend
from recipes.models import (Ingredient, Recipe, RecipeIngredientAmount,
                            Subscription, Tag)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from rest_framework import filters, permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response

from .filters import RecipeFilter
from .mixins import ListCreateRetrieveViewSet, ListRetrieveViewSet, ListViewSet
from .pagination import CustomPageNumberPagination
from .permissions import IsOwner
from .serializers import (FavoriteSerializer, IngredientSerializer,
                          PasswordSerializer, RecipeSerializer,
                          RecipeWriteSerializer, SubscriptionSerializer,
                          TagSerializer, UserReadSerializer,
                          UserWriteSerializer)

User = get_user_model()


class UserViewSet(ListCreateRetrieveViewSet):
    """
    Вьюсет для получения списка, создания, получения пользователя.
    """
    queryset = User.objects.get_queryset()
    pagination_class = CustomPageNumberPagination

    def get_serializer_class(self):
        if self.request.method == 'GET':
            return UserReadSerializer
        return UserWriteSerializer

    def get_permissions(self):
        if self.action in ('list', 'create'):
            permission_classes = [permissions.AllowAny]
        else:
            permission_classes = [permissions.IsAuthenticated]
        return [permission() for permission in permission_classes]

    @action(methods=['get'], detail=False)
    def me(self, request):
        user = request.user
        serializer = self.get_serializer(user)
        return Response(serializer.data)

    @action(methods=['post'], detail=False)
    def set_password(self, request):
        request_user = request.user
        serializer = PasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        current_password = serializer.validated_data['current_password']

        if request_user.is_staff:
            for user in User.objects.all():
                if user.check_password(current_password):
                    user.set_password(
                        serializer.validated_data['new_password']
                    )
                    user.save()
                    return Response(status=status.HTTP_204_NO_CONTENT)

        if request_user.check_password(current_password):
            request_user.set_password(
                serializer.validated_data['new_password']
            )
            request_user.save()
            return Response(status=status.HTTP_204_NO_CONTENT)

        response = {
                        "current_password": [
                            "Не соответствует текущему значению."
                        ]
                    }
        return Response(response, status=status.HTTP_400_BAD_REQUEST)

    @action(methods=['post', 'delete'], detail=True,
            permission_classes=[permissions.IsAuthenticated])
    def subscribe(self, request, pk=None):
        user = request.user
        author = get_object_or_404(User, id=pk)

        if request.method == 'POST':
            if user == author:
                raise serializers.ValidationError(
                    {
                        "author": [
                            "Подписка на себя запрещена."
                        ]
                    }
                )
            elif Subscription.objects.filter(user=user,
                                             author=author).exists():
                raise serializers.ValidationError(
                    {
                        "author": [
                            "Такая подписка уже существует."
                        ]
                    }
                )

            subscription, _ = Subscription.objects.get_or_create(
                user=user, author=author
            )
            serializer = SubscriptionSerializer(
                subscription,
                context={'request': request}
            )
            return Response(serializer.data,
                            status=status.HTTP_201_CREATED)

        if request.method == 'DELETE':
            if user.subscriptions.filter(author_id=pk).delete()[0] == 0:
                response = {"errors": 'Автор не найден в подписках.'}
                return Response(response, status=status.HTTP_400_BAD_REQUEST)
            return Response(status=status.HTTP_204_NO_CONTENT)


class SubscriptionViewSet(ListViewSet):
    """
    Вьюсет для получения списка подписок.
    """
    serializer_class = SubscriptionSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = CustomPageNumberPagination

    def get_queryset(self):
        user = self.request.user
        return user.subscriptions.all()


class TagViewSet(ListRetrieveViewSet):
    """
    Вьюсет для получения тега и списка тегов.
    """
    queryset = Tag.objects.get_queryset()
    serializer_class = TagSerializer
    permission_classes = [permissions.AllowAny]
    pagination_class = None


class IngredientViewSet(ListRetrieveViewSet):
    """
    Вьюсет для получения ингредиента и списка ингредиентов.
    """
    queryset = Ingredient.objects.get_queryset()
    serializer_class = IngredientSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = None
    filter_backends = (filters.SearchFilter,)
    search_fields = ('^name',)


class RecipeViewSet(viewsets.ModelViewSet):
    """
    Вьюсет для получения, создания, обновления и удаления рецептов.
    """
    pagination_class = CustomPageNumberPagination
    filter_backends = (DjangoFilterBackend,)
    filterset_class = RecipeFilter

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            permission_classes = [permissions.AllowAny]
        elif self.action in ('partial_update', 'destroy'):
            permission_classes = [IsOwner]
        else:
            permission_classes = [permissions.IsAuthenticated]
        return [permission() for permission in permission_classes]

    def get_queryset(self):
        queryset = Recipe.objects

        is_favorited_filter = self.request.query_params.get('is_favorited')
        if is_favorited_filter == '1':
            user = self.request.user
            if user.is_authenticated:
                favorite_pks = user.recipes_favorite_related.all().values_list(
                    'recipe__pk', flat=True
                )
                return queryset.filter(pk__in=favorite_pks)

        is_in_shopping_cart = self.request.query_params.get(
            'is_in_shopping_cart'
        )
        if is_in_shopping_cart == '1':
            user = self.request.user
            if user.is_authenticated:
                sh_c_pks = user.recipes_shoppingcart_related.all().values_list(
                    'recipe__pk', flat=True
                )
                return queryset.filter(pk__in=sh_c_pks)

        return queryset.all()

    def get_serializer_class(self):
        if self.request.method == 'GET':
            return RecipeSerializer
        return RecipeWriteSerializer

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)

    def perform_update(self, serializer):
        serializer.save(author=self.request.user)

    def partial_update(self, request, *args, **kwargs):
        kwargs['partial'] = False
        return self.update(request, *args, **kwargs)

    def favorite_shopping_cart(self, request, pk, model, related, text):
        """
        Выполнить добавление или удаление записи в соответствующей таблице.
        """
        user = request.user
        model = apps.get_model(app_label='recipes', model_name=model)

        try:
            recipe = Recipe.objects.get(pk=pk)
        except Recipe.DoesNotExist:
            response = {"errors": 'Рецепт не найден.'}
            return Response(response, status=status.HTTP_400_BAD_REQUEST)

        if request.method == 'POST':
            item, created = model.objects.get_or_create(
                user=user,
                recipe=recipe
            )
            if created:
                serializer = FavoriteSerializer(recipe)
                return Response(serializer.data,
                                status=status.HTTP_201_CREATED)
            response = {"errors": f'Рецепт уже в {text}.'}
            return Response(response, status=status.HTTP_400_BAD_REQUEST)

        try:
            item = related.get(recipe_id=pk)
        except model.DoesNotExist:
            response = {"errors": f'Рецепт не найден в {text}.'}
            return Response(response, status=status.HTTP_400_BAD_REQUEST)

        item.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(methods=['post', 'delete'], detail=True,
            permission_classes=[permissions.IsAuthenticated])
    def favorite(self, request, pk=None):
        """
        Добавить рецепт в избранное, удалить из избранного.
        """
        queryset = request.user.recipes_favorite_related
        return self.favorite_shopping_cart(request=request,
                                           pk=pk,
                                           model='Favorite',
                                           related=queryset,
                                           text='избранном')

    @action(methods=['post', 'delete'], detail=True,
            permission_classes=[permissions.IsAuthenticated])
    def shopping_cart(self, request, pk=None):
        """
        Добавить рецепт в список покупок, удалить из списка.
        """
        queryset = request.user.recipes_shoppingcart_related
        return self.favorite_shopping_cart(request=request,
                                           pk=pk,
                                           model='ShoppingCart',
                                           related=queryset,
                                           text='списке покупок')

    @action(methods=['get'], detail=False,
            permission_classes=[permissions.IsAuthenticated])
    def download_shopping_cart(self, request):
        """
        Скачать список покупок.
        """
        user = request.user
        recipes = user.recipes_shoppingcart_related.all().values_list(
            'recipe__pk', flat=True
        )
        shopping_cart = RecipeIngredientAmount.objects.filter(
            recipe__in=recipes
        ).values(
            'ingredient__name', 'ingredient__measurement_unit'
        ).annotate(amount=Sum('amount'))

        return self.get_pdf(shopping_cart)

    def get_pdf(self, shopping_cart):
        buffer = io.BytesIO()
        p = canvas.Canvas(buffer)

        pdfmetrics.registerFont(TTFont('Georgia', 'georgia.ttf'))
        p.setFont('Georgia', 28)
        x = 80
        y = 730
        p.drawString(x, y + 30, 'Список покупок')
        for ingredient in shopping_cart:
            name, measurement_unit, amount = ingredient.values()
            p.setFont('Georgia', 16)
            p.drawString(x, y - 12, f'• {name}, {measurement_unit}   {amount}')
            y = y - 25
        p.showPage()
        p.save()
        buffer.seek(0)
        return FileResponse(
            buffer,
            as_attachment=True,
            filename='shopping_cart.pdf'
        )
