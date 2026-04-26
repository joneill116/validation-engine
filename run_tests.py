#!/usr/bin/env python3
"""
Simple test runner for validation-engine tests.

Usage:
    python3 run_tests.py              # Run all tests
    python3 run_tests.py unit         # Run only unit tests
    python3 run_tests.py test_rules   # Run specific test file
    python3 run_tests.py -k country   # Run tests matching 'country'

Make executable (optional):
    chmod +x run_tests.py
    ./run_tests.py
"""
import sys
import subprocess
from pathlib import Path


def main():
    """Run pytest with appropriate arguments."""
    # Base command
    cmd = [sys.executable, "-m", "pytest"]
    
    # Parse arguments
    args = sys.argv[1:]
    
    if not args:
        # Default: run all tests with verbose output
        cmd.extend(["-v", "tests/"])
    elif args[0] == "unit":
        # Run only unit tests
        cmd.extend(["-v", "-m", "unit", "tests/"])
    elif args[0] == "integration":
        # Run only integration tests
        cmd.extend(["-v", "-m", "integration", "tests/"])
    elif args[0].startswith("test_"):
        # Run specific test file
        test_file = Path("tests") / f"{args[0]}.py"
        if not test_file.exists():
            test_file = Path("tests") / args[0]
        cmd.extend(["-v", str(test_file)])
    else:
        # Pass through all arguments
        cmd.extend(args)
        if "tests/" not in " ".join(args):
            cmd.append("tests/")
    
    # Run pytest
    print(f"Running: {' '.join(cmd)}")
    print("=" * 80)
    
    try:
        result = subprocess.run(cmd, check=False)
        return result.returncode
    except FileNotFoundError:
        print("\n❌ Error: pytest not found!")
        print("\nInstall dependencies:")
        print("  python3 -m venv .venv")
        print("  source .venv/bin/activate  # On Windows: .venv\\Scripts\\activate")
        print("  pip install pytest pyyaml")
        print("\nOr install system-wide (not recommended):")
        print("  pip3 install --user pytest pyyaml")
        return 1


if __name__ == "__main__":
    sys.exit(main())
