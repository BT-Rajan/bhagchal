"""API routes package."""

from .auth import auth_bp
from .game import game_bp

__all__ = ['auth_bp', 'game_bp']
