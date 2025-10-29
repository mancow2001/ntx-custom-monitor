#!/usr/bin/env python3
"""
Test script for Nutanix SNMP Daemon

This script tests the connection to Nutanix Prism Central and SNMP functionality.
"""

import sys
import requests
import urllib3
from pysnmp.hlapi import *
import configparser

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def test_nutanix_connection(config):
    """Test connection to Nutanix Prism Central"""
    print("Testing Nutanix Prism Central connection...")
    
    prism_ip = config['nutanix']['prism_central_ip']
    username = config['nutanix']['username']
    password = config['nutanix']['password']
    port = config['nutanix'].get('port', '9440')
    
    url = f"https://{prism_ip}:{port}/api/nutanix/v3/clusters/list"
    
    try:
        response = requests.post(
            url,
            auth=(username, password),
            json={"kind": "cluster"},
            verify=False,
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            cluster_count = len(data.get('entities', []))
            print(f"✓ Successfully connected to Prism Central")
            print(f"✓ Found {cluster_count} clusters")
            return True
        else:
            print(f"✗ HTTP Error: {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"✗ Connection failed: {e}")
        return False

def test_snmp_agent(config):
    """Test SNMP agent functionality"""
    print("\nTesting SNMP agent...")
    
    # Note: This is a basic test - the actual agent needs to be running
    bind_ip = config['snmp']['bind_ip']
    bind_port = int(config['snmp']['bind_port'])
    username = config['snmp']['username']
    auth_key = config['snmp']['auth_key']
    priv_key = config['snmp']['priv_key']
    
    # Test SNMP v3 configuration
    if len(auth_key) < 8:
        print("✗ Authentication key too short (minimum 8 characters)")
        return False
    
    if len(priv_key) < 8:
        print("✗ Privacy key too short (minimum 8 characters)")
        return False
    
    print("✓ SNMP v3 keys are valid length")
    print(f"✓ SNMP agent configured for {bind_ip}:{bind_port}")
    
    # Try to perform an SNMP walk (this will fail if agent isn't running)
    try:
        target_ip = '127.0.0.1' if bind_ip == '0.0.0.0' else bind_ip
        
        for (errorIndication, errorStatus, errorIndex, varBinds) in nextCmd(
            SnmpEngine(),
            UsmUserData(username, auth_key, priv_key,
                       authProtocol=usmHMACMD5AuthProtocol,
                       privProtocol=usmDESPrivProtocol),
            UdpTransportTarget((target_ip, bind_port)),
            ContextData(),
            ObjectType(ObjectIdentity('1.3.6.1.4.1.99999.1')),
            lexicographicMode=False, maxRows=1):
            
            if errorIndication:
                print(f"✗ SNMP walk failed: {errorIndication}")
                return False
            elif errorStatus:
                print(f"✗ SNMP error: {errorStatus.prettyPrint()}")
                return False
            else:
                print("✓ SNMP agent responded successfully")
                return True
                
    except Exception as e:
        print(f"✗ SNMP test failed: {e}")
        print("Note: This is expected if the daemon is not running")
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

def main():
    """Main test function"""
    print("Nutanix SNMP Daemon Test Script")
    print("=" * 40)
    
    # Load configuration
    config = configparser.ConfigParser()
    config_file = '/etc/nutanix_snmp_daemon.conf'
    
    if not config.read(config_file):
        print(f"✗ Cannot read configuration file: {config_file}")
        print("Please ensure the configuration file exists and is readable")
        sys.exit(1)
    
    print(f"✓ Configuration loaded from {config_file}")
    
    # Run tests
    success = True
    
    success &= test_nutanix_connection(config)
    success &= test_snmp_agent(config)
    test_permissions()  # This is informational only
    
    print("\n" + "=" * 40)
    if success:
        print("✓ All critical tests passed!")
        print("The daemon should work correctly with this configuration.")
    else:
        print("✗ Some tests failed!")
        print("Please fix the issues before running the daemon.")
        sys.exit(1)

if __name__ == "__main__":
    main()
