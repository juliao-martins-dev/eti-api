from rest_framework.permissions import BasePermission


class EhAdmin(BasePermission):
    """
    Only the school's administration may look at somebody else's attendance.
    Every other endpoint scopes its queryset to `request.user`, so this is the
    one gate that has to be explicit.
    """

    message = 'Ita la iha permisaun atu haree prezensa profesór/a seluk nian.'

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        return user.is_staff or user.role == user.Role.ADMIN
