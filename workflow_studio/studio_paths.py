"""Paths shared by model selection and the file panel."""
import os
from pathlib import Path


def model_directory():
    return Path(os.environ.get("WORKFLOW_MODELS_DIR", "models")).resolve()
