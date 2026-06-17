"""
User model and authentication management.

In-memory user store (swap for database in production).
"""
import hashlib
import secrets
import time
from typing import Optional, Dict, Any, Tuple


class UserModel:
    """Manages user accounts and authentication."""
    
    def __init__(self):
        self._users: Dict[str, Dict[str, Any]] = {}
        self._tokens: Dict[str, Dict[str, Any]] = {}
        self._seed_defaults()
    
    def _hash(self, password: str) -> str:
        """Hash password using SHA-256 (use bcrypt/argon2 in production)."""
        return hashlib.sha256(password.encode()).hexdigest()
    
    def _seed_defaults(self) -> None:
        """Seed default admin and guest users."""
        defaults = [
            ('admin', 'admin', 'admin'),
            ('guest', 'guest', 'user')
        ]
        for username, password, role in defaults:
            key = username.lower()
            self._users[key] = {
                'username': username,
                'password_hash': self._hash(password),
                'role': role,
                'created_at': '2024-01-01',
                'games_played': 0,
                'email': f'{username}@localhost'
            }
    
    def register(self, username: str, password: str, email: str = '') -> Tuple[bool, Any]:
        """Register a new user account."""
        if not username or len(username) < 2:
            return False, 'Username must be at least 2 characters.'
        
        if not all(c.isalnum() or c == '_' for c in username):
            return False, 'Username: letters, numbers, underscores only.'
        
        if not password or len(password) < 4:
            return False, 'Password must be at least 4 characters.'
        
        key = username.lower()
        if key in self._users:
            return False, 'Username already taken.'
        
        self._users[key] = {
            'username': username,
            'password_hash': self._hash(password),
            'role': 'user',
            'created_at': time.strftime('%Y-%m-%d'),
            'games_played': 0,
            'email': email
        }
        return True, self._users[key]
    
    def login(self, username: str, password: str) -> Tuple[bool, Any]:
        """Authenticate user credentials."""
        key = username.lower()
        user = self._users.get(key)
        
        if not user:
            return False, 'User not found.'
        
        if user['password_hash'] != self._hash(password):
            return False, 'Incorrect password.'
        
        return True, user
    
    def get_user(self, username: str) -> Optional[Dict[str, Any]]:
        """Get user by username."""
        return self._users.get(username.lower())
    
    def all_users(self) -> list:
        """Get all users."""
        return list(self._users.values())
    
    def delete_user(self, username: str) -> bool:
        """Delete a non-admin user."""
        key = username.lower()
        user = self._users.get(key)
        if user and user['role'] != 'admin':
            del self._users[key]
            return True
        return False
    
    def increment_games(self, username: str) -> None:
        """Increment games played counter."""
        user = self._users.get(username.lower())
        if user:
            user['games_played'] = user.get('games_played', 0) + 1
    
    def generate_reset_token(self, username: str) -> Optional[str]:
        """Generate a password reset token (valid for 5 minutes)."""
        user = self._users.get(username.lower())
        if not user:
            return None
        
        token = secrets.token_hex(6).upper()
        self._tokens[username.lower()] = {
            'token': token,
            'expires': time.time() + 300
        }
        return token
    
    def reset_password(self, username: str, token: str, new_password: str) -> Tuple[bool, str]:
        """Reset password using token."""
        if not new_password or len(new_password) < 4:
            return False, 'Password must be at least 4 characters.'
        
        key = username.lower()
        entry = self._tokens.get(key)
        
        if not entry or entry['token'] != token:
            return False, 'Invalid token.'
        
        if time.time() > entry['expires']:
            return False, 'Token expired.'
        
        user = self._users.get(key)
        if not user:
            return False, 'User not found.'
        
        user['password_hash'] = self._hash(new_password)
        del self._tokens[key]
        return True, 'Password reset successfully.'


# Singleton instance
user_model = UserModel()
