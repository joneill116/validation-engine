"""
Example rules demonstrating validation engine capabilities.

These are generic, domain-agnostic rules showing common validation patterns.
Replace with your own domain-specific rules.
"""
from validation_engine import (
    Rule,
    Severity,
    Scope,
    Category,
    make_finding,
    EvaluationContext,
)


class RequiredFieldRule:
    """Ensures a field is present and non-empty."""
    
    rule_id = "required_field"
    scope = Scope.FIELD
    severity = Severity.BLOCKING
    category = Category.COMPLETENESS
    applies_to = {"*"}
    
    def __init__(self, field_name: str):
        """
        Initialize rule for a specific field.
        
        Args:
            field_name: Name of the field to check
        """
        self.field_path = field_name
        self.rule_id = f"required:{field_name}"
    
    def evaluate(self, target, ctx: EvaluationContext):
        """Check if field value is present and non-empty."""
        passed = target is not None and str(target).strip() != ""
        
        return make_finding(
            self,
            passed=passed,
            message=f"Field '{self.field_path}' is required" if not passed else "OK",
            field_path=self.field_path,
            actual=target,
        )


class EnumerationRule:
    """Validates field value against allowed enumeration."""
    
    rule_id = "enumeration"
    scope = Scope.FIELD
    severity = Severity.WARNING
    category = Category.STRUCTURAL
    applies_to = {"*"}
    
    def __init__(self, field_name: str, ref_data_key: str):
        """
        Initialize enumeration rule.
        
        Args:
            field_name: Name of the field to validate
            ref_data_key: Key in reference_data containing allowed values
        """
        self.field_path = field_name
        self.ref_data_key = ref_data_key
        self.rule_id = f"enum:{field_name}"
    
    def evaluate(self, target, ctx: EvaluationContext):
        """Check if value is in allowed enumeration."""
        allowed_values = ctx.reference_data.get(self.ref_data_key, [])
        passed = target in allowed_values
        
        return make_finding(
            self,
            passed=passed,
            message=(
                f"Value '{target}' not in allowed set {allowed_values}"
                if not passed else "OK"
            ),
            field_path=self.field_path,
            expected=allowed_values,
            actual=target,
        )


class RangeRule:
    """Validates numeric value is within range."""
    
    rule_id = "range_check"
    scope = Scope.FIELD
    severity = Severity.WARNING
    category = Category.BUSINESS
    applies_to = {"*"}
    
    def __init__(self, field_name: str, min_value: float, max_value: float):
        """
        Initialize range validation rule.
        
        Args:
            field_name: Name of numeric field
            min_value: Minimum allowed value (inclusive)
            max_value: Maximum allowed value (inclusive)
        """
        self.field_path = field_name
        self.min_value = min_value
        self.max_value = max_value
        self.rule_id = f"range:{field_name}"
    
    def evaluate(self, target, ctx: EvaluationContext):
        """Check if value is within min/max range."""
        try:
            value = float(target)
            passed = self.min_value <= value <= self.max_value
            
            return make_finding(
                self,
                passed=passed,
                message=(
                    f"Value {value} outside range [{self.min_value}, {self.max_value}]"
                    if not passed else "OK"
                ),
                field_path=self.field_path,
                expected=f"[{self.min_value}, {self.max_value}]",
                actual=value,
            )
        except (TypeError, ValueError):
            return make_finding(
                self,
                passed=False,
                message=f"Value '{target}' is not a valid number",
                field_path=self.field_path,
                actual=target,
            )


class FormatRule:
    """Validates field matches expected format pattern."""
    
    rule_id = "format_check"
    scope = Scope.FIELD
    severity = Severity.BLOCKING
    category = Category.STRUCTURAL
    applies_to = {"*"}
    
    def __init__(self, field_name: str, pattern: str, description: str = "expected format"):
        """
        Initialize format validation rule.
        
        Args:
            field_name: Name of field to validate
            pattern: Regex pattern to match
            description: Human-readable description of format
        """
        import re
        self.field_path = field_name
        self.pattern = re.compile(pattern)
        self.pattern_str = pattern
        self.description = description
        self.rule_id = f"format:{field_name}"
    
    def evaluate(self, target, ctx: EvaluationContext):
        """Check if value matches format pattern."""
        if target is None:
            return make_finding(
                self,
                passed=False,
                message=f"Field '{self.field_path}' is null",
                field_path=self.field_path,
            )
        
        passed = bool(self.pattern.match(str(target)))
        
        return make_finding(
            self,
            passed=passed,
            message=(
                f"Value '{target}' does not match {self.description}"
                if not passed else "OK"
            ),
            field_path=self.field_path,
            expected=self.description,
            actual=target,
        )


