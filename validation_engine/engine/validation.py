"""
Payload validation and schema enforcement.

Validates input structure before processing to fail fast with clear errors.
"""
import json
from typing import Any


class PayloadValidationError(ValueError):
    """Raised when payload structure is invalid."""
    
    def __init__(self, message: str, path: str | None = None):
        self.path = path
        super().__init__(f"{message} (at: {path})" if path else message)


def validate_payload(payload: Any) -> dict[str, list[dict[str, Any]]]:
    """
    Validate payload structure before processing.
    
    Args:
        payload: Input payload to validate
        
    Returns:
        Validated payload with normalized structure
        
    Raises:
        PayloadValidationError: If payload structure is invalid
    """
    if not isinstance(payload, dict):
        raise PayloadValidationError(
            f"Payload must be a dictionary, got {type(payload).__name__}"
        )
    
    if "entities" not in payload:
        raise PayloadValidationError(
            "Payload must contain 'entities' key"
        )
    
    entities = payload["entities"]
    if not isinstance(entities, list):
        raise PayloadValidationError(
            f"'entities' must be a list, got {type(entities).__name__}",
            path="entities"
        )
    
    # Validate each entity structure
    for idx, entity in enumerate(entities):
        _validate_entity(entity, idx)
    
    return {"entities": entities}


def _validate_entity(entity: Any, index: int) -> None:
    """Validate single entity structure."""
    path_prefix = f"entities[{index}]"
    
    if not isinstance(entity, dict):
        raise PayloadValidationError(
            f"Entity must be a dictionary, got {type(entity).__name__}",
            path=path_prefix
        )
    
    # entity_ref is optional but must be dict if present
    if "entity_ref" in entity:
        if not isinstance(entity["entity_ref"], dict):
            raise PayloadValidationError(
                f"entity_ref must be a dictionary, got {type(entity['entity_ref']).__name__}",
                path=f"{path_prefix}.entity_ref"
            )
    
    # fields is required
    if "fields" not in entity:
        raise PayloadValidationError(
            "Entity must contain 'fields' key",
            path=path_prefix
        )
    
    if not isinstance(entity["fields"], dict):
        raise PayloadValidationError(
            f"fields must be a dictionary, got {type(entity['fields']).__name__}",
            path=f"{path_prefix}.fields"
        )


def validate_entity_type(entity_type: Any) -> str:
    """Validate entity_type parameter."""
    if not isinstance(entity_type, str):
        raise ValueError(f"entity_type must be a string, got {type(entity_type).__name__}")
    
    if not entity_type or not entity_type.strip():
        raise ValueError("entity_type cannot be empty")
    
    return entity_type.strip()


def validate_ruleset_id(ruleset_id: Any) -> str:
    """Validate ruleset_id parameter."""
    if not isinstance(ruleset_id, str):
        raise ValueError(f"ruleset_id must be a string, got {type(ruleset_id).__name__}")
    
    if not ruleset_id or not ruleset_id.strip():
        raise ValueError("ruleset_id cannot be empty")
    
    return ruleset_id.strip()


def validate_metadata(metadata: Any) -> dict[str, Any]:
    """Validate and normalize metadata.
    
    Ensures metadata is JSON-serializable for safe context passing.
    """
    if metadata is None:
        return {}
    
    if not isinstance(metadata, dict):
        raise ValueError(f"metadata must be a dictionary, got {type(metadata).__name__}")
    
    # Verify metadata is serializable to prevent runtime issues
    try:
        json.dumps(metadata, ensure_ascii=False)
    except (TypeError, ValueError) as e:
        raise ValueError(
            f"metadata must be JSON-serializable (no functions, classes, etc.). "
            f"Contains non-serializable objects: {e}"
        )
    
    return metadata
