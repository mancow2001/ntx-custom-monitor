#!/usr/bin/env python3
"""
Nutanix Prism Central SNMP Daemon

This daemon collects performance statistics from Nutanix Prism Central
and exposes them via SNMPv3 for monitoring tools like SolarWinds, ScienceLogic, etc.
"""

import asyncio
import json
import logging
import signal
import sys
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import threading
import configparser
import os

# Third-party imports (install via pip)
import requests
import urllib3
from pysnmp.entity import engine, config
from pysnmp.entity.rfc3413 import cmdrsp, context
from pysnmp.carrier.asyncore import dgram
from pysnmp.smi import builder, view, compiler
from pysnmp.proto.api import v2c
from pysnmp import debug

# Disable SSL warnings for self-signed certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/var/log/nutanix_snmp_daemon.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class NutanixAPI:
    """Handles communication with Nutanix Prism Central API"""
    
    def __init__(self, prism_central_ip: str, username: str, password: str, port: int = 9440):
        self.base_url = f"https://{prism_central_ip}:{port}/api/nutanix/v3"
        self.auth = (username, password)
        self.session = requests.Session()
        self.session.verify = False
        self.session.auth = self.auth
        
    def _make_request(self, method: str, endpoint: str, data: dict = None) -> Optional[dict]:
        """Make HTTP request to Nutanix API"""
        url = f"{self.base_url}/{endpoint}"
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        
        try:
            if method.upper() == 'GET':
                response = self.session.get(url, headers=headers, timeout=30)
            elif method.upper() == 'POST':
                response = self.session.post(url, headers=headers, json=data, timeout=30)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
                
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed: {e}")
            return None
    
    def get_clusters(self) -> List[Dict]:
        """Get list of all clusters"""
        data = {"kind": "cluster"}
        response = self._make_request("POST", "clusters/list", data)
        return response.get("entities", []) if response else []
    
    def get_hosts(self) -> List[Dict]:
        """Get list of all hosts"""
        data = {"kind": "host"}
        response = self._make_request("POST", "hosts/list", data)
        return response.get("entities", []) if response else []
    
    def get_vms(self) -> List[Dict]:
        """Get list of all VMs"""
        data = {"kind": "vm"}
        response = self._make_request("POST", "vms/list", data)
        return response.get("entities", []) if response else []
    
    def get_cluster_stats(self, cluster_uuid: str) -> Optional[Dict]:
        """Get performance statistics for a specific cluster"""
        endpoint = f"clusters/{cluster_uuid}/stats"
        return self._make_request("GET", endpoint)
    
    def get_host_stats(self, host_uuid: str) -> Optional[Dict]:
        """Get performance statistics for a specific host"""
        endpoint = f"hosts/{host_uuid}/stats"
        return self._make_request("GET", endpoint)

