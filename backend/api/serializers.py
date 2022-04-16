import base64
import imghdr
import uuid

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.paginator import Paginator
from recipes.models import (Favorite, Ingredient, Recipe,
                            RecipeIngredientAmount, ShoppingCart, Subscription,
                            Tag)
from rest_framework import serializers
from rest_framework.generics import get_object_or_404

User = get_user_model()


class UserReadSerializer(serializers.ModelSerializer):
    """
    Сериализатор на чтение для модели пользователя.
    """
    is_subscribed = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ('email', 'id', 'username', 'first_name',
                  'last_name', 'is_subscribed')

    def get_is_subscribed(self, obj):
        return False


class UserWriteSerializer(serializers.ModelSerializer):
    """
    Сериализатор на запись для модели пользователя.
    """

    class Meta:
        model = User
        fields = ('email', 'id', 'username', 'first_name',
                  'last_name', 'password')
        extra_kwargs = {'password': {'write_only': True}}

    def create(self, validated_data):
        for user in User.objects.all():
            if user.check_password(validated_data['password']):
                raise serializers.ValidationError(
                    {
                        "password": [
                            "Пользователь с таким паролем уже существует."
                        ]
                    }
                )
        user = super().create(validated_data)
        user.set_password(validated_data['password'])
        user.save()
        return user


class PasswordSerializer(serializers.Serializer):
    """
    Сериализатор пароля.
    """
    new_password = serializers.CharField(max_length=150, required=True)
    current_password = serializers.CharField(max_length=150, required=True)


class TagSerializer(serializers.ModelSerializer):
    """
    Сериализатор модели тега.
    """
    class Meta:
        model = Tag
        fields = '__all__'


class IngredientSerializer(serializers.ModelSerializer):
    """
    Сериализатор модели ингредиента.
    """
    class Meta:
        model = Ingredient
        fields = ('id', 'name', 'measurement_unit')


class RecipeIngredientAmountSerializer(serializers.ModelSerializer):
    """
    Сериализатор модели, связывающей рецепт, ингредиент и количество.
    На чтение.
    """
    id = serializers.ReadOnlyField(
        source='ingredient.id'
    )
    name = serializers.ReadOnlyField(
        source='ingredient.name'
    )
    measurement_unit = serializers.ReadOnlyField(
        source='ingredient.measurement_unit'
    )

    class Meta:
        model = RecipeIngredientAmount
        fields = ('id', 'name', 'measurement_unit', 'amount')


class RecipeIngredientAmountWriteSerializer(serializers.ModelSerializer):
    """
    Сериализатор модели, связывающей рецепт, ингредиент и количество.
    На запись.
    """
    id = serializers.IntegerField()

    class Meta:
        model = RecipeIngredientAmount
        fields = ('id', 'amount')


class RecipeSerializer(serializers.ModelSerializer):
    """
    Сериализатор на чтение для модели рецепта.
    """
    tags = TagSerializer(many=True)
    author = UserReadSerializer()
    ingredients = RecipeIngredientAmountSerializer(
        source='recipeingredientamount',
        many=True
    )
    is_favorited = serializers.SerializerMethodField()
    is_in_shopping_cart = serializers.SerializerMethodField()

    class Meta:
        model = Recipe
        fields = ('id', 'tags', 'author', 'ingredients',
                  'is_favorited', 'is_in_shopping_cart',
                  'name', 'image', 'text', 'cooking_time')

    def get_is_favorited(self, obj):
        user = self.context['request'].user
        return (user.is_authenticated and
                Favorite.objects.filter(user=user, recipe=obj).exists())

    def get_is_in_shopping_cart(self, obj):
        user = self.context['request'].user
        return (user.is_authenticated and
                ShoppingCart.objects.filter(user=user, recipe=obj).exists())


