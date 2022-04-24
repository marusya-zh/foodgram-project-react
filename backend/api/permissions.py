from rest_framework.permissions import SAFE_METHODS, BasePermission


class ReadOnlyPermission(BasePermission):
    def has_permission(self, request, view):
        return request.method in SAFE_METHODS


class ReadOnly(ReadOnlyPermission):
    """
    Безопасные запросы доступны любому пользователю.
    """
    def has_object_permission(self, request, view, obj):
        return super().has_permission(request, view)


class IsOwner(BasePermission):
    """
    Пермишен, дающий доступ к объекту только его владельцу.
    """
    def has_object_permission(self, request, view, obj):
        return obj.author == request.user
