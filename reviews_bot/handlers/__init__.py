from .user import user_router
from .admin import admin_router
from .errors import errors_router

__all__ = ["user_router", "admin_router", "errors_router"]
