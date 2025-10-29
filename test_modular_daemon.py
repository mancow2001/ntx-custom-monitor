#!/usr/bin/env python3
"""
Test script for Nutanix SNMP Daemon (Modular Version)

This script tests the connection to Nutanix Prism Central and SNMP functionality
with the new modular structure and YAML configuration.
"""

import sys
import os
import yaml
import requests
import urllib3
from pysnmp.hlapi import *

# Add current directory to path for module imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config_manager import ConfigManager
from nutanix_api import NutanixAPIClient
from snmp_agent import SNMPAgent

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def test_config_loading(config_path=None):
    """Test configuration loading"""
    print("Testing configuration loading...")
    
    try:
        config_manager = ConfigManager(config_path)
        config = config_manager.to_dict()
        
        print("✓ Configuration loaded successfully")
        print(f"✓ Found sections: {list(config.keys())}")
        
        # Validate required sections
        required_sections = ['nutanix', 'snmp', 'daemon']
        for section in required_sections:
            if section in config:
                print(f"✓ Section '{section}' found")
            else:
                print(f"✗ Missing required section: {section}")
                return False, None
        
        return True, config
        
    except Exception as e:
        print(f"✗ Configuration loading failed: {e}")
        return False, None

def test_nutanix_connection(config):
    """Test connection to Nutanix Prism Central"""
    print("\nTesting Nutanix Prism Central connection...")
    
    try:
        nutanix_config = config['nutanix']
        api_client = NutanixAPIClient(nutanix_config)
        
        # Test basic connectivity
        if api_client.health_check():
            print("✓ Successfully connected to Prism Central")
            
            # Test data retrieval
            clusters = api_client.get_clusters()
            hosts = api_client.get_hosts()
            
            print(f"✓ Found {len(clusters)} clusters")
            print(f"✓ Found {len(hosts)} hosts")
            
            # Test stats retrieval for first cluster
            if clusters:
                cluster_uuid = clusters[0].get('metadata', {}).get('uuid')
                if cluster_uuid:
                    stats = api_client.get_cluster_stats(cluster_uuid)
                    if stats:
                        print("✓ Successfully retrieved cluster statistics")
                    else:
                        print("⚠ Cluster statistics not available")
            
            api_client.close()
            return True
        else:
            print("✗ Health check failed")
            return False
            
    except Exception as e:
        print(f"✗ Connection failed: {e}")
        return False

def test_snmp_configuration(config):
    """Test SNMP configuration"""
    print("\nTesting SNMP configuration...")
    
    try:
        snmp_config = config.get('snmp', {})
        
        # Validate SNMP keys
        auth_key = snmp_config.get('auth_key', '')
        priv_key = snmp_config.get('priv_key', '')
        
        if len(auth_key) < 8:
            print("✗ Authentication key too short (minimum 8 characters)")
            return False
        
        if len(priv_key) < 8:
            print("✗ Privacy key too short (minimum 8 characters)")
            return False
        
        print("✓ SNMP v3 keys are valid length")
        
        # Validate protocols
        auth_protocol = snmp_config.get('auth_protocol', 'MD5').upper()
        priv_protocol = snmp_config.get('priv_protocol', 'DES').upper()
        
        if auth_protocol in ['MD5', 'SHA']:
            print(f"✓ Authentication protocol: {auth_protocol}")
        else:
            print(f"⚠ Unknown authentication protocol: {auth_protocol}")
        
        if priv_protocol in ['DES', 'AES']:
            print(f"✓ Privacy protocol: {priv_protocol}")
        else:
            print(f"⚠ Unknown privacy protocol: {priv_protocol}")
        
        # Validate OID
        base_oid = snmp_config.get('base_oid', '')
        if base_oid and all(part.isdigit() for part in base_oid.split('.')):
            print(f"✓ Base OID format valid: {base_oid}")
        else:
            print(f"⚠ Base OID format may be invalid: {base_oid}")
        
        bind_ip = snmp_config.get('bind_ip', '0.0.0.0')
        bind_port = snmp_config.get('bind_port', 161)
        print(f"✓ SNMP agent configured for {bind_ip}:{bind_port}")
        
        return True
        
    except Exception as e:
        print(f"✗ SNMP configuration test failed: {e}")
        return False

def test_snmp_agent_creation(config):
    """Test SNMP agent creation (without starting)"""
    print("\nTesting SNMP agent creation...")
    
    try:
        # Create SNMP agent (but don't start it)
        snmp_agent = SNMPAgent(config)
        
        print("✓ SNMP agent created successfully")
        
        # Test OID tree building
        stats = snmp_agent.get_stats()
        print(f"✓ SNMP agent statistics: {stats}")
        
        return True
        
    except Exception as e:
        print(f"✗ SNMP agent creation failed: {e}")
        return False

