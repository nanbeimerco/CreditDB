"""
Data module exports.
"""

from .anilist_client import AniListClient
from .seesaa_client import SeesaaStaffClient
from .matcher import AnimeMatcher
from .dataset import DatasetManager
from .bulk_collector import BulkDataCollector

__all__ = [
    "AniListClient",
    "SeesaaStaffClient",
    "AnimeMatcher",
    "DatasetManager",
    "BulkDataCollector",
]
