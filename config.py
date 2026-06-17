"""
Configuration settings for the Baghchal application.
"""
import os


class Config:
    """Base configuration."""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'baghchal-server-secret-change-in-production'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    
    # Game settings
    MAX_SESSION_GAMES = 5
    DEFAULT_DIFFICULTIES = ['easy', 'medium', 'medium', 'medium', 'medium']
    DEFAULT_ROLES = ['tiger', 'goat', 'tiger', 'goat', 'tiger']
    
    # Time limits (in seconds) for timed games
    TIMED_GAME_NUMBER = 5
    TIMED_GAME_LIMIT = 7 * 60  # 7 minutes
    
    # AI difficulty depth mapping
    AI_DEPTH_MAP = {
        'easy': 1,
        'medium': 3,
        'hard': 4
    }
    
    # Report settings
    REPORTS_DIR = 'game_reports'


class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True


class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False
    # In production, use a real database and proper password hashing
    # SECRET_KEY should be set via environment variable


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
