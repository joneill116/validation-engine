"""
Rule result caching for performance optimization.

Caches immutable rule evaluations to avoid redundant computation.
Only caches deterministic rules (no randomness, no external state changes).
"""
import hashlib
import json
from typing import Any, Optional
from collections import OrderedDict
from ..contracts.findings import Finding


def make_cache_key(rule_id: str, target: Any, context_hash: str) -> str:
    """
    Generate deterministic cache key for rule evaluation.
    
    Args:
        rule_id: Unique rule identifier
        target: Target value being validated
        context_hash: Hash of relevant context fields
        
    Returns:
        Cache key string
    """
    try:
        # Attempt to create a stable representation (strict - no default fallback)
        target_repr = json.dumps(target, sort_keys=True, ensure_ascii=False)
    except (TypeError, ValueError):
        # Fall back to repr for non-JSON-serializable objects
        # Warning: repr() may not be stable across runs for some objects
        target_repr = repr(target)
    
    combined = f"{rule_id}:{target_repr}:{context_hash}"
    # Use 128 bits (32 hex chars) to avoid birthday paradox collisions
    return hashlib.sha256(combined.encode()).hexdigest()[:32]


def hash_context(entity_type: str, ruleset_id: str, reference_data: Any) -> str:
    """
    Create stable hash of evaluation context.
    
    Only includes fields that affect rule evaluation.
    Excludes metadata which doesn't impact rule logic.
    
    Args:
        entity_type: Type of entity being validated
        ruleset_id: Ruleset identifier
        reference_data: Reference data (dict or MappingProxyType)
        
    Returns:
        Hex digest hash string
    """
    # Convert MappingProxyType to dict for serialization
    ref_data_dict = dict(reference_data) if hasattr(reference_data, '__iter__') else reference_data
    
    context_dict = {
        "entity_type": entity_type,
        "ruleset_id": ruleset_id,
        "reference_data": ref_data_dict,
    }
    try:
        # Strict serialization - fail if reference_data contains non-JSON types
        serialized = json.dumps(context_dict, sort_keys=True, ensure_ascii=False)
    except (TypeError, ValueError) as e:
        # Non-serializable reference_data breaks caching guarantees
        raise ValueError(
            f"reference_data must be JSON-serializable for cache consistency. "
            f"Contains non-serializable objects: {e}"
        )
    # Use 128 bits (32 hex chars) to avoid birthday paradox collisions
    return hashlib.sha256(serialized.encode()).hexdigest()[:32]


class RuleCache:
    """
    LRU cache for rule evaluation results.
    
    Memory-bounded cache for immutable rule findings with LRU eviction.
    Automatically evicts least-recently-used entries when capacity is reached.
    
    **Note**: This implementation is NOT thread-safe. For concurrent use,
    wrap method calls with external locking (e.g., threading.Lock).
    
    Usage:
        cache = RuleCache(max_size=10000)
        
        # Try to get cached result
        key = make_cache_key(rule.rule_id, target, ctx_hash)
        cached = cache.get(key)
        
        if cached is None:
            # Cache miss - evaluate and store
            result = rule.evaluate(target, ctx)
            cache.put(key, result)
        else:
            # Cache hit
            result = cached
    """
    
    def __init__(self, max_size: int = 10000):
        """
        Initialize cache with maximum size.
        
        Args:
            max_size: Maximum number of cached entries (default: 10000)
        """
        self.max_size = max_size
        self._cache: OrderedDict[str, Finding] = OrderedDict()
        self._hits = 0
        self._misses = 0
    
    def get(self, key: str) -> Optional[Finding]:
        """
        Retrieve cached finding by key.
        
        Updates access order for LRU eviction (O(1) operation).
        
        Args:
            key: Cache key
            
        Returns:
            Cached Finding or None if not found
        """
        if key in self._cache:
            self._hits += 1
            # Move to end (most recently used) - O(1) with OrderedDict
            self._cache.move_to_end(key)
            return self._cache[key]
        
        self._misses += 1
        return None
    
    def put(self, key: str, finding: Finding) -> None:
        """
        Store finding in cache.
        
        Evicts least-recently-used entry if at capacity (O(1) operation).
        
        Args:
            key: Cache key
            finding: Finding to cache
        """
        if key in self._cache:
            # Update existing entry and move to end
            self._cache.move_to_end(key)
            self._cache[key] = finding
            return
        
        # Evict LRU if at capacity
        if len(self._cache) >= self.max_size:
            # Remove first item (least recently used) - O(1)
            self._cache.popitem(last=False)
        
        # Add new entry at end (most recently used)
        self._cache[key] = finding
    
    def clear(self) -> None:
        """Clear all cached entries and reset statistics."""
        self._cache.clear()
        self._hits = 0
        self._misses = 0
    
    def stats(self) -> dict[str, int | float]:
        """
        Get cache statistics.
        
        Returns:
            Dictionary with:
            - hits: Number of cache hits (int)
            - misses: Number of cache misses (int)
            - size: Current number of cached entries (int)
            - max_size: Maximum cache capacity (int)
            - hit_rate_percent: Hit rate as percentage (float)
        """
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total > 0 else 0.0
        
        return {
            "hits": self._hits,
            "misses": self._misses,
            "size": len(self._cache),
            "max_size": self.max_size,
            "hit_rate_percent": round(hit_rate, 2),
        }
