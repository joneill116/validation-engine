"""
Comprehensive test for enhanced validation engine features.

Tests new features:
- Input validation
- Caching
- Hooks/observability
- Enhanced error handling
- Logging
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from validation_engine import (
    ValidationEngine,
    SeverityGateStrategy,
    ValidationHooks,
    RuleCache,
    PayloadValidationError,
    Severity,
    Scope,
    Category,
    make_finding,
    EvaluationContext,
)


# Sample rule for testing
class SampleRule:
    rule_id = "sample_rule"
    scope = Scope.FIELD
    severity = Severity.WARNING
    category = Category.STRUCTURAL
    field_path = "test_field"
    applies_to = {"*"}
    
    def evaluate(self, target, ctx):
        passed = target == "valid"
        return make_finding(
            self,
            passed=passed,
            message=f"Value is {'valid' if passed else 'invalid'}",
            field_path=self.field_path,
            actual=target,
        )


def test_input_validation():
    """Test that input validation catches malformed payloads."""
    print("\n=== Testing Input Validation ===")
    
    engine = ValidationEngine(
        rules=[SampleRule()],
        strategy=SeverityGateStrategy(
            publish_target="valid",
            exception_target="invalid",
        ),
    )
    
    # Test invalid payload - missing entities key
    try:
        engine.validate(
            payload={"invalid": "structure"},
            entity_type="test",
            ruleset_id="test:v1",
        )
        print("❌ FAILED: Should have raised PayloadValidationError")
        return False
    except PayloadValidationError as e:
        print(f"✅ PASSED: Caught invalid payload: {e}")
    
    # Test invalid payload - entities not a list
    try:
        engine.validate(
            payload={"entities": "not_a_list"},
            entity_type="test",
            ruleset_id="test:v1",
        )
        print("❌ FAILED: Should have raised PayloadValidationError")
        return False
    except PayloadValidationError as e:
        print(f"✅ PASSED: Caught invalid entities: {e}")
    
    # Test invalid entity_type
    try:
        engine.validate(
            payload={"entities": []},
            entity_type="",
            ruleset_id="test:v1",
        )
        print("❌ FAILED: Should have raised ValueError for empty entity_type")
        return False
    except ValueError as e:
        print(f"✅ PASSED: Caught empty entity_type: {e}")
    
    return True


def test_caching():
    """Test that caching improves performance."""
    print("\n=== Testing Caching ===")
    
    engine = ValidationEngine(
        rules=[SampleRule()],
        strategy=SeverityGateStrategy(
            publish_target="valid",
            exception_target="invalid",
        ),
        enable_cache=True,
        cache_size=100,
    )
    
    payload = {
        "entities": [
            {
                "entity_ref": {"id": "1"},
                "fields": {"test_field": "valid"},
            },
        ]
    }
    
    # First call - cache miss
    result1 = engine.validate(
        payload=payload,
        entity_type="test",
        ruleset_id="test:v1",
    )
    
    # Second call - should hit cache
    result2 = engine.validate(
        payload=payload,
        entity_type="test",
        ruleset_id="test:v1",
    )
    
    stats = engine.get_cache_stats()
    print(f"Cache stats: {stats}")
    
    if stats and stats["hits"] > 0:
        print(f"✅ PASSED: Cache hits={stats['hits']}, hit_rate={stats['hit_rate_percent']}%")
        return True
    else:
        print(f"⚠️  WARNING: Cache not working as expected: {stats}")
        return False


def test_hooks():
    """Test that lifecycle hooks are called."""
    print("\n=== Testing Hooks ===")
    
    events = []
    
    def on_start(event):
        events.append(("start", event.entity_count))
    
    def on_complete(event):
        events.append(("complete", event.duration_ms))
    
    def on_rule(event):
        events.append(("rule", event.rule_id))
    
    hooks = ValidationHooks()
    hooks.on_validation_start(on_start)
    hooks.on_validation_complete(on_complete)
    hooks.on_rule_execution(on_rule)
    
    engine = ValidationEngine(
        rules=[SampleRule()],
        strategy=SeverityGateStrategy(
            publish_target="valid",
            exception_target="invalid",
        ),
        hooks=hooks,
    )
    
    payload = {
        "entities": [
            {
                "entity_ref": {"id": "1"},
                "fields": {"test_field": "valid"},
            },
        ]
    }
    
    engine.validate(
        payload=payload,
        entity_type="test",
        ruleset_id="test:v1",
    )
    
    # Check that events were captured
    event_types = [e[0] for e in events]
    
    if "start" in event_types and "complete" in event_types and "rule" in event_types:
        print(f"✅ PASSED: All hooks fired. Events: {event_types}")
        return True
    else:
        print(f"❌ FAILED: Missing hook events. Got: {event_types}")
        return False


def test_frozen_context():
    """Test that EvaluationContext is immutable."""
    print("\n=== Testing Immutable Context ===")
    
    ctx = EvaluationContext(
        entity_type="test",
        ruleset_id="test:v1",
        rules_config_version="v1",
        reference_data={"key": "value"},
        metadata={"extra": "data"},
    )
    
    # Try to modify - should fail
    try:
        ctx.entity_type = "modified"
        print("❌ FAILED: Context should be immutable")
        return False
    except Exception as e:
        print(f"✅ PASSED: Context is immutable: {type(e).__name__}")
        return True


def test_enhanced_registry():
    """Test enhanced registry with better error messages."""
    print("\n=== Testing Enhanced Registry ===")
    
    from validation_engine import RuleRegistry, StrategyRegistry
    
    rule_reg = RuleRegistry()
    rule_reg.register("test", "v1", [SampleRule()])
    
    # Test successful retrieval
    rules = rule_reg.get("test", "v1")
    print(f"✅ Retrieved {len(rules)} rules")
    
    # Test error message for missing rules
    try:
        rules = rule_reg.get("missing", "v1")
        print("❌ FAILED: Should have raised KeyError")
        return False
    except KeyError as e:
        error_msg = str(e)
        if "Available:" in error_msg:
            print(f"✅ PASSED: Enhanced error message includes available keys")
        else:
            print(f"⚠️  WARNING: Error message could be better: {error_msg}")
    
    # Test list_keys
    keys = rule_reg.list_keys()
    print(f"✅ Registry has {len(keys)} key(s): {keys}")
    
    return True


def test_cache_class():
    """Test RuleCache directly."""
    print("\n=== Testing RuleCache ===")
    
    cache = RuleCache(max_size=3)
    
    # Create sample findings
    finding1 = make_finding(
        SampleRule(),
        passed=True,
        message="Test 1",
        field_path="field1",
    )
    finding2 = make_finding(
        SampleRule(),
        passed=False,
        message="Test 2",
        field_path="field2",
    )
    
    # Put entries
    cache.put("key1", finding1)
    cache.put("key2", finding2)
    
    # Get entries
    result1 = cache.get("key1")
    result2 = cache.get("key2")
    result3 = cache.get("key3")
    
    if result1 == finding1 and result2 == finding2 and result3 is None:
        print("✅ PASSED: Cache get/put works correctly")
    else:
        print("❌ FAILED: Cache not working correctly")
        return False
    
    # Check stats
    stats = cache.stats()
    print(f"Cache stats: {stats}")
    
    if stats["hits"] == 2 and stats["misses"] == 1:
        print("✅ PASSED: Cache stats tracking correctly")
    else:
        print(f"⚠️  WARNING: Cache stats unexpected: {stats}")
    
    # Test LRU eviction
    cache.put("key3", finding1)
    cache.put("key4", finding1)  # Should evict key1 (LRU)
    
    if cache.get("key1") is None and cache.get("key4") is not None:
        print("✅ PASSED: LRU eviction works")
    else:
        print("❌ FAILED: LRU eviction not working")
        return False
    
    return True


def run_all_tests():
    """Run all tests and report results."""
    print("\n" + "=" * 60)
    print("VALIDATION ENGINE - ENHANCED FEATURES TEST SUITE")
    print("=" * 60)
    
    tests = [
        ("Input Validation", test_input_validation),
        ("Caching", test_caching),
        ("Hooks", test_hooks),
        ("Immutable Context", test_frozen_context),
        ("Enhanced Registry", test_enhanced_registry),
        ("RuleCache", test_cache_class),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            passed = test_func()
            results.append((name, passed))
        except Exception as e:
            print(f"\n❌ EXCEPTION in {name}: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    passed_count = sum(1 for _, passed in results if passed)
    total_count = len(results)
    
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {name}")
    
    print(f"\n{passed_count}/{total_count} tests passed")
    
    if passed_count == total_count:
        print("\n🎉 ALL TESTS PASSED! 🎉")
        return 0
    else:
        print(f"\n⚠️  {total_count - passed_count} test(s) failed")
        return 1


if __name__ == "__main__":
    exit_code = run_all_tests()
    sys.exit(exit_code)
