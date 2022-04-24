import io

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db.models import Sum
from django.http import HttpResponse
from django_filters.rest_framework import DjangoFilterBackend
from djoser.views import UserViewSet as DjoserUserViewSet
from recipes.models import (Ingredient, Recipe, RecipeIngredientAmount,
                            Subscription, Tag)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from rest_framework import permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.generics import get_object_or_404
from rest_framework.response import Response

from .filters import IngredientFilter, RecipeFilter
from .mixins import ListRetrieveViewSet, ListViewSet
from .permissions import IsOwner, ReadOnly
from .serializers import (FavoriteSerializer, IngredientSerializer,
                          RecipeSerializer, RecipeWriteSerializer,
                          SubscriptionSerializer, TagSerializer)

User = get_user_model()


class UserViewSet(DjoserUserViewSet):
    @action(methods=['post', 'delete'], detail=True,
            permission_classes=(permissions.IsAuthenticated,))
    def subscribe(self, request, id=None):
        user = request.user
        author = get_object_or_404(User, id=id)

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
            deleted, _ = user.subscriptions.filter(author_id=id).delete()
            if deleted:
                return Response(status=status.HTTP_204_NO_CONTENT)
            response = {"errors": 'Автор не найден в подписках.'}
            return Response(response, status=status.HTTP_400_BAD_REQUEST)


class SubscriptionViewSet(ListViewSet):
    """
    Вьюсет для получения списка подписок.
    """
    serializer_class = SubscriptionSerializer
    permission_classes = (permissions.IsAuthenticated,)

    def get_queryset(self):
        user = self.request.user
        return user.subscriptions.all()


class TagViewSet(ListRetrieveViewSet):
    """
    Вьюсет для получения тега и списка тегов.
    """
    queryset = Tag.objects.get_queryset()
    serializer_class = TagSerializer
    permission_classes = (permissions.AllowAny,)
    pagination_class = None


class IngredientViewSet(ListRetrieveViewSet):
    """
    Вьюсет для получения ингредиента и списка ингредиентов.
    """
    queryset = Ingredient.objects.get_queryset()
    serializer_class = IngredientSerializer
    permission_classes = (permissions.AllowAny,)
    pagination_class = None
    filter_backends = (DjangoFilterBackend,)
    filterset_class = IngredientFilter


class RecipeViewSet(viewsets.ModelViewSet):
    """
    Вьюсет для получения, создания, обновления и удаления рецептов.
    """
    permission_classes = ((permissions.IsAuthenticated & IsOwner) | ReadOnly,)
    filter_backends = (DjangoFilterBackend,)
    filterset_class = RecipeFilter

    def get_queryset(self):
        user = self.request.user
        is_favorited_filter = self.request.query_params.get(
            'is_favorited'
        )
        is_in_shopping_cart_filter = self.request.query_params.get(
            'is_in_shopping_cart'
        )

        if user.is_authenticated:
            marked_recipes = Recipe.marked.favorited_shoppingcart(user)
            if is_favorited_filter == '1':
                return marked_recipes.filter(is_favorited=True).all()
            elif is_in_shopping_cart_filter == '1':
                return marked_recipes.filter(is_in_shopping_cart=True).all()
            return marked_recipes
        return Recipe.objects.all()

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
            permission_classes=(permissions.IsAuthenticated,))
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
            permission_classes=(permissions.IsAuthenticated,))
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

    def get_pdf(self, shopping_cart):
        """
        Сформировать список покупок.
        """
        buffer = io.BytesIO()
        p = canvas.Canvas(buffer)

        pdfmetrics.registerFont(TTFont('Georgia', 'georgia.ttf'))
        p.setFont('Georgia', 28)
        x, y = 80, 730
        p.drawString(x, y + 30, 'Список покупок')
        for ingredient in shopping_cart:
            name, measurement_unit, amount = ingredient.values()
            p.setFont('Georgia', 16)
            p.drawString(x, y - 12, f'• {name}, {measurement_unit}   {amount}')
            y = y - 25
        p.showPage()
        p.save()
        pdf = buffer.getvalue()
        buffer.close()

        return pdf

    @action(methods=['get'], detail=False,
            permission_classes=(permissions.IsAuthenticated,))
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

        pdf = self.get_pdf(shopping_cart)
        response = HttpResponse(pdf, content_type='application/pdf')
        content_disposition = 'attachment; filename="shopping_cart.pdf"'
        response['Content-Disposition'] = content_disposition
        return response
