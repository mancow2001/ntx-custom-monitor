#!/usr/bin/env python3
"""
Test script for Nutanix SNMP Daemon (v4 SDK Version)

This script tests the connection to Nutanix Prism Central using the official v4 SDK
and SNMP functionality with the new modular structure and YAML configuration.
"""

import sys
import os
import yaml
import urllib3

# Add current directory to path for module imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config_manager import ConfigManager
from nutanix_api_v4 import NutanixAPIClient
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
        
        # Check for v4 SDK configuration
        if 'v4_sdk' in config:
            print("✓ v4 SDK configuration section found")
        else:
            print("⚠ v4 SDK configuration section not found (using defaults)")
        
        return True, config
        
    except Exception as e:
        print(f"✗ Configuration loading failed: {e}")
        return False, None

def test_v4_sdk_imports():
    """Test v4 SDK imports"""
    print("\nTesting v4 SDK imports...")
    
    try:
        # Test cluster management SDK
        from ntnx_clustermgmt_py_client import Configuration as ClusterMgmtConfig
        from ntnx_clustermgmt_py_client import ApiClient as ClusterMgmtApiClient
        from ntnx_clustermgmt_py_client.api.clusters_api import ClustersApi
        from ntnx_clustermgmt_py_client.api.hosts_api import HostsApi
        print("✓ Cluster Management SDK imported successfully")
        
        # Test VMM SDK
        from ntnx_vmm_py_client import Configuration as VmmConfig
        from ntnx_vmm_py_client import ApiClient as VmmApiClient
        from ntnx_vmm_py_client.api.vm_api import VmApi
        print("✓ VMM SDK imported successfully")
        
        # Test Prism SDK
        from ntnx_prism_py_client import Configuration as PrismConfig
        from ntnx_prism_py_client import ApiClient as PrismApiClient
        print("✓ Prism SDK imported successfully")
        
        return True
        
    except ImportError as e:
        print(f"✗ SDK import failed: {e}")
        print("Make sure you have installed the v4 SDK packages:")
        print("  pip install ntnx-clustermgmt-py-client ntnx-vmm-py-client ntnx-prism-py-client")
        return False
    except Exception as e:
        print(f"✗ Unexpected error during SDK import: {e}")
        return False

def test_nutanix_v4_connection(config):
    """Test connection to Nutanix Prism Central using v4 SDK"""
    print("\nTesting Nutanix Prism Central connection (v4 SDK)...")
    
    try:
        nutanix_config = config['nutanix']
        api_client = NutanixAPIClient(nutanix_config)
        
        # Test basic connectivity
        if api_client.health_check():
            print("✓ Successfully connected to Prism Central using v4 SDK")
            
            # Test data retrieval
            clusters = api_client.get_clusters()
            hosts = api_client.get_hosts()
            vms = api_client.get_vms()
            
            print(f"✓ Found {len(clusters)} clusters")
            print(f"✓ Found {len(hosts)} hosts")
            print(f"✓ Found {len(vms)} VMs")
            
            # Test stats retrieval for first cluster
            if clusters:
                cluster_uuid = clusters[0].get('metadata', {}).get('uuid')
                cluster_name = clusters[0].get('metadata', {}).get('name', 'Unknown')
                if cluster_uuid:
                    print(f"✓ Testing stats for cluster: {cluster_name}")
                    stats = api_client.get_cluster_stats(cluster_uuid)
                    if stats:
                        print("✓ Successfully retrieved cluster statistics using v4 SDK")
                        print(f"  Sample stats keys: {list(stats.keys())[:5]}")
                    else:
                        print("⚠ Cluster statistics not available (may not be supported)")
                else:
                    print("⚠ Cluster UUID not found")
            
            # Test stats retrieval for first host
            if hosts:
                host_uuid = hosts[0].get('metadata', {}).get('uuid')
                host_name = hosts[0].get('metadata', {}).get('name', 'Unknown')
                if host_uuid:
                    print(f"✓ Testing stats for host: {host_name}")
                    stats = api_client.get_host_stats(host_uuid)
                    if stats:
                        print("✓ Successfully retrieved host statistics using v4 SDK")
                        print(f"  Sample stats keys: {list(stats.keys())[:5]}")
                    else:
                        print("⚠ Host statistics not available (may not be supported)")
                else:
                    print("⚠ Host UUID not found")
            
            api_client.close()
            return True
        else:
            print("✗ Health check failed")
            return False
            
    except Exception as e:
        print(f"✗ Connection failed: {e}")
        print("This could be due to:")
        print("  - Incorrect credentials")
        print("  - Network connectivity issues")
        print("  - Prism Central not running v4 API compatible version")
        print("  - Firewall blocking connection")
        return False

def test_v4_sdk_configuration(config):
    """Test v4 SDK specific configuration"""
    print("\nTesting v4 SDK configuration...")
    
    try:
        v4_config = config.get('v4_sdk', {})
        
        # Check SDK namespace enablement
        namespaces = ['clustermgmt', 'vmm', 'prism', 'networking', 'volumes']
        enabled_namespaces = []
        for ns in namespaces:
            key = f"enable_{ns}"
            if v4_config.get(key, False):
                enabled_namespaces.append(ns)
        
        print(f"✓ Enabled SDK namespaces: {enabled_namespaces}")
        
        # Check statistics configuration
        stats_config = v4_config.get('stats', {})
        if stats_config.get('enabled', True):
            print("✓ Statistics collection enabled")
            print(f"  Time range: {stats_config.get('time_range_minutes', 5)} minutes")
            print(f"  Stat type: {stats_config.get('stat_type', 'AVG')}")
        else:
            print("⚠ Statistics collection disabled")
        
        # Check rate limiting configuration
        rate_config = v4_config.get('rate_limiting', {})
        if rate_config.get('enable_backoff', True):
            print("✓ Rate limiting backoff enabled")
            print(f"  Max requests per minute: {rate_config.get('max_requests_per_minute', 300)}")
        
        return True
        
    except Exception as e:
        print(f"✗ v4 SDK configuration test failed: {e}")
        return False

