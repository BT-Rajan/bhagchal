"""
Baghchal - A Flask-based Bagh Chal (Tiger and Goat) Board Game

A complete server-authoritative implementation of the traditional Nepali board game.
All game logic, AI, and state management run on the server. The browser only renders
the board and sends user actions.

Project Structure:
    baghchal/
    ├── __init__.py          - Application factory and extensions
    ├── config.py             - Configuration settings
    ├── app.py                - Main application entry point
    ├── models/               - Data models and storage
    │   ├── __init__.py
    │   ├── user.py           - User model and authentication
    │   └── game.py           - Game session and state management
    ├── services/             - Business logic
    │   ├── __init__.py
    │   ├── engine.py         - Core game logic (board, moves, validation)
    │   ├── ai.py             - Minimax AI with Alpha-Beta pruning
    │   └── report.py         - Game report export
    ├── api/                  - REST API routes
    │   ├── __init__.py
    │   ├── auth.py           - Authentication endpoints
    │   └── game.py           - Game action endpoints
    └── utils/                - Helper utilities
        └── decorators.py     - Flask route decorators
"""

__version__ = '2.0.0'
__author__ = 'Baghchal Team'

from baghchal.app import create_app

__all__ = ['create_app']
