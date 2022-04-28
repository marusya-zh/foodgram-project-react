from rest_framework.permissions import SAFE_METHODS, BasePermission


class ReadOnly(BasePermission):
    """
    Безопасные запросы доступны любому пользователю.
    """
    def has_permission(self, request, view):
        return request.method in SAFE_METHODS


class IsOwner(BasePermission):
    """
    Пермишен, дающий доступ к объекту только его владельцу.
    """
    def has_object_permission(self, request, view, obj):
        return obj.author == request.user
