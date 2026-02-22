"""Configuration management for singine."""

import os
from pathlib import Path
from typing import Optional
import configparser


class Config:
    """Manages singine configuration from ~/.singine/backend.config."""

    CONFIG_DIR = Path.home() / ".singine"
    CONFIG_FILE = CONFIG_DIR / "backend.config"

    def __init__(self):
        self.config = configparser.ConfigParser()
        self._load_config()

    def _load_config(self):
        """Load configuration from file."""
        if not self.CONFIG_FILE.exists():
            raise FileNotFoundError(
                f"Config file not found: {self.CONFIG_FILE}\n"
                f"Please create {self.CONFIG_FILE} with your Logseq environment settings."
            )

        self.config.read(self.CONFIG_FILE)

    def get_logseq_path(self) -> Path:
        """Get the Logseq graph directory path."""
        if not self.config.has_section('logseq'):
            raise ValueError("Config file missing [logseq] section")

        if not self.config.has_option('logseq', 'graph_path'):
            raise ValueError("Config file missing 'graph_path' in [logseq] section")

        path_str = self.config.get('logseq', 'graph_path')
        path = Path(path_str).expanduser()

        if not path.exists():
            raise FileNotFoundError(f"Logseq graph path does not exist: {path}")

        return path

    @classmethod
    def ensure_config_dir(cls):
        """Ensure the config directory exists."""
        cls.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
