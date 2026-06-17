"""
Configuration settings for the Baghchal application.
"""
import os
from dotenv import load_dotenv

# Load environment variables from .env before reading them below.
load_dotenv()


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

    # DeepSeek-powered post-game personality analysis
    DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY')
    DEEPSEEK_API_URL = os.environ.get('DEEPSEEK_API_URL', 'https://api.deepseek.com/v1/chat/completions')

    # Mail delivery for the analyzed report.
    # MAIL_MODE='development' (default) writes a .log file under MAIL_DIR
    # instead of sending; MAIL_MODE='production' sends via SMTP_* below.
    MAIL_MODE = os.environ.get('MAIL_MODE', 'development')
    MAIL_DIR = os.environ.get('MAIL_DIR', 'mail')
    MAIL_FROM = os.environ.get('MAIL_FROM', 'noreply@baghchal.local')
    MAIL_TO = os.environ.get('MAIL_TO', '')  # optional extra/admin recipients, comma-separated
    SMTP_HOST = os.environ.get('SMTP_HOST', '')
    SMTP_PORT = int(os.environ.get('SMTP_PORT', '587'))
    SMTP_USERNAME = os.environ.get('SMTP_USERNAME', '')
    SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD', '')
    SMTP_USE_TLS = os.environ.get('SMTP_USE_TLS', '1') == '1'


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
