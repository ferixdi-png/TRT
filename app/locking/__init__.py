"""
Locking module - единый механизм блокировки для предотвращения 409 Conflict
"""

from app.locking.single_instance import (
    acquire_single_instance_lock,
    release_single_instance_lock,
    is_lock_held,
)

__all__ = [
    'acquire_single_instance_lock',
    'release_single_instance_lock',
    'is_lock_held',
]