class ConsistencyRule:
    """Cross-field consistency validation."""
    
    rule_id = "consistency_check"
    scope = Scope.ENTITY
    severity = Severity.WARNING
    category = Category.CONSISTENCY
    field_path = "*"
    applies_to = {"*"}
    
    def __init__(self, field1: str, field2: str, rule_description: str):
        """
        Initialize consistency rule.
        
        Args:
            field1: First field name
            field2: Second field name
            rule_description: Description of consistency requirement
        """
        self.field1 = field1
        self.field2 = field2
        self.rule_description = rule_description
        self.rule_id = f"consistency:{field1}_{field2}"
    
    def evaluate(self, target, ctx: EvaluationContext):
        """Check consistency between two fields."""
        fields = target.get("fields", {})
        val1 = fields.get(self.field1)
        val2 = fields.get(self.field2)
        
        # Example: both present or both absent
        passed = (val1 is None) == (val2 is None)
        
        return make_finding(
            self,
            passed=passed,
            message=self.rule_description if not passed else "OK",
            involved_fields=(self.field1, self.field2),
        )


class UniquenessRule:
    """Collection-level uniqueness validation."""
    
    rule_id = "uniqueness_check"
    scope = Scope.COLLECTION
    severity = Severity.BLOCKING
    category = Category.UNIQUENESS
    field_path = "*"
    applies_to = {"*"}
    
    def __init__(self, field_name: str):
        """
        Initialize uniqueness rule.
        
        Args:
            field_name: Field that must be unique across collection
        """
        self.field_name = field_name
        self.rule_id = f"unique:{field_name}"
    
    def evaluate(self, target, ctx: EvaluationContext):
        """Check if field values are unique across all entities."""
        values = []
        duplicates = []
        
        for entity in target:
            fields = entity.get("fields", {})
            value = fields.get(self.field_name)
            
            if value is not None:
                if value in values:
                    duplicates.append(value)
                else:
                    values.append(value)
        
        passed = len(duplicates) == 0
        
        return make_finding(
            self,
            passed=passed,
            message=(
                f"Duplicate values found in '{self.field_name}': {set(duplicates)}"
                if not passed else "OK"
            ),
            field_path=self.field_name,
            actual=f"{len(duplicates)} duplicates" if duplicates else None,
        )


# Example usage
if __name__ == "__main__":
    from validation_engine import ValidationEngine, SeverityGateStrategy
    
    # Create rules
    rules = [
        RequiredFieldRule("id"),
        RequiredFieldRule("name"),
        EnumerationRule("status", "valid_statuses"),
        RangeRule("priority_score", 0, 100),
        FormatRule("code", r"^[A-Z]{3}-\d{4}$", "format AAA-9999"),
        ConsistencyRule("start_date", "end_date", "Both dates must be present or both absent"),
        UniquenessRule("id"),
    ]
    
    # Create engine
    engine = ValidationEngine(
        rules=rules,
        strategy=SeverityGateStrategy(
            publish_target="valid_queue",
            exception_target="invalid_queue",
        ),
        reference_data={
            "valid_statuses": ["active", "inactive", "pending"],
        },
    )
    
    # Example payload
    payload = {
        "entities": [
            {
                "entity_ref": {"id": "1"},
                "fields": {
                    "id": "001",
                    "name": "Example Record",
                    "status": "active",
                    "priority_score": 75,
                    "code": "ABC-1234",
                },
            },
        ]
    }
    
    # Validate
    decision = engine.validate(
        payload=payload,
        entity_type="record",
        ruleset_id="example:v1",
    )
    
    print(f"Actions: {len(decision.actions)}")
    print(f"Summary: {decision.summary}")
