#!/usr/bin/env python3
"""
SNMP Agent Module

Implements SNMPv3 agent that exposes Nutanix performance data.
Uses modern pysnmp 6.x API compatible with Python 3.10+
"""

import logging
import threading
import time
import asyncio
from typing import Dict, Any, Optional, List, Tuple
from ipaddress import ip_network, ip_address

from pysnmp.entity import engine, config
from pysnmp.entity.rfc3413 import cmdrsp, context
from pysnmp.carrier.asyncio import dgram
from pysnmp.smi import builder, view, instrum
from pysnmp.proto.api import v2c
from pysnmp.proto import rfc1902

logger = logging.getLogger(__name__)

class SNMPAgentError(Exception):
    """Custom exception for SNMP agent errors"""
    pass

class NutanixMIBInstrumController(instrum.MibInstrumController):
    """Custom MIB instrumentation controller for Nutanix metrics"""
    
    def __init__(self, mib_builder, snmp_agent):
        super().__init__(mib_builder)
        self.snmp_agent = snmp_agent
        
    def readVars(self, varBinds, acInfo=(None, None)):
        """Handle SNMP GET requests"""
        result_vars = []
        
        for oid, val in varBinds:
            try:
                # Convert OID to string for easier handling
                oid_str = str(oid)
                value = self.snmp_agent.get_oid_value(oid_str)
                
                if value is not None:
                    # Convert Python value to SNMP value
                    snmp_value = self._python_to_snmp_value(value)
                    result_vars.append((oid, snmp_value))
                else:
                    # OID not found
                    result_vars.append((oid, rfc1902.noSuchInstance))
                    
            except Exception as e:
                logger.error(f"Error reading OID {oid}: {e}")
                result_vars.append((oid, rfc1902.noSuchInstance))
        
        return result_vars
    
    def readNextVars(self, varBinds, acInfo=(None, None)):
        """Handle SNMP GETNEXT requests"""
        result_vars = []
        
        for oid, val in varBinds:
            try:
                oid_str = str(oid)
                next_oid, next_value = self.snmp_agent.get_next_oid(oid_str)
                
                if next_oid and next_value is not None:
                    snmp_value = self._python_to_snmp_value(next_value)
                    result_vars.append((rfc1902.ObjectName(next_oid), snmp_value))
                else:
                    result_vars.append((oid, rfc1902.endOfMibView))
                    
            except Exception as e:
                logger.error(f"Error reading next OID for {oid}: {e}")
                result_vars.append((oid, rfc1902.endOfMibView))
        
        return result_vars
    
    def _python_to_snmp_value(self, value):
        """Convert Python value to appropriate SNMP value type"""
        if isinstance(value, int):
            return rfc1902.Integer32(value)
        elif isinstance(value, float):
            # Convert float to integer (multiply by 100 for percentage precision)
            return rfc1902.Integer32(int(value * 100))
        elif isinstance(value, str):
            return rfc1902.OctetString(value)
        elif isinstance(value, bool):
            return rfc1902.Integer32(1 if value else 0)
        else:
            return rfc1902.OctetString(str(value))

