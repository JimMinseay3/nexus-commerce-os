from rest_framework.permissions import BasePermission, SAFE_METHODS

from .models import UserProfile


ROLE_WRITE_MATRIX = {
    "products": {UserProfile.Role.ADMIN, UserProfile.Role.OPERATIONS, UserProfile.Role.PROCUREMENT},
    "orders": {UserProfile.Role.ADMIN, UserProfile.Role.OPERATIONS, UserProfile.Role.WAREHOUSE},
    "purchases": {UserProfile.Role.ADMIN, UserProfile.Role.PROCUREMENT},
    "warehouse": {UserProfile.Role.ADMIN, UserProfile.Role.WAREHOUSE},
    "finance": {UserProfile.Role.ADMIN, UserProfile.Role.FINANCE},
    "integrations": {UserProfile.Role.ADMIN, UserProfile.Role.OPERATIONS},
    "admin": {UserProfile.Role.ADMIN},
}


class RolePermission(BasePermission):
    area = None

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if hasattr(request.auth, "scopes"):
            if request.method in SAFE_METHODS:
                return "read" in request.auth.scopes or not request.auth.scopes
            return "write" in request.auth.scopes
        if request.method in SAFE_METHODS:
            return True
        profile = getattr(request.user, "profile", None)
        if request.user.is_superuser:
            return True
        area = getattr(view, "permission_area", self.area)
        if not profile or not area:
            return False
        return profile.role in ROLE_WRITE_MATRIX.get(area, {UserProfile.Role.ADMIN})


class IsAdminRole(BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        return request.user.is_superuser or getattr(getattr(request.user, "profile", None), "role", "") == UserProfile.Role.ADMIN

