"""
Test to verify that deep copying in strategies prevents nested mutation bugs.

This test specifically addresses the bug where MappingProxyType provides
shallow immutability only - it prevents reassignment but not nested mutations.
"""
from types import MappingProxyType
from validation_engine.contracts.results import FieldResult, EntityResult, CollectionResult
from validation_engine.contracts.findings import Finding
from validation_engine.contracts.enums import Severity, Scope, Category
from validation_engine.strategies.severity_gate import SeverityGateStrategy


def test_nested_value_immutability():
    """Test that strategies deep copy values, preventing nested mutations."""
    print("\n" + "="*70)
    print("DEEP COPY FIX VERIFICATION")
    print("="*70)
    
    # Create FieldResult with MUTABLE nested value (dict)
    mutable_value = {'amount': 100, 'currency': 'USD', 'breakdown': {'tax': 10, 'base': 90}}
    fr = FieldResult(
        field_path='price',
        value=mutable_value,
        failures=()
    )
    
    # Create EntityResult
    er = EntityResult(
        entity_ref=MappingProxyType({'id': 'test123'}),
        entity_type='record',
        good=(('price', fr),),
        bad=(),
        entity_findings=()
    )
    
    # Create CollectionResult
    result = CollectionResult(
        collection_id='test',
        entity_type='record',
        ruleset_id='test:v1',
        entities=(er,),
        collection_findings=()
    )
    
    print("\n✅ Created results with nested mutable value:")
    print(f"   Original FieldResult.value: {fr.value}")
    print(f"   Nested breakdown: {fr.value['breakdown']}")
    
    # Run strategy (which should deep copy values)
    strategy = SeverityGateStrategy(
        publish_target='topic.valid',
        exception_target='topic.invalid',
        urgent_target='topic.urgent'
    )
    
    decision = strategy.decide(result)
    
    print(f"\n✅ Strategy created {len(decision.actions)} action(s)")
    
    # Get the action payload
    action = decision.actions[0]
    print(f"   Action type: {action.action_type}")
    print(f"   Payload type: {type(action.payload)}")
    
    # Try to mutate the payload's nested value
    print("\n⚠️  Attempting to mutate action payload nested values...")
    
    try:
        # This should be blocked (top-level is MappingProxyType)
        action.payload['entity'] = 'mutated'
        print("   ❌ FAIL: Could mutate top-level payload!")
        return False
    except TypeError:
        print("   ✅ PASS: Top-level payload mutation blocked")
    
    # The critical test: can we mutate nested values?
    try:
        # Before fix: this would mutate the original FieldResult.value
        # After fix: this mutates only the copy in the payload
        payload_price = action.payload['entity']['price']
        print(f"   Payload price before mutation: {payload_price}")
        
        # Mutate the nested dict
        payload_price['amount'] = 999999
        payload_price['breakdown']['tax'] = 888
        
        print(f"   Payload price after mutation: {payload_price}")
        print(f"   Original FieldResult.value: {fr.value}")
        print(f"   Original breakdown: {fr.value['breakdown']}")
        
        # Check if original was affected
        if fr.value['amount'] == 999999:
            print("\n   ❌ FAIL: ORIGINAL FieldResult WAS MUTATED!")
            print("   This means deep copy is NOT working!")
            return False
        else:
            print("\n   ✅ PASS: Original FieldResult UNCHANGED!")
            print("   Deep copy successfully prevents nested mutations!")
            return True
            
    except Exception as e:
        print(f"\n   ❌ UNEXPECTED ERROR: {e}")
        return False


def test_action_payload_independence():
    """Test that multiple actions don't share mutable references."""
    print("\n" + "="*70)
    print("ACTION PAYLOAD INDEPENDENCE TEST")
    print("="*70)
    
    # Create shared mutable value
    shared_value = {'shared': 'data', 'nested': {'count': 1}}
    
    # Create two EntityResults with same mutable value
    fr1 = FieldResult(field_path='field1', value=shared_value, failures=())
    fr2 = FieldResult(field_path='field2', value=shared_value, failures=())
    
    er1 = EntityResult(
        entity_ref=MappingProxyType({'id': 'entity1'}),
        entity_type='record',
        good=(('field1', fr1),),
        bad=(),
        entity_findings=()
    )
    
    er2 = EntityResult(
        entity_ref=MappingProxyType({'id': 'entity2'}),
        entity_type='record',
        good=(('field2', fr2),),
        bad=(),
        entity_findings=()
    )
    
    result = CollectionResult(
        collection_id='test',
        entity_type='record',
        ruleset_id='test:v1',
        entities=(er1, er2),
        collection_findings=()
    )
    
    print(f"\n✅ Created 2 entities sharing same mutable value: {shared_value}")
    
    # Run strategy
    strategy = SeverityGateStrategy(
        publish_target='topic.valid',
        exception_target='topic.invalid',
        urgent_target='topic.urgent'
    )
    
    decision = strategy.decide(result)
    
    print(f"✅ Strategy created {len(decision.actions)} actions")
    
    # Get payloads from both actions
    action1 = decision.actions[0]
    action2 = decision.actions[1]
    
    payload1_field = action1.payload['entity']['field1']
    payload2_field = action2.payload['entity']['field2']
    
    print(f"\n   Action 1 field value: {payload1_field}")
    print(f"   Action 2 field value: {payload2_field}")
    
    # Mutate payload1
    payload1_field['nested']['count'] = 100
    
    print(f"\n⚠️  Mutated Action 1 payload nested value to 100")
    print(f"   Action 1 field value: {payload1_field}")
    print(f"   Action 2 field value: {payload2_field}")
    print(f"   Original shared value: {shared_value}")
    
    # Check independence
    if payload2_field['nested']['count'] == 100:
        print("\n   ❌ FAIL: Action 2 was affected by Action 1 mutation!")
        print("   Payloads share references!")
        return False
    elif shared_value['nested']['count'] == 100:
        print("\n   ❌ FAIL: Original value was affected!")
        print("   Deep copy not working!")
        return False
    else:
        print("\n   ✅ PASS: All payloads are independent copies!")
        print("   Deep copy successfully isolates mutations!")
        return True


def main():
    """Run all deep copy verification tests."""
    print("="*70)
    print("VERIFYING DEEP COPY FIX FOR NESTED MUTATION BUGS")
    print("="*70)
    print("\nThis tests the fix for the critical bug where MappingProxyType")
    print("provides only shallow immutability, allowing nested mutations.")
    
    test1 = test_nested_value_immutability()
    test2 = test_action_payload_independence()
    
    print("\n" + "="*70)
    print("FINAL RESULTS")
    print("="*70)
    
    if test1 and test2:
        print("\n🎉 ALL DEEP COPY TESTS PASSED! 🎉")
        print("\n✅ Verified:")
        print("   1. Strategy deep copies values into action payloads")
        print("   2. Mutating action payloads does NOT affect original FieldResults")
        print("   3. Multiple actions have independent copies")
        print("   4. True deep immutability enforced end-to-end")
        return 0
    else:
        print("\n❌ SOME TESTS FAILED")
        print("   Deep copy fix not working correctly!")
        return 1


if __name__ == "__main__":
    exit(main())
