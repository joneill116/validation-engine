"""
Reference Data Management System.

Centralized management of static lookup data used in validation rules.
Keeps hardcoded values out of rules and makes them externally configurable.
Completely domain-agnostic - works with any type of reference data.

Example reference data:
    - Allowed enumerations (statuses, types, categories)
    - Geographic codes (countries, regions, timezones)
    - Identifier format specifications
    - Lookup tables for cross-referencing
    - Business rules thresholds and limits
"""
import json
from pathlib import Path
from typing import Any, Optional
import logging

logger = logging.getLogger(__name__)


class ReferenceDataManager:
    """
    Manages static lookup data for validation rules.
    
    Loads JSON files from a directory and provides key-based access.
    All data is cached in memory for fast lookups during validation.
    Supports hot-reloading for configuration updates without restart.
    
    Usage:
        ref_data = ReferenceDataManager()
        
        # Access reference data by key
        valid_countries = ref_data.get("valid_countries")
        allowed_statuses = ref_data.get("allowed_statuses", default=[])
        
        # Check existence
        if ref_data.has("custom_lookup"):
            values = ref_data.get("custom_lookup")
        
        # Programmatic updates (useful for testing)
        ref_data.set("test_data", {"key": "value"})
        
        # Reload from disk
        ref_data.reload()
    """
    
    def __init__(self, data_dir: Optional[str] = None):
        """
        Initialize reference data manager.
        
        Args:
            data_dir: Path to reference data directory containing JSON files.
                     Defaults to ./reference_data/ relative to project root.
        """
        if data_dir is None:
            # Default to reference_data/ in project root
            self.data_dir = Path(__file__).parent.parent.parent / "reference_data"
        else:
            self.data_dir = Path(data_dir)
        
        self._cache: dict[str, Any] = {}
        self._load_all_reference_data()
    
    def _load_all_reference_data(self) -> None:
        """
        Load all JSON files from reference data directory.
        
        Files are merged into a single flat namespace.
        Keys from later files override keys from earlier files.
        """
        if not self.data_dir.exists():
            logger.warning(
                f"Reference data directory not found: {self.data_dir}. "
                f"No reference data will be available."
            )
            return
        
        if not self.data_dir.is_dir():
            logger.error(
                f"Reference data path is not a directory: {self.data_dir}"
            )
            return
        
        json_files = sorted(self.data_dir.glob("*.json"))
        
        if not json_files:
            logger.info(
                f"No JSON files found in reference data directory: {self.data_dir}"
            )
            return
        
        for json_file in json_files:
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                if not isinstance(data, dict):
                    logger.error(
                        f"Invalid reference data format in {json_file.name}: "
                        f"expected dict, got {type(data).__name__}"
                    )
                    continue
                
                # Merge into cache
                self._cache.update(data)
                logger.info(
                    f"Loaded reference data from {json_file.name}: "
                    f"{len(data)} keys"
                )
                
            except json.JSONDecodeError as e:
                logger.error(
                    f"Failed to parse JSON in {json_file.name}: {e}",
                    exc_info=True
                )
            except Exception as e:
                logger.error(
                    f"Failed to load {json_file.name}: {e}",
                    exc_info=True
                )
        
        logger.info(
            f"Reference data loaded: {len(self._cache)} total keys from "
            f"{len(json_files)} files"
        )
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get reference data by key.
        
        Args:
            key: The reference data key (e.g., 'valid_countries')
            default: Default value if key not found
            
        Returns:
            Reference data value or default
        """
        return self._cache.get(key, default)
    
    def has(self, key: str) -> bool:
        """
        Check if reference data key exists.
        
        Args:
            key: The reference data key to check
            
        Returns:
            True if key exists, False otherwise
        """
        return key in self._cache
    
    def reload(self) -> None:
        """
        Reload all reference data from disk.
        
        Clears the cache and reloads all JSON files.
        Useful for picking up configuration changes without restart.
        """
        logger.info("Reloading reference data from disk")
        self._cache.clear()
        self._load_all_reference_data()
    
    def get_all_keys(self) -> list[str]:
        """
        Get all available reference data keys.
        
        Returns:
            Sorted list of all keys in the cache
        """
        return sorted(self._cache.keys())
    
    def set(self, key: str, value: Any) -> None:
        """
        Set reference data programmatically.
        
        Useful for testing or dynamic configuration.
        Changes are not persisted to disk.
        
        Args:
            key: The reference data key
            value: The value to set
        """
        self._cache[key] = value
        logger.debug(f"Set reference data key: {key!r}")
    
    def clear(self) -> None:
        """
        Clear all cached reference data.
        
        Does not delete files from disk, only clears in-memory cache.
        """
        self._cache.clear()
        logger.info("Reference data cache cleared")
    
    def size(self) -> int:
        """
        Get the number of cached reference data keys.
        
        Returns:
            Count of keys in cache
        """
        return len(self._cache)


# Global singleton instance for convenience
_global_ref_data: Optional[ReferenceDataManager] = None


def get_reference_data() -> ReferenceDataManager:
    """
    Get the global reference data manager instance.
    
    Returns:
        Singleton ReferenceDataManager instance
    """
    global _global_ref_data
    if _global_ref_data is None:
        _global_ref_data = ReferenceDataManager()
    return _global_ref_data


def load_custom_reference_data(data_dir: str):
    """
    Load reference data from a custom directory.
    
    Args:
        data_dir: Path to custom reference data directory
    """
    global _global_ref_data
    _global_ref_data = ReferenceDataManager(data_dir)
