# Platform-Specific Setup

## Linux / macOS Setup

### Quick Setup (Recommended)
```bash
chmod +x setup.sh
./setup.sh
```

This script will:
- Check Python 3.11+ availability
- Create virtual environment
- Install pytest and pyyaml
- Make scripts executable

### Manual Setup
```bash
# Create virtual environment
python3 -m venv .venv

# Activate it
source .venv/bin/activate

# Install dependencies
pip install pytest pyyaml

# Run validation
python3 run_validation.py config_equity.yaml sample_data.csv

# Run tests
python3 run_tests.py
```

### Make Scripts Executable (Optional)
```bash
chmod +x run_validation.py run_tests.py generate_rule_test.py
./run_validation.py config_equity.yaml sample_data.csv
./run_tests.py
```

## Windows Setup

### Using WSL (Windows Subsystem for Linux)
Follow the Linux instructions above.

### Native Windows
```powershell
# Create virtual environment
python -m venv .venv

# Activate it
.venv\Scripts\activate

# Install dependencies
pip install pytest pyyaml

# Run validation
python run_validation.py config_equity.yaml sample_data.csv

# Run tests
python run_tests.py
```

## Common Issues

### "python: command not found"
**Solution:** Use `python3` instead:
```bash
python3 run_validation.py config_equity.yaml sample_data.csv
```

### "externally-managed-environment" error
This occurs on Debian/Ubuntu when trying to install packages system-wide.

**Solution:** Use virtual environment (recommended):
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install pytest pyyaml
```

### "No module named pytest"
**Solution:** Install pytest:
```bash
# In virtual environment
pip install pytest pyyaml

# Or system-wide (not recommended)
pip3 install --user pytest pyyaml
```

### Permission denied when running scripts
**Solution:** Make executable:
```bash
chmod +x run_validation.py
./run_validation.py config_equity.yaml sample_data.csv
```

Or use python3 explicitly:
```bash
python3 run_validation.py config_equity.yaml sample_data.csv
```

## Verifying Installation

After setup, verify everything works:

```bash
# Test validation runs
python3 run_validation.py config_equity.yaml sample_data.csv

# Test suite runs
python3 run_tests.py

# Reference data loads
python3 -c "from validation_engine.reference import get_reference_data; print(get_reference_data()['valid_countries'][:5])"
```

Expected output:
```
✅ Valid: 7
❌ Invalid: 3
Results saved to: validation_results.json
```

## Development Environment

For active development:

```bash
# Activate virtual environment
source .venv/bin/activate  # Linux/macOS
.venv\Scripts\activate     # Windows

# Install in editable mode (optional)
pip install -e .

# Run validation without python3 prefix
python run_validation.py config_equity.yaml sample_data.csv

# Your shell prompt will show (.venv) when active
```

To deactivate:
```bash
deactivate
```

## Docker Setup (Advanced)

If you want to run in Docker:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python3", "run_validation.py", "config_equity.yaml", "sample_data.csv"]
```

Build and run:
```bash
docker build -t validation-engine .
docker run -v $(pwd)/data:/app/data validation-engine
```
