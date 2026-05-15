"""Model file integrity verification for SOC Copilot.

Generates and validates SHA-256 hashes for ML model files to detect
tampering or corruption before loading serialized model artifacts.
"""

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from soc_copilot.core.logging import get_logger
from soc_copilot.security.network import env_flag

logger = get_logger(__name__)


HASH_MANIFEST_FILENAME = "model_hashes.json"
HASH_ALGORITHM = "sha256"
BUFFER_SIZE = 65536
STRICT_INTEGRITY_ENV = "SOC_COPILOT_STRICT_MODEL_INTEGRITY"

REQUIRED_MODEL_FILES = [
    "isolation_forest_v1.joblib",
    "random_forest_v1.joblib",
    "feature_order.json",
    "label_map.json",
]


@dataclass
class IntegrityResult:
    """Result of model integrity verification."""

    is_valid: bool
    verified_files: list[str] = field(default_factory=list)
    failed_files: list[str] = field(default_factory=list)
    missing_files: list[str] = field(default_factory=list)
    error: Optional[str] = None


def strict_model_integrity_enabled() -> bool:
    """Whether missing hash manifests should fail model loading."""

    return env_flag(STRICT_INTEGRITY_ENV, default=False)


def compute_file_hash(filepath: Path) -> str:
    """Compute the SHA-256 hash of a file."""

    hasher = hashlib.new(HASH_ALGORITHM)
    with open(filepath, "rb") as f:
        while True:
            data = f.read(BUFFER_SIZE)
            if not data:
                break
            hasher.update(data)
    return hasher.hexdigest()


def generate_manifest(models_dir: str | Path) -> dict[str, str]:
    """Generate an integrity hash manifest for required model files."""

    models_path = Path(models_dir)
    if not models_path.exists():
        raise FileNotFoundError(f"Models directory not found: {models_path}")

    manifest = {}
    for filename in REQUIRED_MODEL_FILES:
        filepath = models_path / filename
        if filepath.exists():
            file_hash = compute_file_hash(filepath)
            manifest[filename] = file_hash
            logger.info("model_hash_generated", file=filename, hash=file_hash[:16] + "...")
        else:
            logger.warning("model_file_missing_for_manifest", file=filename)
    return manifest


def save_manifest(models_dir: str | Path, manifest: Optional[dict[str, str]] = None) -> Path:
    """Generate and save an integrity manifest to the models directory."""

    models_path = Path(models_dir)
    if manifest is None:
        manifest = generate_manifest(models_path)

    manifest_path = models_path / HASH_MANIFEST_FILENAME
    manifest_data = {"algorithm": HASH_ALGORITHM, "files": manifest}

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2)

    logger.info("manifest_saved", path=str(manifest_path), file_count=len(manifest))
    return manifest_path


def load_manifest(models_dir: str | Path) -> Optional[dict[str, str]]:
    """Load the integrity manifest from a model directory."""

    manifest_path = Path(models_dir) / HASH_MANIFEST_FILENAME
    if not manifest_path.exists():
        logger.warning("integrity_manifest_missing", path=str(manifest_path))
        return None

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("files", {})
    except (json.JSONDecodeError, OSError) as e:
        logger.error("manifest_load_failed", error=str(e))
        return None


def verify_model_file(model_path: str | Path, strict: Optional[bool] = None) -> IntegrityResult:
    """Verify one model artifact against the directory manifest before loading."""

    filepath = Path(model_path)
    strict_mode = strict_model_integrity_enabled() if strict is None else strict

    if not filepath.exists():
        return IntegrityResult(
            is_valid=False,
            missing_files=[filepath.name],
            error=f"Model file not found: {filepath}",
        )

    expected_hashes = load_manifest(filepath.parent)
    if expected_hashes is None:
        message = "Integrity manifest not found - verification skipped"
        logger.warning("model_file_integrity_skipped", file=filepath.name, strict=strict_mode)
        return IntegrityResult(
            is_valid=not strict_mode,
            error=message if not strict_mode else f"{message} in strict mode",
        )

    expected_hash = expected_hashes.get(filepath.name)
    if expected_hash is None:
        message = f"Model file '{filepath.name}' is not listed in integrity manifest"
        logger.warning("model_file_not_in_manifest", file=filepath.name, strict=strict_mode)
        return IntegrityResult(
            is_valid=not strict_mode,
            verified_files=[] if strict_mode else [filepath.name],
            error=message if strict_mode else f"{message} - verification skipped",
        )

    try:
        actual_hash = compute_file_hash(filepath)
    except OSError as e:
        return IntegrityResult(
            is_valid=False,
            failed_files=[filepath.name],
            error=f"Could not hash model file: {e}",
        )

    if actual_hash != expected_hash:
        logger.error(
            "model_file_integrity_violation",
            file=filepath.name,
            expected=expected_hash[:16] + "...",
            actual=actual_hash[:16] + "...",
        )
        return IntegrityResult(
            is_valid=False,
            failed_files=[filepath.name],
            error=f"Integrity check failed for {filepath.name}",
        )

    logger.info("model_file_verified", file=filepath.name)
    return IntegrityResult(is_valid=True, verified_files=[filepath.name])


def verify_models(models_dir: str | Path, strict: Optional[bool] = None) -> IntegrityResult:
    """Verify integrity of all model files listed in the stored manifest."""

    models_path = Path(models_dir)
    strict_mode = strict_model_integrity_enabled() if strict is None else strict

    if not models_path.exists():
        return IntegrityResult(
            is_valid=False,
            error=f"Models directory not found: {models_path}",
        )

    expected_hashes = load_manifest(models_path)
    if expected_hashes is None:
        logger.warning(
            "integrity_check_skipped",
            reason="No manifest found. Run build to generate model_hashes.json.",
            strict=strict_mode,
        )
        return IntegrityResult(
            is_valid=not strict_mode,
            error=(
                "Integrity manifest not found - verification skipped"
                if not strict_mode
                else "Integrity manifest not found in strict mode"
            ),
        )

    result = IntegrityResult(is_valid=True)
    for filename, expected_hash in expected_hashes.items():
        filepath = models_path / filename

        if not filepath.exists():
            result.missing_files.append(filename)
            result.is_valid = False
            logger.error("model_file_missing", file=filename)
            continue

        try:
            actual_hash = compute_file_hash(filepath)
        except OSError as e:
            result.failed_files.append(filename)
            result.is_valid = False
            logger.error("model_hash_failed", file=filename, error=str(e))
            continue

        if actual_hash != expected_hash:
            result.failed_files.append(filename)
            result.is_valid = False
            logger.error(
                "model_integrity_violation",
                file=filename,
                expected=expected_hash[:16] + "...",
                actual=actual_hash[:16] + "...",
            )
        else:
            result.verified_files.append(filename)
            logger.info("model_verified", file=filename)

    if result.is_valid:
        logger.info("all_models_verified", count=len(result.verified_files))
    else:
        result.error = (
            f"Integrity check failed: {len(result.failed_files)} tampered, "
            f"{len(result.missing_files)} missing"
        )
        logger.error("integrity_check_failed", details=result.error)

    return result
