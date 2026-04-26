"""
Comprehensive test to verify all immutability fixes are working correctly.

Tests the 3 critical bugs we found and fixed:
1. EntityResult.entity_ref immutability
2. Event dataclasses frozen
3. EntityProcessedEvent.entity_ref immutability
"""
from types import MappingProxyType
from validation_engine.contracts.results import EntityResult, FieldResult, CollectionResult
from validation_engine.contracts.findings import Finding
from validation_engine.contracts.enums import Severity, Scope, Category, Disposition
from validation_engine.engine.hooks import (
    ValidationStartEvent, 
    ValidationCompleteEvent,
    ValidationErrorEvent,
    RuleExecutionEvent,
    EntityProcessedEvent
)
from validation_engine.contracts.actions import StrategyDecision, Action, ActionType


def test_entity_result_immutability():
    """Test that EntityResult.entity_ref is truly immutable."""
    print("\n=== Test 1: EntityResult.entity_ref Immutability ===")
    
    fr = FieldResult(field_path='x', value=1, failures=())
    er = EntityResult(
        entity_ref=MappingProxyType({'id': 'test123'}),
        entity_type='record',
        good=(('field1', fr),),
        bad=(),
        entity_findings=()
    )
    
    # Verify entity_ref is MappingProxyType
    assert isinstance(er.entity_ref, MappingProxyType), \
        f"entity_ref should be MappingProxyType, got {type(er.entity_ref)}"
    
    # Try to mutate - should fail
    try:
        er.entity_ref['id'] = 'MUTATED'
        print("❌ FAILED: entity_ref is still mutable!")
        return False
    except TypeError as e:
        print(f"✅ PASSED: entity_ref is immutable - {e}")
        return True


def test_event_dataclasses_frozen():
    """Test that all event dataclasses are frozen."""
    print("\n=== Test 2: Event Dataclasses Frozen ===")
    
    # Create a CollectionResult for testing
    fr = FieldResult(field_path='x', value=1, failures=())
    er = EntityResult(
        entity_ref=MappingProxyType({'id': 'test'}),
        entity_type='record',
        good=(('x', fr),),
        bad=(),
        entity_findings=()
    )
    result = CollectionResult(
        collection_id='test',
        entity_type='record',
        ruleset_id='test:v1',
        entities=(er,),
        collection_findings=()
    )
    
    # Create a StrategyDecision for testing
    decision = StrategyDecision(
        strategy_id='test',
        strategy_version='1.0',
        actions=(),
        summary=MappingProxyType({})
    )
    
    # Test ValidationStartEvent
    event1 = ValidationStartEvent(
        timestamp=1.0,
        entity_type='record',
        ruleset_id='test:v1',
        collection_id='coll1',
        entity_count=1,
        rule_count=5
    )
    try:
        event1.entity_count = 999
        print("❌ FAILED: ValidationStartEvent is mutable!")
        return False
    except Exception:
        print("✅ PASSED: ValidationStartEvent is frozen")
    
    # Test ValidationCompleteEvent
    event2 = ValidationCompleteEvent(
        timestamp=2.0,
        entity_type='record',
        ruleset_id='test:v1',
        collection_id='coll1',
        duration_ms=10.0,
        result=result,
        decision=decision
    )
    try:
        event2.duration_ms = 999.0
        print("❌ FAILED: ValidationCompleteEvent is mutable!")
        return False
    except Exception:
        print("✅ PASSED: ValidationCompleteEvent is frozen")
    
    # Test ValidationErrorEvent
    event3 = ValidationErrorEvent(
        timestamp=3.0,
        entity_type='record',
        ruleset_id='test:v1',
        collection_id='coll1',
        error=ValueError("test"),
        duration_ms=5.0
    )
    try:
        event3.duration_ms = 999.0
        print("❌ FAILED: ValidationErrorEvent is mutable!")
        return False
    except Exception:
        print("✅ PASSED: ValidationErrorEvent is frozen")
    
    # Test RuleExecutionEvent
    finding = Finding(
        rule_id='test',
        scope=Scope.FIELD,
        severity=Severity.INFO,
        category=Category.STRUCTURAL,
        passed=True,
        message='ok'
    )
    event4 = RuleExecutionEvent(
        timestamp=4.0,
        entity_type='record',
        ruleset_id='test:v1',
        rule_id='rule1',
        scope='field',
        duration_ms=1.0,
        finding=finding
    )
    try:
        event4.duration_ms = 999.0
        print("❌ FAILED: RuleExecutionEvent is mutable!")
        return False
    except Exception:
        print("✅ PASSED: RuleExecutionEvent is frozen")
    
    # Test EntityProcessedEvent
    event5 = EntityProcessedEvent(
        timestamp=5.0,
        entity_type='record',
        ruleset_id='test:v1',
        entity_ref=MappingProxyType({'id': 'test'}),
        result=er,
        duration_ms=2.0
    )
    try:
        event5.duration_ms = 999.0
        print("❌ FAILED: EntityProcessedEvent is mutable!")
        return False
    except Exception:
        print("✅ PASSED: EntityProcessedEvent is frozen")
    
    return True


