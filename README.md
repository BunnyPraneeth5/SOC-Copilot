# SOC Copilot

A fully offline, desktop-based Security Operations Center (SOC) Copilot application using hybrid ML (Isolation Forest + Random Forest) for threat detection.

## Features

- **Hybrid ML Approach**: Isolation Forest for unsupervised anomaly detection + Random Forest for supervised attack classification
- **Fully Offline**: All inference runs locally on your machine
- **Modular Architecture**: Designed for future extensibility (Autoencoder, Transformer, etc.)
- **SOC Analyst Focused**: Every feature prioritizes analyst workflow and explainability

## Installation

```bash
pip install -e .
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
└── ui/                      # Presentation layer
```

## Configuration

Configuration files are in `config/`:
- `thresholds.yaml` - Alert thresholds
- `features.yaml` - Feature definitions
- `model_config.yaml` - Model parameters

## License

MIT