class PerformanceCollector:
    """Collects and processes performance statistics"""
    
    def __init__(self, nutanix_api: NutanixAPI):
        self.api = nutanix_api
        self.stats_cache = {}
        self.last_update = None
        self.collection_interval = 60  # seconds
        
    async def collect_all_stats(self) -> Dict:
        """Collect performance statistics from all clusters and hosts"""
        stats = {
            'clusters': {},
            'hosts': {},
            'timestamp': datetime.now().isoformat()
        }
        
        # Collect cluster statistics
        clusters = self.api.get_clusters()
        for cluster in clusters:
            cluster_uuid = cluster.get('metadata', {}).get('uuid')
            cluster_name = cluster.get('spec', {}).get('name', 'Unknown')
            
            if cluster_uuid:
                cluster_stats = self.api.get_cluster_stats(cluster_uuid)
                if cluster_stats:
                    stats['clusters'][cluster_uuid] = {
                        'name': cluster_name,
                        'stats': self._process_cluster_stats(cluster_stats)
                    }
        
        # Collect host statistics
        hosts = self.api.get_hosts()
        for host in hosts:
            host_uuid = host.get('metadata', {}).get('uuid')
            host_name = host.get('spec', {}).get('name', 'Unknown')
            
            if host_uuid:
                host_stats = self.api.get_host_stats(host_uuid)
                if host_stats:
                    stats['hosts'][host_uuid] = {
                        'name': host_name,
                        'stats': self._process_host_stats(host_stats)
                    }
        
        self.stats_cache = stats
        self.last_update = datetime.now()
        return stats
    
    def _process_cluster_stats(self, raw_stats: Dict) -> Dict:
        """Process and normalize cluster statistics"""
        processed = {}
        
        # Extract key metrics
        if 'hypervisor_cpu_usage_ppm' in raw_stats:
            processed['cpu_usage_percent'] = raw_stats['hypervisor_cpu_usage_ppm'] / 10000
        
        if 'hypervisor_memory_usage_ppm' in raw_stats:
            processed['memory_usage_percent'] = raw_stats['hypervisor_memory_usage_ppm'] / 10000
        
        if 'controller_avg_io_latency_usecs' in raw_stats:
            processed['avg_io_latency_ms'] = raw_stats['controller_avg_io_latency_usecs'] / 1000
        
        if 'controller_avg_read_io_latency_usecs' in raw_stats:
            processed['avg_read_latency_ms'] = raw_stats['controller_avg_read_io_latency_usecs'] / 1000
        
        if 'controller_avg_write_io_latency_usecs' in raw_stats:
            processed['avg_write_latency_ms'] = raw_stats['controller_avg_write_io_latency_usecs'] / 1000
        
        if 'controller_io_bandwidth_kBps' in raw_stats:
            processed['io_bandwidth_mbps'] = raw_stats['controller_io_bandwidth_kBps'] / 1024
        
        if 'controller_num_iops' in raw_stats:
            processed['iops'] = raw_stats['controller_num_iops']
        
        return processed
    
    def _process_host_stats(self, raw_stats: Dict) -> Dict:
        """Process and normalize host statistics"""
        processed = {}
        
        # Extract key metrics
        if 'hypervisor_cpu_usage_ppm' in raw_stats:
            processed['cpu_usage_percent'] = raw_stats['hypervisor_cpu_usage_ppm'] / 10000
        
        if 'hypervisor_memory_usage_ppm' in raw_stats:
            processed['memory_usage_percent'] = raw_stats['hypervisor_memory_usage_ppm'] / 10000
        
        if 'controller_avg_io_latency_usecs' in raw_stats:
            processed['avg_io_latency_ms'] = raw_stats['controller_avg_io_latency_usecs'] / 1000
        
        if 'controller_io_bandwidth_kBps' in raw_stats:
            processed['io_bandwidth_mbps'] = raw_stats['controller_io_bandwidth_kBps'] / 1024
        
        if 'controller_num_iops' in raw_stats:
            processed['iops'] = raw_stats['controller_num_iops']
        
        if 'hypervisor_num_vms' in raw_stats:
            processed['num_vms'] = raw_stats['hypervisor_num_vms']
        
        return processed

class SNMPAgent:
    """SNMP v3 Agent that exposes Nutanix performance data"""
    
    # Custom OID base (you should register your own OID)
    BASE_OID = '1.3.6.1.4.1.99999.1'  # Example private enterprise OID
    
    def __init__(self, bind_ip: str = '0.0.0.0', bind_port: int = 161, 
                 username: str = 'nutanix', auth_key: str = 'authkey123', 
                 priv_key: str = 'privkey123'):
        self.bind_ip = bind_ip
        self.bind_port = bind_port
        self.username = username
        self.auth_key = auth_key
        self.priv_key = priv_key
        
        self.snmp_engine = engine.SnmpEngine()
        self.performance_data = {}
        
        self._setup_snmp_engine()
    
    def _setup_snmp_engine(self):
        """Configure SNMP engine with SNMPv3 settings"""
        
        # Setup transport endpoint
        config.addTransport(
            self.snmp_engine,
            dgram.domainName,
            dgram.UdpTransport().openServerMode((self.bind_ip, self.bind_port))
        )
        
        # Setup SNMPv3 user with authentication and privacy
        config.addV3User(
            self.snmp_engine,
            self.username,
            config.usmHMACMD5AuthProtocol, self.auth_key,
            config.usmDESPrivProtocol, self.priv_key
        )
        
        # Setup context
        config.addContext(self.snmp_engine, '')
        
        # Register SNMP application
        cmdrsp.GetCommandResponder(self.snmp_engine, context.SnmpContext(self.snmp_engine))
        
        # Setup MIB builder
        self.mib_builder = builder.MibBuilder()
        self.mib_view = view.MibViewController(self.mib_builder)
        
        logger.info(f"SNMP agent configured on {self.bind_ip}:{self.bind_port}")
    
    def update_performance_data(self, stats: Dict):
        """Update the performance data that SNMP agent will serve"""
        self.performance_data = stats
        logger.debug("Performance data updated in SNMP agent")
    
    def start(self):
        """Start the SNMP agent"""
        logger.info("Starting SNMP agent...")
        try:
            self.snmp_engine.transportDispatcher.runDispatcher()
        except Exception as e:
            logger.error(f"SNMP agent error: {e}")
    
    def stop(self):
        """Stop the SNMP agent"""
        logger.info("Stopping SNMP agent...")
        self.snmp_engine.transportDispatcher.closeDispatcher()