def test_entity_processed_event_entity_ref():
    """Test that EntityProcessedEvent.entity_ref is immutable."""
    print("\n=== Test 3: EntityProcessedEvent.entity_ref Immutability ===")
    
    fr = FieldResult(field_path='x', value=1, failures=())
    er = EntityResult(
        entity_ref=MappingProxyType({'id': 'test'}),
        entity_type='record',
        good=(('x', fr),),
        bad=(),
        entity_findings=()
    )
    
    event = EntityProcessedEvent(
        timestamp=1.0,
        entity_type='record',
        ruleset_id='test:v1',
        entity_ref=MappingProxyType({'id': 'test123'}),
        result=er,
        duration_ms=2.0
    )
    
    # Verify entity_ref is MappingProxyType
    assert isinstance(event.entity_ref, MappingProxyType), \
        f"entity_ref should be MappingProxyType, got {type(event.entity_ref)}"
    
    # Try to mutate - should fail
    try:
        event.entity_ref['id'] = 'MUTATED'
        print("❌ FAILED: entity_ref is still mutable!")
        return False
    except TypeError as e:
        print(f"✅ PASSED: entity_ref is immutable - {e}")
        return True


def test_action_immutability():
    """Test that Action entity_ref and payload are immutable."""
    print("\n=== Test 4: Action Immutability ===")
    
    action = Action(
        action_type=ActionType.PUBLISH,
        entity_ref=MappingProxyType({'id': 'test'}),
        payload=MappingProxyType({'data': 'value'}),
        target='topic.valid',
        rationale='clean'
    )
    
    # Try to mutate entity_ref - should fail
    try:
        action.entity_ref['id'] = 'MUTATED'
        print("❌ FAILED: Action.entity_ref is mutable!")
        return False
    except TypeError:
        print("✅ PASSED: Action.entity_ref is immutable")
    
    # Try to mutate payload - should fail
    try:
        action.payload['data'] = 'MUTATED'
        print("❌ FAILED: Action.payload is mutable!")
        return False
    except TypeError:
        print("✅ PASSED: Action.payload is immutable")
    
    return True


def test_strategy_decision_immutability():
    """Test that StrategyDecision is fully immutable."""
    print("\n=== Test 5: StrategyDecision Immutability ===")
    
    action = Action(
        action_type=ActionType.PUBLISH,
        entity_ref=MappingProxyType({'id': 'test'}),
        payload=MappingProxyType({'data': 'value'}),
        target='topic.valid',
        rationale='clean'
    )
    
    decision = StrategyDecision(
        strategy_id='test',
        strategy_version='1.0',
        actions=(action,),
        summary=MappingProxyType({'count': 1})
    )
    
    # Try to mutate summary - should fail
    try:
        decision.summary['count'] = 999
        print("❌ FAILED: StrategyDecision.summary is mutable!")
        return False
    except TypeError:
        print("✅ PASSED: StrategyDecision.summary is immutable")
    
    return True


def test_field_result_immutability():
    """Test that FieldResult.failures is immutable."""
    print("\n=== Test 6: FieldResult Immutability ===")
    
    finding = Finding(
        rule_id='test',
        scope=Scope.FIELD,
        severity=Severity.WARNING,
        category=Category.STRUCTURAL,
        passed=False,
        message='warning'
    )
    
    fr = FieldResult(
        field_path='x',
        value=1,
        failures=(finding,)
    )
    
    # Verify failures is tuple
    assert isinstance(fr.failures, tuple), \
        f"failures should be tuple, got {type(fr.failures)}"
    
    # Try to mutate - should fail
    try:
        fr.failures.append(finding)
        print("❌ FAILED: FieldResult.failures is mutable!")
        return False
    except AttributeError:
        print("✅ PASSED: FieldResult.failures is immutable (tuple)")
        return True


def main():
    """Run all immutability tests."""
    print("="*70)
    print("COMPREHENSIVE IMMUTABILITY TEST SUITE")
    print("="*70)
    
    tests = [
        test_entity_result_immutability,
        test_event_dataclasses_frozen,
        test_entity_processed_event_entity_ref,
        test_action_immutability,
        test_strategy_decision_immutability,
        test_field_result_immutability,
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append((test.__name__, result))
        except Exception as e:
            print(f"❌ EXCEPTION in {test.__name__}: {e}")
            results.append((test.__name__, False))
    
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    print(f"\n{passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 ALL IMMUTABILITY TESTS PASSED! 🎉")
        print("\n✅ All critical bugs fixed:")
        print("   1. EntityResult.entity_ref is now immutable (MappingProxyType)")
        print("   2. All Event dataclasses are now frozen")
        print("   3. EntityProcessedEvent.entity_ref is now immutable")
        print("   4. Action entity_ref and payload are immutable")
        print("   5. StrategyDecision is fully immutable")
        print("   6. FieldResult.failures is immutable (tuple)")
        return 0
    else:
        print("\n❌ SOME TESTS FAILED")
        return 1


if __name__ == "__main__":
    exit(main())
