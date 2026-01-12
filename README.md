# SOC Copilot

A fully offline, desktop-based Security Operations Center (SOC) Copilot application using hybrid ML (Isolation Forest + Random Forest) for threat detection.

## Features

- **Hybrid ML Approach**: Isolation Forest for unsupervised anomaly detection + Random Forest for supervised attack classification
- **Fully Offline**: All inference runs locally on your machine
- **Modular Architecture**: Designed for future extensibility (Autoencoder, Transformer, etc.)
- **SOC Analyst Focused**: Every feature prioritizes analyst workflow and explainability
- **Production Ready**: Robust error handling, empty state management, and cross-platform compatibility

## Quick Start

### Prerequisites

- Python 3.10 or higher
- 4GB+ RAM recommended
- Windows, macOS, or Linux

### Installation

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd "SOC Copilot"
   ```

2. **Run setup script**:
   ```bash
   python setup.py
   ```

3. **Check system requirements**:
   ```bash
   python check_requirements.py
   ```

4. **Train models** (if not already trained):
   ```bash
   python scripts/train_models.py
   ```

5. **Launch the application**:
   ```bash
   python launch_ui.py
   ```
   
   Or use the CLI:
   ```bash
   soc-copilot
   ```

### Manual Installation

If the setup script fails:

```bash
# Install dependencies
pip install -e .

# Create required directories
mkdir -p data/models data/logs logs/system

# Train models
python scripts/train_models.py

# Launch UI
python launch_ui.py
```

## Project Structure

```
src/
├── data/                    # Data layer
│   ├── log_ingestion/       # Log parsers and validators
│   ├── preprocessing/       # Data cleaning and normalization
│   └── feature_engineering/ # Feature extraction
├── models/                  # ML Core layer
│   ├── isolation_forest/    # Anomaly detection
│   ├── random_forest/       # Attack classification
│   └── ensemble_controller.py
├── intelligence/            # Intelligence layer
│   ├── alert_engine.py
│   └── context_enrichment.py
├── phase4/                  # Real-time processing
│   ├── ingestion/          # Log ingestion with micro-batching
│   ├── controller/         # Application orchestration
│   └── ui/                 # Desktop interface
└── ui/                      # Presentation layer
```

## Configuration

Configuration files are in `config/`:
- `thresholds.yaml` - Alert thresholds
- `features.yaml` - Feature definitions
- `model_config.yaml` - Model parameters
- `ingestion/system_logs.yaml` - Log ingestion settings

## Usage

### Desktop UI

Launch the desktop application:
```bash
python launch_ui.py
```

The UI provides:
- Real-time threat monitoring dashboard
- Live alerts table with priority-based coloring
- Detailed alert analysis and explainability
- System status and statistics

### Command Line

Analyze log files directly:
```bash
soc-copilot analyze /path/to/logfile.log
```

### Real-time Monitoring

The application can monitor:
- Individual log files (tail mode)
- Directories with pattern matching
- System logs (with proper permissions)

## Troubleshooting

### Common Issues

1. **Missing models error**:
   ```bash
   python scripts/train_models.py
   ```

2. **PyQt6 import error**:
   ```bash
   pip install PyQt6
   ```

3. **Permission errors**:
   - Ensure write access to `data/` and `logs/` directories
   - Run with appropriate permissions for system log access

4. **Memory issues**:
   - Ensure at least 4GB RAM available
   - Close other applications if needed

### System Requirements Check

Run the requirements checker:
```bash
python check_requirements.py
```

This will verify:
- Python version compatibility
- Required dependencies
- File structure
- Model availability
- System permissions

### Fresh Installation

For a completely fresh setup:
```bash
# Remove existing installation
rm -rf data/models data/logs

# Run setup
python setup.py

# Verify installation
python check_requirements.py
```

## Development

### Running Tests

```bash
# Run all tests
python -m pytest tests/

# Run specific test categories
python -m pytest tests/unit/
python -m pytest tests/integration/

# Run with coverage
python -m pytest tests/ --cov=soc_copilot
```

### Code Quality

```bash
# Format code
black src/ tests/

# Lint code
ruff src/ tests/

# Type checking
mypy src/
```

## Production Deployment

For production use:

1. **System Requirements**:
   - Dedicated machine with 8GB+ RAM
   - SSD storage for better I/O performance
   - Network access to log sources

2. **Security Considerations**:
   - Run with minimal required permissions
   - Isolate from internet access
   - Regular security updates

3. **Monitoring**:
   - Monitor application logs in `logs/`
   - Set up alerts for system failures
   - Regular model retraining

## License

MIT