class NutanixSNMPDaemon:
    """Main daemon class that orchestrates data collection and SNMP exposure"""
    
    def __init__(self, config_file: str = '/etc/nutanix_snmp_daemon.conf'):
        self.config_file = config_file
        self.config = self._load_config()
        
        # Initialize components
        self.nutanix_api = NutanixAPI(
            self.config['nutanix']['prism_central_ip'],
            self.config['nutanix']['username'],
            self.config['nutanix']['password'],
            int(self.config['nutanix'].get('port', 9440))
        )
        
        self.collector = PerformanceCollector(self.nutanix_api)
        
        self.snmp_agent = SNMPAgent(
            self.config['snmp']['bind_ip'],
            int(self.config['snmp']['bind_port']),
            self.config['snmp']['username'],
            self.config['snmp']['auth_key'],
            self.config['snmp']['priv_key']
        )
        
        self.running = False
        self.collection_thread = None
        self.snmp_thread = None
        
        # Setup signal handlers
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
    
    def _load_config(self) -> configparser.ConfigParser:
        """Load configuration from file"""
        config = configparser.ConfigParser()
        
        # Default configuration
        config['nutanix'] = {
            'prism_central_ip': '10.1.1.100',
            'username': 'admin',
            'password': 'password',
            'port': '9440'
        }
        
        config['snmp'] = {
            'bind_ip': '0.0.0.0',
            'bind_port': '161',
            'username': 'nutanix',
            'auth_key': 'authkey123',
            'priv_key': 'privkey123'
        }
        
        config['daemon'] = {
            'collection_interval': '60',
            'log_level': 'INFO'
        }
        
        # Load from file if exists
        if os.path.exists(self.config_file):
            config.read(self.config_file)
            logger.info(f"Configuration loaded from {self.config_file}")
        else:
            # Create default config file
            with open(self.config_file, 'w') as f:
                config.write(f)
            logger.info(f"Default configuration created at {self.config_file}")
        
        return config
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        logger.info(f"Received signal {signum}, shutting down...")
        self.stop()
    
    def _collection_worker(self):
        """Background worker for collecting performance data"""
        collection_interval = int(self.config['daemon']['collection_interval'])
        
        while self.running:
            try:
                start_time = time.time()
                
                # Collect performance statistics
                logger.info("Collecting performance statistics...")
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                stats = loop.run_until_complete(self.collector.collect_all_stats())
                loop.close()
                
                # Update SNMP agent with new data
                self.snmp_agent.update_performance_data(stats)
                
                collection_time = time.time() - start_time
                logger.info(f"Statistics collection completed in {collection_time:.2f} seconds")
                
                # Sleep for remaining interval time
                sleep_time = max(0, collection_interval - collection_time)
                time.sleep(sleep_time)
                
            except Exception as e:
                logger.error(f"Error in collection worker: {e}")
                time.sleep(30)  # Wait 30 seconds before retrying
    
    def _snmp_worker(self):
        """Background worker for SNMP agent"""
        try:
            self.snmp_agent.start()
        except Exception as e:
            logger.error(f"SNMP worker error: {e}")
    
    def start(self):
        """Start the daemon"""
        logger.info("Starting Nutanix SNMP Daemon...")
        self.running = True
        
        # Start collection thread
        self.collection_thread = threading.Thread(target=self._collection_worker, daemon=True)
        self.collection_thread.start()
        
        # Start SNMP agent thread
        self.snmp_thread = threading.Thread(target=self._snmp_worker, daemon=True)
        self.snmp_thread.start()
        
        logger.info("Daemon started successfully")
        
        # Keep main thread alive
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop()
    
    def stop(self):
        """Stop the daemon"""
        logger.info("Stopping daemon...")
        self.running = False
        
        if self.snmp_agent:
            self.snmp_agent.stop()
        
        logger.info("Daemon stopped")

def main():
    """Main entry point"""
    daemon = NutanixSNMPDaemon()
    daemon.start()

if __name__ == "__main__":
    main()
