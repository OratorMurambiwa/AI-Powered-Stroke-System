from .user_service import ensure_default_users, authenticate_user

# Avoid importing optional/third-party heavy modules (e.g. ai_service)
# at package import time. Import submodules directly where needed instead.

__all__ = ["ensure_default_users", "authenticate_user"]
