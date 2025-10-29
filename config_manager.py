#!/usr/bin/env python3
"""
Configuration Manager Module

Handles loading and validation of YAML configuration files.
"""

import os
import yaml
import logging
from typing import Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

class ConfigManager:
    """Manages configuration loading and validation"""
    
    DEFAULT_CONFIG_PATHS = [
        "/etc/nutanix_snmp_daemon/config.yaml",
        "/etc/nutanix_snmp_daemon.yaml",
        "./config.yaml",
        "~/.nutanix_snmp_daemon.yaml"
    ]
    
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path
        self.config: Dict[str, Any] = {}
        self._load_config()
        self._validate_config()
    
    def _find_config_file(self) -> str:
        """Find the configuration file in default locations"""
        if self.config_path:
            if os.path.exists(self.config_path):
                return self.config_path
            else:
                raise FileNotFoundError(f"Configuration file not found: {self.config_path}")
        
        # Search in default locations
        for path in self.DEFAULT_CONFIG_PATHS:
            expanded_path = os.path.expanduser(path)
            if os.path.exists(expanded_path):
                return expanded_path
        
        raise FileNotFoundError(f"Configuration file not found in any of: {self.DEFAULT_CONFIG_PATHS}")
    
    def _load_config(self):
        """Load configuration from YAML file"""
        config_file = self._find_config_file()
        
        try:
            with open(config_file, 'r') as f:
                self.config = yaml.safe_load(f)
            logger.info(f"Configuration loaded from: {config_file}")
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML configuration: {e}")
        except Exception as e:
            raise RuntimeError(f"Failed to load configuration: {e}")
    
    def _validate_config(self):
        """Validate required configuration parameters"""
        required_sections = ['nutanix', 'snmp', 'daemon']
        
        for section in required_sections:
            if section not in self.config:
                raise ValueError(f"Missing required configuration section: {section}")
        
        # Validate Nutanix section
        nutanix_required = ['prism_central_ip', 'username', 'password']
        for field in nutanix_required:
            if field not in self.config['nutanix']:
                raise ValueError(f"Missing required Nutanix field: {field}")
        
        # Validate SNMP section
        snmp_required = ['username', 'auth_key', 'priv_key']
        for field in snmp_required:
            if field not in self.config['snmp']:
                raise ValueError(f"Missing required SNMP field: {field}")
        
        # Validate key lengths
        if len(self.config['snmp']['auth_key']) < 8:
            raise ValueError("SNMP authentication key must be at least 8 characters")
        
        if len(self.config['snmp']['priv_key']) < 8:
            raise ValueError("SNMP privacy key must be at least 8 characters")
        
        logger.info("Configuration validation passed")
    
    def get(self, key_path: str, default: Any = None) -> Any:
        """
        Get configuration value using dot notation
        Example: get('nutanix.prism_central_ip')
        """
        keys = key_path.split('.')
        value = self.config
        
        try:
            for key in keys:
                value = value[key]
            return value
        except (KeyError, TypeError):
            return default
    
    def get_section(self, section: str) -> Dict[str, Any]:
        """Get entire configuration section"""
        return self.config.get(section, {})
    
    def set(self, key_path: str, value: Any):
        """
        Set configuration value using dot notation
        Example: set('daemon.log_level', 'DEBUG')
        """
        keys = key_path.split('.')
        config_ref = self.config
        
        # Navigate to the parent of the target key
        for key in keys[:-1]:
            if key not in config_ref:
                config_ref[key] = {}
            config_ref = config_ref[key]
        
        # Set the value
        config_ref[keys[-1]] = value
    
    def save(self, output_path: Optional[str] = None):
        """Save configuration to file"""
        save_path = output_path or self.config_path or self.DEFAULT_CONFIG_PATHS[0]
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        
        try:
            with open(save_path, 'w') as f:
                yaml.dump(self.config, f, default_flow_style=False, indent=2)
            logger.info(f"Configuration saved to: {save_path}")
        except Exception as e:
            raise RuntimeError(f"Failed to save configuration: {e}")
    
    def reload(self):
        """Reload configuration from file"""
        self._load_config()
        self._validate_config()
        logger.info("Configuration reloaded")
    
    def to_dict(self) -> Dict[str, Any]:
        """Return configuration as dictionary"""
        return self.config.copy()
    
    def update(self, updates: Dict[str, Any]):
        """Update configuration with new values"""
        def deep_update(base_dict: Dict, update_dict: Dict):
            for key, value in update_dict.items():
                if key in base_dict and isinstance(base_dict[key], dict) and isinstance(value, dict):
                    deep_update(base_dict[key], value)
                else:
                    base_dict[key] = value
        
        deep_update(self.config, updates)
        self._validate_config()
    
    @classmethod
    def create_default_config(cls, output_path: str):
        """Create a default configuration file"""
        default_config = {
            'nutanix': {
                'prism_central_ip': '10.1.1.100',
                'username': 'admin',
                'password': 'password',
                'port': 9440,
                'ssl_verify': False,
                'timeout': 30,
                'retry_count': 3,
                'retry_delay': 5
            },
            'snmp': {
                'bind_ip': '0.0.0.0',
                'bind_port': 161,
                'username': 'nutanix_monitor',
                'auth_key': 'AuthenticationKey123!',
                'priv_key': 'PrivacyKey123!',
                'auth_protocol': 'MD5',
                'priv_protocol': 'DES',
                'base_oid': '1.3.6.1.4.1.99999.1'
            },
            'daemon': {
                'collection_interval': 60,
                'log_level': 'INFO',
                'log_file': '/var/log/nutanix_snmp_daemon.log',
                'pid_file': '/var/run/nutanix_snmp_daemon.pid',
                'user': 'nutanix-snmp',
                'group': 'nutanix-snmp'
            },
            'metrics': {
                'cluster': {
                    'cpu_usage': True,
                    'memory_usage': True,
                    'io_latency': True,
                    'io_bandwidth': True,
                    'iops': True,
                    'read_latency': True,
                    'write_latency': True
                },
                'host': {
                    'cpu_usage': True,
                    'memory_usage': True,
                    'io_latency': True,
                    'io_bandwidth': True,
                    'iops': True,
                    'vm_count': True
                },
                'vm': {
                    'enabled': False,
                    'cpu_usage': True,
                    'memory_usage': True,
                    'disk_usage': True
                }
            },
            'performance': {
                'max_concurrent_requests': 10,
                'cache_timeout': 30,
                'connection_pool_size': 5,
                'enable_metrics_cache': True
            },
            'monitoring': {
                'enable_health_checks': True,
                'health_check_interval': 300,
                'alert_on_connection_failure': True,
                'alert_threshold_cpu': 90,
                'alert_threshold_memory': 90,
                'alert_threshold_latency': 100
            },
            'security': {
                'enable_ssl_verification': False,
                'cert_file': '',
                'key_file': '',
                'ca_file': '',
                'allowed_snmp_clients': []
            },
            'sdk': {
                'enable_clustermgmt': True,
                'enable_vmm': True,
                'enable_prism': True,
                'enable_networking': False,
                'enable_volumes': False,
                'enable_opsmgmt': False,
                'stats': {
                    'enabled': True,
                    'time_range_minutes': 5,
                    'stat_type': 'AVG',
                    'default_page_size': 1000
                },
                'rate_limiting': {
                    'enable_backoff': True,
                    'max_requests_per_minute': 300,
                    'retry_on_rate_limit': True,
                    'backoff_multiplier': 2,
                    'max_retry_delay': 60
                }
            },
            'debug': {
                'enable_api_logging': False,
                'enable_snmp_debugging': False,
                'enable_sdk_debug': False,
                'dump_raw_metrics': False,
                'test_mode': False
            }
        }
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        with open(output_path, 'w') as f:
            yaml.dump(default_config, f, default_flow_style=False, indent=2)
        
        print(f"Default configuration created at: {output_path}")
