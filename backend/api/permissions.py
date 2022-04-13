from rest_framework import permissions


class IsOwner(permissions.BasePermission):
    """
    Пермишен, дающий доступ к объекту только его владельцу.
    """

    def has_permission(self, request, view):
        return request.user.is_authenticated

    def has_object_permission(self, request, view, obj):
        return obj.author == request.user
