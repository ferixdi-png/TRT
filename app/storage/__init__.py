"""
Storage module - единый интерфейс для хранения данных
"""

from app.storage.base import BaseStorage
from app.storage.json_storage import JsonStorage
from app.storage.pg_storage import PostgresStorage
from app.storage.factory import create_storage, get_storage, reset_storage

__all__ = [
    'BaseStorage',
    'JsonStorage',
    'PostgresStorage',
    'create_storage',
    'get_storage',
    'reset_storage'
]