class Base64ImageField(serializers.ImageField):
    """
    Сериализатор изображения для записи рецепта.
    """
    def to_internal_value(self, data):
        if isinstance(data, str):
            if 'data:' in data and ';base64,' in data:
                header, data = data.split(';base64,')

            try:
                decoded_file = base64.b64decode(data)
            except TypeError:
                self.fail('invalid_image')

            file_name = str(uuid.uuid4())
            file_extension = self.get_file_extension(file_name, decoded_file)
            complete_file_name = f'{file_name}.{file_extension}'
            data = ContentFile(decoded_file, name=complete_file_name)

        return super().to_internal_value(data)

    def get_file_extension(self, file_name, decoded_file):
        extension = imghdr.what(file_name, decoded_file)
        extension = "jpg" if extension == "jpeg" else extension
        return extension


class RecipeWriteSerializer(serializers.ModelSerializer):
    """
    Сериализатор на запись для модели рецепта.
    """
    ingredients = RecipeIngredientAmountWriteSerializer(
        many=True
    )
    tags = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Tag.objects.all()
    )
    image = Base64ImageField(max_length=None, use_url=True)

    class Meta:
        model = Recipe
        fields = ('ingredients', 'tags', 'image',
                  'name', 'text', 'cooking_time')

    def create(self, validated_data):
        ingredients_data = validated_data.pop('ingredients')
        tags_data = validated_data.pop('tags')

        recipe = Recipe.objects.create(**validated_data)
        amounts = self.get_amounts(recipe, ingredients_data)
        RecipeIngredientAmount.objects.bulk_create(amounts)

        for tag_data in tags_data:
            tag = get_object_or_404(Tag, id=tag_data.id)
            recipe.tags.add(tag)

        recipe.save()
        return recipe

    def update(self, instance, validated_data):
        ingredients_data = validated_data.pop('ingredients')
        tags_data = validated_data.pop('tags')

        instance = super().update(instance, validated_data)
        instance.recipeingredientamount.all().delete()
        amounts = self.get_amounts(instance, ingredients_data)
        RecipeIngredientAmount.objects.bulk_create(amounts)

        tags = []
        for tag_data in tags_data:
            tag = get_object_or_404(Tag, id=tag_data.id)
            tags.append(tag)
        instance.tags.set(tags)

        return instance

    def get_amounts(self, recipe, ingredients_data):
        amounts = [
            RecipeIngredientAmount(
                recipe=recipe,
                ingredient=get_object_or_404(Ingredient,
                                             id=ingredient_data['id']),
                amount=ingredient_data['amount']
            )
            for ingredient_data in ingredients_data
        ]
        return amounts

    def to_representation(self, instance):
        return RecipeSerializer(instance, context=self.context).data


class FavoriteSerializer(serializers.ModelSerializer):
    """
    Сериализатор для модели избранного.
    """
    class Meta:
        model = Recipe
        fields = ('id', 'name', 'image', 'cooking_time')
        read_only_fields = ('id', 'name', 'image', 'cooking_time')


class SubscriptionSerializer(serializers.ModelSerializer):
    """
    Сериализатор для модели подписки.
    """
    email = serializers.EmailField(source='author.email')
    id = serializers.IntegerField(source='author.id', required=False)
    username = serializers.CharField(source='author.username')
    first_name = serializers.CharField(source='author.first_name')
    last_name = serializers.CharField(source='author.last_name')
    is_subscribed = serializers.SerializerMethodField()
    recipes = serializers.SerializerMethodField()
    recipes_count = serializers.SerializerMethodField()

    class Meta:
        model = Subscription
        fields = ('email', 'id', 'username', 'first_name', 'last_name',
                  'is_subscribed', 'recipes', 'recipes_count')

    def get_is_subscribed(self, obj):
        user = self.context['request'].user
        author = obj.author
        return (user.is_authenticated and
                Subscription.objects.filter(user=user, author=author).exists())

    def get_recipes(self, obj):
        query_params = self.context['request'].query_params
        recipes_limit = query_params.get(
            'recipes_limit',
            settings.REST_FRAMEWORK['PAGE_SIZE']
        )
        recipes_page = query_params.get('recipes_page', 1)

        paginator = Paginator(obj.author.recipes.all(), recipes_limit)
        recipes = paginator.page(recipes_page)
        serializer = FavoriteSerializer(recipes, many=True)
        return serializer.data

    def get_recipes_count(self, obj):
        return obj.author.recipes.all().count()
