"""
Configuration Loader

Loads and validates configuration from YAML files with environment variable support.
"""
import os
import yaml
import logging
from typing import Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)


class ConfigLoader:
    """Configuration loader with environment variable substitution"""
    
    def __init__(self, config_path: str):
        """
        Initialize config loader
        
        Args:
            config_path: Path to YAML configuration file
        """
        self.config_path = config_path
        self.config: Dict[str, Any] = {}
    
    def load(self) -> Dict[str, Any]:
        """
        Load configuration from file
        
        Returns:
            Configuration dictionary
        """
        if not Path(self.config_path).exists():
            raise FileNotFoundError(f"Configuration file not found: {self.config_path}")
        
        with open(self.config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        
        # Substitute environment variables
        self.config = self._substitute_env_vars(self.config)
        
        # Validate configuration
        self._validate()
        
        logger.info(f"Loaded configuration from {self.config_path}")
        return self.config
    
    def _substitute_env_vars(self, config: Any) -> Any:
        """
        Recursively substitute environment variables in config
        
        Args:
            config: Configuration value (dict, list, or string)
            
        Returns:
            Configuration with substituted values
        """
        if isinstance(config, dict):
            return {k: self._substitute_env_vars(v) for k, v in config.items()}
        elif isinstance(config, list):
            return [self._substitute_env_vars(item) for item in config]
        elif isinstance(config, str):
            # Check for ${VAR} pattern
            if config.startswith("${") and config.endswith("}"):
                var_name = config[2:-1]
                return os.environ.get(var_name, config)
            return config
        else:
            return config
    
    def _validate(self) -> None:
        """Validate required configuration fields"""
        required_fields = [
            ("can", "interface"),
            ("vehicle", "vin"),
            ("vehicle", "gateway_id")
        ]
        
        for field_path in required_fields:
            value = self.config
            for key in field_path:
                if key not in value:
                    raise ValueError(f"Missing required configuration: {'.'.join(field_path)}")
                value = value[key]
        
        logger.info("Configuration validated successfully")