def test_metrics_configuration(config):
    """Test metrics configuration"""
    print("\nTesting metrics configuration...")
    
    try:
        metrics_config = config.get('metrics', {})
        
        # Check cluster metrics
        cluster_metrics = metrics_config.get('cluster', {})
        enabled_cluster_metrics = [k for k, v in cluster_metrics.items() if v]
        print(f"✓ Cluster metrics enabled: {enabled_cluster_metrics}")
        
        # Check host metrics
        host_metrics = metrics_config.get('host', {})
        enabled_host_metrics = [k for k, v in host_metrics.items() if v]
        print(f"✓ Host metrics enabled: {enabled_host_metrics}")
        
        # Check VM metrics
        vm_metrics = metrics_config.get('vm', {})
        vm_enabled = vm_metrics.get('enabled', False)
        print(f"✓ VM metrics enabled: {vm_enabled}")
        
        return True
        
    except Exception as e:
        print(f"✗ Metrics configuration test failed: {e}")
        return False

def test_performance_settings(config):
    """Test performance settings"""
    print("\nTesting performance settings...")
    
    try:
        perf_config = config.get('performance', {})
        
        max_concurrent = perf_config.get('max_concurrent_requests', 10)
        cache_timeout = perf_config.get('cache_timeout', 30)
        pool_size = perf_config.get('connection_pool_size', 5)
        cache_enabled = perf_config.get('enable_metrics_cache', True)
        
        print(f"✓ Max concurrent requests: {max_concurrent}")
        print(f"✓ Cache timeout: {cache_timeout}s")
        print(f"✓ Connection pool size: {pool_size}")
        print(f"✓ Metrics cache enabled: {cache_enabled}")
        
        return True
        
    except Exception as e:
        print(f"✗ Performance settings test failed: {e}")
        return False

def test_permissions():
    """Test system permissions"""
    print("\nTesting system permissions...")
    
    import os
    
    # Check if running as root (needed for port 161)
    if os.geteuid() == 0:
        print("✓ Running as root (can bind to port 161)")
    else:
        print("⚠ Not running as root (cannot bind to port 161)")
        print("  Consider using a port > 1024 or running with sudo")
    
    # Check write permissions for log file
    try:
        log_file = "/var/log/nutanix_snmp_daemon.log"
        with open(log_file, 'a'):
            pass
        print(f"✓ Can write to log file: {log_file}")
    except PermissionError:
        print(f"✗ Cannot write to log file: {log_file}")
        print("  Run: sudo touch /var/log/nutanix_snmp_daemon.log")
        print("       sudo chown $USER /var/log/nutanix_snmp_daemon.log")
    except Exception:
        print(f"⚠ Log file test skipped (file system constraints)")

def create_sample_config():
    """Create a sample configuration file for testing"""
    sample_config = {
        'nutanix': {
            'prism_central_ip': '10.1.1.100',
            'username': 'admin',
            'password': 'nutanix/4u',
            'port': 9440,
            'ssl_verify': False,
            'timeout': 30
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
            'log_file': '/var/log/nutanix_snmp_daemon.log'
        },
        'metrics': {
            'cluster': {
                'cpu_usage': True,
                'memory_usage': True,
                'io_latency': True,
                'io_bandwidth': True,
                'iops': True
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
                'enabled': False
            }
        },
        'performance': {
            'max_concurrent_requests': 10,
            'cache_timeout': 30,
            'enable_metrics_cache': True
        }
    }
    
    config_file = './test_config.yaml'
    with open(config_file, 'w') as f:
        yaml.dump(sample_config, f, default_flow_style=False, indent=2)
    
    print(f"Sample configuration created: {config_file}")
    return config_file

def main():
    """Main test function"""
    print("Nutanix SNMP Daemon Test Script (Modular Version)")
    print("=" * 55)
    
    # Check for config file argument
    config_path = None
    if len(sys.argv) > 1:
        config_path = sys.argv[1]
    
    # If no config provided, create a sample one
    if not config_path:
        print("No configuration file specified. Creating sample configuration...")
        config_path = create_sample_config()
        print("Please edit the configuration file with your actual settings before running the daemon.")
        print()
    
    # Run tests
    success = True
    config = None
    
    # Test configuration loading
    config_success, config = test_config_loading(config_path)
    success &= config_success
    
    if not config:
        print("\n" + "=" * 55)
        print("✗ Cannot continue without valid configuration!")
        sys.exit(1)
    
    # Test individual components
    success &= test_metrics_configuration(config)
    success &= test_performance_settings(config)
    success &= test_snmp_configuration(config)
    success &= test_snmp_agent_creation(config)
    success &= test_nutanix_connection(config)
    
    # Test system permissions (informational)
    test_permissions()
    
    print("\n" + "=" * 55)
    if success:
        print("✓ All critical tests passed!")
        print("The modular daemon should work correctly with this configuration.")
        print()
        print("To start the daemon:")
        print(f"  python3 nutanix_snmp_daemon.py --config {config_path}")
    else:
        print("✗ Some tests failed!")
        print("Please fix the issues before running the daemon.")
        sys.exit(1)

if __name__ == "__main__":
    main()