class SNMPAgent:
    """SNMP v3 Agent that exposes Nutanix performance data using modern pysnmp 6.x"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.snmp_config = config.get('snmp', {})
        self.security_config = config.get('security', {})
        
        # SNMP configuration
        self.bind_ip = self.snmp_config.get('bind_ip', '0.0.0.0')
        self.bind_port = int(self.snmp_config.get('bind_port', 161))
        self.username = self.snmp_config.get('username', 'nutanix')
        self.auth_key = self.snmp_config.get('auth_key', 'authkey123')
        self.priv_key = self.snmp_config.get('priv_key', 'privkey123')
        self.base_oid = self.snmp_config.get('base_oid', '1.3.6.1.4.1.99999.1')
        
        # Protocol settings
        self.auth_protocol = self._get_auth_protocol()
        self.priv_protocol = self._get_priv_protocol()
        
        # Data storage
        self.performance_data = {}
        self.data_lock = threading.RLock()
        
        # SNMP engine and event loop
        self.snmp_engine = None
        self.running = False
        self.loop = None
        self.transport = None
        
        # OID mapping for metrics
        self.oid_tree = {}
        self._build_oid_tree()
        
        # Security - allowed clients
        self.allowed_clients = self._parse_allowed_clients()
        
        logger.info(f"SNMP agent initialized for {self.bind_ip}:{self.bind_port}")
    
    def _get_auth_protocol(self):
        """Get authentication protocol"""
        auth_proto = self.snmp_config.get('auth_protocol', 'MD5').upper()
        if auth_proto == 'SHA':
            return config.usmHMACSHAAuthProtocol
        else:
            return config.usmHMACMD5AuthProtocol
    
    def _get_priv_protocol(self):
        """Get privacy protocol"""
        priv_proto = self.snmp_config.get('priv_protocol', 'DES').upper()
        if priv_proto == 'AES':
            return config.usmAesCfb128Protocol
        else:
            return config.usmDESPrivProtocol
    
    def _parse_allowed_clients(self) -> List:
        """Parse allowed SNMP clients from configuration"""
        allowed = self.security_config.get('allowed_snmp_clients', [])
        parsed_clients = []
        
        for client in allowed:
            try:
                # Try to parse as network
                network = ip_network(client, strict=False)
                parsed_clients.append(network)
            except ValueError:
                try:
                    # Try to parse as single IP
                    addr = ip_address(client)
                    parsed_clients.append(addr)
                except ValueError:
                    logger.warning(f"Invalid client specification: {client}")
        
        return parsed_clients
    
    def _is_client_allowed(self, client_ip: str) -> bool:
        """Check if client IP is allowed"""
        if not self.allowed_clients:
            return True  # No restrictions
        
        try:
            client = ip_address(client_ip)
            for allowed in self.allowed_clients:
                if hasattr(allowed, 'network_address'):
                    # It's a network
                    if client in allowed:
                        return True
                else:
                    # It's a single IP
                    if client == allowed:
                        return True
        except ValueError:
            logger.warning(f"Invalid client IP: {client_ip}")
        
        return False
    
    def _build_oid_tree(self):
        """Build the OID tree structure for metrics"""
        base_parts = self.base_oid.split('.')
        
        # Define OID structure
        self.cluster_base = f"{self.base_oid}.1.1"
        self.host_base = f"{self.base_oid}.2.1"
        self.vm_base = f"{self.base_oid}.3.1"
        
        # Metric definitions
        self.cluster_metrics = {
            1: 'cpu_usage_percent',
            2: 'memory_usage_percent',
            3: 'avg_io_latency_ms',
            4: 'io_bandwidth_mbps',
            5: 'iops'
        }
        
        self.host_metrics = {
            1: 'cpu_usage_percent',
            2: 'memory_usage_percent',
            3: 'avg_io_latency_ms',
            4: 'io_bandwidth_mbps',
            5: 'iops',
            6: 'num_vms'
        }
        
        self.vm_metrics = {
            1: 'cpu_usage_percent',
            2: 'memory_usage_percent',
            3: 'disk_usage_gb'
        }
    
    def setup_snmp_engine(self):
        """Configure SNMP engine with SNMPv3 settings"""
        self.snmp_engine = engine.SnmpEngine()
        
        # Setup transport endpoint using asyncio
        self.transport = dgram.UdpTransport().openServerMode((self.bind_ip, self.bind_port))
        
        config.addTransport(
            self.snmp_engine,
            dgram.domainName,
            self.transport
        )
        
        # Setup SNMPv3 user with authentication and privacy
        config.addV3User(
            self.snmp_engine,
            self.username,
            self.auth_protocol, self.auth_key,
            self.priv_protocol, self.priv_key
        )
        
        # Setup context
        config.addContext(self.snmp_engine, '')
        
        # Setup MIB builder and instrumentation
        mib_builder = builder.MibBuilder()
        mib_instrum = NutanixMIBInstrumController(mib_builder, self)
        
        # Register command responder
        cmdrsp.GetCommandResponder(self.snmp_engine, context.SnmpContext(self.snmp_engine))
        
        # Register the custom MIB controller
        self.snmp_engine.msgAndPduDsp.mibInstrumController = mib_instrum
        
        logger.info(f"SNMP engine configured on {self.bind_ip}:{self.bind_port}")
    
    def get_oid_value(self, oid: str) -> Optional[Any]:
        """Get value for a specific OID"""
        with self.data_lock:
            try:
                # Parse OID to determine what metric is being requested
                if oid.startswith(self.cluster_base):
                    return self._get_cluster_metric(oid)
                elif oid.startswith(self.host_base):
                    return self._get_host_metric(oid)
                elif oid.startswith(self.vm_base):
                    return self._get_vm_metric(oid)
                else:
                    logger.debug(f"OID not in our tree: {oid}")
                    return None
                    
            except Exception as e:
                logger.error(f"Error getting value for OID {oid}: {e}")
                return None
    
    def get_next_oid(self, oid: str) -> Tuple[Optional[str], Optional[Any]]:
        """Get the next OID and its value for GETNEXT operations"""
        with self.data_lock:
            try:
                # Get all available OIDs
                all_oids = self._get_all_oids()
                all_oids.sort()
                
                # Find the next OID
                for next_oid in all_oids:
                    if next_oid > oid:
                        value = self.get_oid_value(next_oid)
                        return next_oid, value
                
                return None, None
                
            except Exception as e:
                logger.error(f"Error getting next OID for {oid}: {e}")
                return None, None
    
    def _get_all_oids(self) -> List[str]:
        """Get list of all available OIDs"""
        oids = []
        
        # Add cluster OIDs
        clusters = self.performance_data.get('clusters', {})
        for i, (uuid, cluster_data) in enumerate(clusters.items(), 1):
            for metric_id in self.cluster_metrics.keys():
                oid = f"{self.cluster_base}.{i}.{metric_id}"
                oids.append(oid)
        
        # Add host OIDs
        hosts = self.performance_data.get('hosts', {})
        for i, (uuid, host_data) in enumerate(hosts.items(), 1):
            for metric_id in self.host_metrics.keys():
                oid = f"{self.host_base}.{i}.{metric_id}"
                oids.append(oid)
        
        # Add VM OIDs (if enabled)
        vms = self.performance_data.get('vms', {})
        for i, (uuid, vm_data) in enumerate(vms.items(), 1):
            for metric_id in self.vm_metrics.keys():
                oid = f"{self.vm_base}.{i}.{metric_id}"
                oids.append(oid)
        
        return oids
    
    def _get_cluster_metric(self, oid: str) -> Optional[Any]:
        """Get cluster metric value"""
        # Parse OID: base.1.1.{index}.{metric_id}
        parts = oid.split('.')
        if len(parts) < 2:
            return None
        
        try:
            cluster_index = int(parts[-2])
            metric_id = int(parts[-1])
            
            clusters = list(self.performance_data.get('clusters', {}).items())
            if cluster_index < 1 or cluster_index > len(clusters):
                return None
            
            uuid, cluster_data = clusters[cluster_index - 1]
            metric_name = self.cluster_metrics.get(metric_id)
            
            if not metric_name:
                return None
            
            stats = cluster_data.get('stats', {})
            return stats.get(metric_name)
            
        except (ValueError, IndexError):
            return None
    
    def _get_host_metric(self, oid: str) -> Optional[Any]:
        """Get host metric value"""
        # Parse OID: base.2.1.{index}.{metric_id}
        parts = oid.split('.')
        if len(parts) < 2:
            return None
        
        try:
            host_index = int(parts[-2])
            metric_id = int(parts[-1])
            
            hosts = list(self.performance_data.get('hosts', {}).items())
            if host_index < 1 or host_index > len(hosts):
                return None
            
            uuid, host_data = hosts[host_index - 1]
            metric_name = self.host_metrics.get(metric_id)
            
            if not metric_name:
                return None
            
            stats = host_data.get('stats', {})
            return stats.get(metric_name)
            
        except (ValueError, IndexError):
            return None
    
    def _get_vm_metric(self, oid: str) -> Optional[Any]:
        """Get VM metric value"""
        # Parse OID: base.3.1.{index}.{metric_id}
        parts = oid.split('.')
        if len(parts) < 2:
            return None
        
        try:
            vm_index = int(parts[-2])
            metric_id = int(parts[-1])
            
            vms = list(self.performance_data.get('vms', {}).items())
            if vm_index < 1 or vm_index > len(vms):
                return None
            
            uuid, vm_data = vms[vm_index - 1]
            metric_name = self.vm_metrics.get(metric_id)
            
            if not metric_name:
                return None
            
            stats = vm_data.get('stats', {})
            return stats.get(metric_name)
            
        except (ValueError, IndexError):
            return None
    
    def update_performance_data(self, stats: Dict[str, Any]):
        """Update the performance data that SNMP agent will serve"""
        with self.data_lock:
            self.performance_data = stats
        
        logger.debug("Performance data updated in SNMP agent")
    
    def start(self):
        """Start the SNMP agent using asyncio"""
        if self.running:
            logger.warning("SNMP agent is already running")
            return
        
        logger.info("Starting SNMP agent...")
        
        try:
            # Create new event loop for this thread
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            
            # Setup SNMP engine
            self.setup_snmp_engine()
            self.running = True
            
            # Run the event loop
            self.loop.run_forever()
            
        except Exception as e:
            logger.error(f"Failed to start SNMP agent: {e}")
            self.running = False
            raise SNMPAgentError(f"SNMP agent startup failed: {e}")
        finally:
            if self.loop:
                self.loop.close()
    
    def stop(self):
        """Stop the SNMP agent"""
        if not self.running:
            return
        
        logger.info("Stopping SNMP agent...")
        self.running = False
        
        try:
            if self.transport:
                self.transport.closeTransport()
            
            if self.loop and self.loop.is_running():
                self.loop.call_soon_threadsafe(self.loop.stop)
            
            logger.info("SNMP agent stopped")
        except Exception as e:
            logger.error(f"Error stopping SNMP agent: {e}")
    
    def is_running(self) -> bool:
        """Check if the SNMP agent is running"""
        return self.running
    
    def get_stats(self) -> Dict[str, Any]:
        """Get SNMP agent statistics"""
        with self.data_lock:
            cluster_count = len(self.performance_data.get('clusters', {}))
            host_count = len(self.performance_data.get('hosts', {}))
            vm_count = len(self.performance_data.get('vms', {}))
            
            return {
                'running': self.running,
                'bind_address': f"{self.bind_ip}:{self.bind_port}",
                'username': self.username,
                'auth_protocol': self.snmp_config.get('auth_protocol', 'MD5'),
                'priv_protocol': self.snmp_config.get('priv_protocol', 'DES'),
                'base_oid': self.base_oid,
                'cluster_count': cluster_count,
                'host_count': host_count,
                'vm_count': vm_count,
                'total_oids': len(self._get_all_oids()),
                'allowed_clients': len(self.allowed_clients),
                'last_data_update': self.performance_data.get('timestamp', 'Never')
            }