def test_sdk_version_compatibility():
    """Test SDK version compatibility"""
    print("\nTesting SDK version compatibility...")
    
    try:
        # Try to import and check versions
        import ntnx_clustermgmt_py_client
        import ntnx_vmm_py_client
        import ntnx_prism_py_client
        
        # Check if version attributes exist
        clustermgmt_version = getattr(ntnx_clustermgmt_py_client, '__version__', 'Unknown')
        vmm_version = getattr(ntnx_vmm_py_client, '__version__', 'Unknown')
        prism_version = getattr(ntnx_prism_py_client, '__version__', 'Unknown')
        
        print(f"✓ Cluster Management SDK version: {clustermgmt_version}")
        print(f"✓ VMM SDK version: {vmm_version}")
        print(f"✓ Prism SDK version: {prism_version}")
        
        # Check for major version compatibility
        for version, name in [(clustermgmt_version, 'clustermgmt'), (vmm_version, 'vmm'), (prism_version, 'prism')]:
            if version != 'Unknown' and version.startswith('4.'):
                print(f"✓ {name} SDK is v4 compatible")
            elif version != 'Unknown':
                print(f"⚠ {name} SDK version {version} may not be v4 compatible")
            else:
                print(f"⚠ {name} SDK version could not be determined")
        
        return True
        
    except Exception as e:
        print(f"✗ SDK version compatibility test failed: {e}")
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

def create_sample_v4_config():
    """Create a sample configuration file for v4 SDK testing"""
    sample_config = {
        'nutanix': {
            'prism_central_ip': '10.1.1.100',
            'username': 'admin',
            'password': 'nutanix/4u',
            'port': 9440,
            'ssl_verify': False,
            'timeout': 30,
            'connection_pool_size': 5
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
        },
        'v4_sdk': {
            'enable_clustermgmt': True,
            'enable_vmm': True,
            'enable_prism': True,
            'enable_networking': False,
            'enable_volumes': False,
            'stats': {
                'enabled': True,
                'time_range_minutes': 5,
                'stat_type': 'AVG',
                'default_page_size': 1000
            },
            'rate_limiting': {
                'enable_backoff': True,
                'max_requests_per_minute': 300,
                'retry_on_rate_limit': True
            }
        }
    }
    
    config_file = './test_config_v4.yaml'
    with open(config_file, 'w') as f:
        yaml.dump(sample_config, f, default_flow_style=False, indent=2)
    
    print(f"Sample v4 SDK configuration created: {config_file}")
    return config_file

def main():
    """Main test function"""
    print("Nutanix SNMP Daemon Test Script (v4 SDK Version)")
    print("=" * 55)
    
    # Check for config file argument
    config_path = None
    if len(sys.argv) > 1:
        config_path = sys.argv[1]
    
    # If no config provided, create a sample one
    if not config_path:
        print("No configuration file specified. Creating sample v4 SDK configuration...")
        config_path = create_sample_v4_config()
        print("Please edit the configuration file with your actual settings before running the daemon.")
        print()
    
    # Run tests
    success = True
    config = None
    
    # Test v4 SDK imports first
    sdk_import_success = test_v4_sdk_imports()
    success &= sdk_import_success
    
    if not sdk_import_success:
        print("\n" + "=" * 55)
        print("✗ Cannot continue without v4 SDK packages!")
        print("Please install the required packages:")
        print("  pip install ntnx-clustermgmt-py-client ntnx-vmm-py-client ntnx-prism-py-client")
        sys.exit(1)
    
    # Test configuration loading
    config_success, config = test_config_loading(config_path)
    success &= config_success
    
    if not config:
        print("\n" + "=" * 55)
        print("✗ Cannot continue without valid configuration!")
        sys.exit(1)
    
    # Test individual components
    success &= test_sdk_version_compatibility()
    success &= test_v4_sdk_configuration(config)
    success &= test_snmp_configuration(config)
    success &= test_snmp_agent_creation(config)
    success &= test_nutanix_v4_connection(config)
    
    # Test system permissions (informational)
    test_permissions()
    
    print("\n" + "=" * 55)
    if success:
        print("✓ All critical tests passed!")
        print("The v4 SDK daemon should work correctly with this configuration.")
        print()
        print("To start the daemon:")
        print(f"  python3 nutanix_snmp_daemon_v4.py --config {config_path}")
        print()
        print("Migration notes:")
        print("- The daemon now uses official Nutanix v4 SDK packages")
        print("- Better error handling and retry mechanisms")
        print("- Improved statistics collection")
        print("- Rate limiting and connection pooling support")
    else:
        print("✗ Some tests failed!")
        print("Please fix the issues before running the daemon.")
        sys.exit(1)

if __name__ == "__main__":
    main()
