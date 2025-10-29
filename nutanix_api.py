#!/usr/bin/env python3
"""
Nutanix API Client Module (v4 SDK)

Handles communication with Nutanix Prism Central using the official v4 SDK.
"""

import logging
import time
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timedelta

# Nutanix v4 SDK imports
from ntnx_clustermgmt_py_client import Configuration as ClusterMgmtConfig
from ntnx_clustermgmt_py_client import ApiClient as ClusterMgmtApiClient
from ntnx_clustermgmt_py_client.api.clusters_api import ClustersApi
from ntnx_clustermgmt_py_client.api.hosts_api import HostsApi
from ntnx_clustermgmt_py_client.rest import ApiException as ClusterMgmtApiException

from ntnx_vmm_py_client import Configuration as VmmConfig
from ntnx_vmm_py_client import ApiClient as VmmApiClient
from ntnx_vmm_py_client.api.vm_api import VmApi
from ntnx_vmm_py_client.rest import ApiException as VmmApiException

from ntnx_prism_py_client import Configuration as PrismConfig
from ntnx_prism_py_client import ApiClient as PrismApiClient
from ntnx_prism_py_client.rest import ApiException as PrismApiException

# Import the statistics models
try:
    from ntnx_clustermgmt_py_client.models.common.v1.stats.down_sampling_operator import DownSamplingOperator
    from ntnx_clustermgmt_py_client.models.common.v1.stats.time_range_filter import TimeRangeFilter
    from ntnx_vmm_py_client.models.common.v1.stats.down_sampling_operator import DownSamplingOperator as VmmDownSamplingOperator
    from ntnx_vmm_py_client.models.common.v1.stats.time_range_filter import TimeRangeFilter as VmmTimeRangeFilter
except ImportError as e:
    logging.warning(f"Could not import statistics models: {e}")
    DownSamplingOperator = None
    TimeRangeFilter = None
    VmmDownSamplingOperator = None
    VmmTimeRangeFilter = None

logger = logging.getLogger(__name__)

class NutanixAPIError(Exception):
    """Custom exception for Nutanix API errors"""
    pass

class NutanixAPIClient:
    """Handles communication with Nutanix Prism Central using v4 SDK"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.prism_central_ip = config['prism_central_ip']
        self.port = config.get('port', 9440)
        self.username = config['username']
        self.password = config['password']
        self.ssl_verify = config.get('ssl_verify', False)
        self.timeout = config.get('timeout', 30)
        
        # Connection health tracking
        self.last_successful_request = None
        self.consecutive_failures = 0
        self.max_failures = config.get('retry_count', 3)
        
        # Initialize SDK configurations
        self._setup_sdk_configs()
        
        # Initialize API clients
        self._setup_api_clients()
        
        logger.info(f"Nutanix v4 SDK client initialized for {self.prism_central_ip}:{self.port}")
    
    def _setup_sdk_configs(self):
        """Setup SDK configurations for all namespaces"""
        base_config = {
            'host': self.prism_central_ip,
            'port': self.port,
            'username': self.username,
            'password': self.password,
            'verify_ssl': self.ssl_verify,
            'ssl_ca_cert': None,
            'connection_pool_maxsize': self.config.get('connection_pool_size', 5),
            'proxy': None,
            'proxy_headers': None,
        }
        
        # Cluster Management configuration
        self.clustermgmt_config = ClusterMgmtConfig()
        for key, value in base_config.items():
            setattr(self.clustermgmt_config, key, value)
        
        # VMM configuration
        self.vmm_config = VmmConfig()
        for key, value in base_config.items():
            setattr(self.vmm_config, key, value)
        
        # Prism configuration
        self.prism_config = PrismConfig()
        for key, value in base_config.items():
            setattr(self.prism_config, key, value)
    
    def _setup_api_clients(self):
        """Setup API clients for all namespaces"""
        try:
            # Cluster Management API client
            self.clustermgmt_client = ClusterMgmtApiClient(configuration=self.clustermgmt_config)
            self.clusters_api = ClustersApi(api_client=self.clustermgmt_client)
            self.hosts_api = HostsApi(api_client=self.clustermgmt_client)
            
            # VMM API client
            self.vmm_client = VmmApiClient(configuration=self.vmm_config)
            self.vm_api = VmApi(api_client=self.vmm_client)
            
            # Prism API client
            self.prism_client = PrismApiClient(configuration=self.prism_config)
            
            logger.info("All v4 SDK API clients initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize SDK API clients: {e}")
            raise NutanixAPIError(f"SDK initialization failed: {e}")
    
    def _handle_api_exception(self, operation: str, exception: Exception):
        """Handle API exceptions and update failure tracking"""
        self.consecutive_failures += 1
        
        if hasattr(exception, 'status'):
            status_code = exception.status
            if status_code == 401:
                logger.error(f"Authentication failed for {operation}")
                raise NutanixAPIError("Authentication failed - check credentials")
            elif status_code == 403:
                logger.error(f"Access forbidden for {operation}")
                raise NutanixAPIError("Access forbidden - check user permissions")
            elif status_code == 404:
                logger.warning(f"Resource not found for {operation}")
                return None
            else:
                logger.error(f"HTTP {status_code} error for {operation}: {exception}")
                raise NutanixAPIError(f"HTTP {status_code}: {exception}")
        else:
            logger.error(f"API error for {operation}: {exception}")
            raise NutanixAPIError(f"API error: {exception}")
    
    def _mark_success(self):
        """Mark a successful API call"""
        self.consecutive_failures = 0
        self.last_successful_request = time.time()
    
    def health_check(self) -> bool:
        """Perform a health check on the API connection"""
        try:
            # Simple API call to test connectivity
            clusters = self.get_clusters()
            self._mark_success()
            return clusters is not None
        except Exception as e:
            logger.warning(f"Health check failed: {e}")
            return False
    
    def is_healthy(self) -> bool:
        """Check if the API connection is considered healthy"""
        if self.consecutive_failures >= self.max_failures:
            return False
        
        # If we've never had a successful request, consider unhealthy
        if self.last_successful_request is None:
            return False
        
        # Consider unhealthy if last successful request was too long ago
        max_age = 300  # 5 minutes
        if time.time() - self.last_successful_request > max_age:
            return False
        
        return True
    
    def get_clusters(self) -> List[Dict]:
        """Get list of all clusters"""
        try:
            logger.debug("Fetching clusters using v4 SDK")
            
            # Use the clusters API to list all clusters
            response = self.clusters_api.list_clusters(
                _limit=1000,  # Set a reasonable limit
                _page=1
            )
            
            clusters = []
            if hasattr(response, 'data') and response.data:
                for cluster in response.data:
                    # Convert the SDK object to dictionary format
                    cluster_dict = {
                        'metadata': {
                            'uuid': getattr(cluster, 'ext_id', None),
                            'name': getattr(cluster, 'name', 'Unknown')
                        },
                        'spec': {
                            'name': getattr(cluster, 'name', 'Unknown')
                        },
                        'status': {
                            'state': 'COMPLETE'  # Assume complete for listed clusters
                        }
                    }
                    clusters.append(cluster_dict)
            
            self._mark_success()
            logger.info(f"Retrieved {len(clusters)} clusters using v4 SDK")
            return clusters
            
        except (ClusterMgmtApiException, Exception) as e:
            self._handle_api_exception("get_clusters", e)
            return []
    
    def get_hosts(self) -> List[Dict]:
        """Get list of all hosts"""
        try:
            logger.debug("Fetching hosts using v4 SDK")
            
            # Use the hosts API to list all hosts
            response = self.hosts_api.list_hosts(
                _limit=1000,  # Set a reasonable limit
                _page=1
            )
            
            hosts = []
            if hasattr(response, 'data') and response.data:
                for host in response.data:
                    # Convert the SDK object to dictionary format
                    host_dict = {
                        'metadata': {
                            'uuid': getattr(host, 'ext_id', None),
                            'name': getattr(host, 'name', 'Unknown')
                        },
                        'spec': {
                            'name': getattr(host, 'name', 'Unknown')
                        },
                        'status': {
                            'state': 'COMPLETE'  # Assume complete for listed hosts
                        }
                    }
                    hosts.append(host_dict)
            
            self._mark_success()
            logger.info(f"Retrieved {len(hosts)} hosts using v4 SDK")
            return hosts
            
        except (ClusterMgmtApiException, Exception) as e:
            self._handle_api_exception("get_hosts", e)
            return []
    
    def get_vms(self) -> List[Dict]:
        """Get list of all VMs"""
        try:
            logger.debug("Fetching VMs using v4 SDK")
            
            # Use the VM API to list all VMs
            response = self.vm_api.list_vms(
                _limit=1000,  # Set a reasonable limit
                _page=1
            )
            
            vms = []
            if hasattr(response, 'data') and response.data:
                for vm in response.data:
                    # Convert the SDK object to dictionary format
                    vm_dict = {
                        'metadata': {
                            'uuid': getattr(vm, 'ext_id', None),
                            'name': getattr(vm, 'name', 'Unknown')
                        },
                        'spec': {
                            'name': getattr(vm, 'name', 'Unknown')
                        },
                        'status': {
                            'state': 'COMPLETE'  # Assume complete for listed VMs
                        }
                    }
                    vms.append(vm_dict)
            
            self._mark_success()
            logger.info(f"Retrieved {len(vms)} VMs using v4 SDK")
            return vms
            
        except (VmmApiException, Exception) as e:
            self._handle_api_exception("get_vms", e)
            return []
    
    def get_cluster_stats(self, cluster_uuid: str) -> Optional[Dict]:
        """Get performance statistics for a specific cluster"""
        try:
            logger.debug(f"Fetching cluster stats for {cluster_uuid} using v4 SDK")
            
            # Create time range for the last 5 minutes
            end_time = datetime.now()
            start_time = end_time - timedelta(minutes=5)
            
            # Prepare the request parameters
            kwargs = {
                'ext_id': cluster_uuid,
                '_stat_type': 'AVG',  # Average values
                '_start_time': start_time.isoformat() + 'Z',
                '_end_time': end_time.isoformat() + 'Z'
            }
            
            try:
                # Try to get cluster statistics
                response = self.clusters_api.get_cluster_stats_by_id(**kwargs)
                
                if hasattr(response, 'data') and response.data:
                    stats_data = response.data
                    
                    # Convert to the expected format
                    stats = {}
                    
                    # Map v4 SDK stats to our expected format
                    if hasattr(stats_data, 'hypervisor_cpu_usage_ppm'):
                        stats['hypervisor_cpu_usage_ppm'] = getattr(stats_data, 'hypervisor_cpu_usage_ppm', 0)
                    
                    if hasattr(stats_data, 'aggregate_hypervisor_memory_usage_ppm'):
                        stats['hypervisor_memory_usage_ppm'] = getattr(stats_data, 'aggregate_hypervisor_memory_usage_ppm', 0)
                    
                    if hasattr(stats_data, 'controller_avg_io_latency_usecs'):
                        stats['controller_avg_io_latency_usecs'] = getattr(stats_data, 'controller_avg_io_latency_usecs', 0)
                    
                    if hasattr(stats_data, 'controller_avg_read_io_latency_usecs'):
                        stats['controller_avg_read_io_latency_usecs'] = getattr(stats_data, 'controller_avg_read_io_latency_usecs', 0)
                    
                    if hasattr(stats_data, 'controller_avg_write_io_latency_usecs'):
                        stats['controller_avg_write_io_latency_usecs'] = getattr(stats_data, 'controller_avg_write_io_latency_usecs', 0)
                    
                    if hasattr(stats_data, 'controller_io_bandwidth_kbps'):
                        stats['controller_io_bandwidth_kBps'] = getattr(stats_data, 'controller_io_bandwidth_kbps', 0)
                    
                    if hasattr(stats_data, 'controller_num_iops'):
                        stats['controller_num_iops'] = getattr(stats_data, 'controller_num_iops', 0)
                    
                    self._mark_success()
                    return stats
                else:
                    logger.warning(f"No stats data returned for cluster {cluster_uuid}")
                    return None
                    
            except (ClusterMgmtApiException, Exception) as stats_error:
                # If statistics endpoint is not available, return None gracefully
                logger.debug(f"Statistics not available for cluster {cluster_uuid}: {stats_error}")
                return None
            
        except Exception as e:
            logger.error(f"Error getting cluster stats for {cluster_uuid}: {e}")
            return None
    
    def get_host_stats(self, host_uuid: str) -> Optional[Dict]:
        """Get performance statistics for a specific host"""
        try:
            logger.debug(f"Fetching host stats for {host_uuid} using v4 SDK")
            
            # Create time range for the last 5 minutes
            end_time = datetime.now()
            start_time = end_time - timedelta(minutes=5)
            
            # Prepare the request parameters
            kwargs = {
                'ext_id': host_uuid,
                '_stat_type': 'AVG',  # Average values
                '_start_time': start_time.isoformat() + 'Z',
                '_end_time': end_time.isoformat() + 'Z'
            }
            
            try:
                # Try to get host statistics
                response = self.hosts_api.get_host_stats_by_id(**kwargs)
                
                if hasattr(response, 'data') and response.data:
                    stats_data = response.data
                    
                    # Convert to the expected format
                    stats = {}
                    
                    # Map v4 SDK stats to our expected format
                    if hasattr(stats_data, 'hypervisor_cpu_usage_ppm'):
                        stats['hypervisor_cpu_usage_ppm'] = getattr(stats_data, 'hypervisor_cpu_usage_ppm', 0)
                    
                    if hasattr(stats_data, 'hypervisor_memory_usage_ppm'):
                        stats['hypervisor_memory_usage_ppm'] = getattr(stats_data, 'hypervisor_memory_usage_ppm', 0)
                    
                    if hasattr(stats_data, 'controller_avg_io_latency_usecs'):
                        stats['controller_avg_io_latency_usecs'] = getattr(stats_data, 'controller_avg_io_latency_usecs', 0)
                    
                    if hasattr(stats_data, 'controller_io_bandwidth_kbps'):
                        stats['controller_io_bandwidth_kBps'] = getattr(stats_data, 'controller_io_bandwidth_kbps', 0)
                    
                    if hasattr(stats_data, 'controller_num_iops'):
                        stats['controller_num_iops'] = getattr(stats_data, 'controller_num_iops', 0)
                    
                    if hasattr(stats_data, 'hypervisor_num_vms'):
                        stats['hypervisor_num_vms'] = getattr(stats_data, 'hypervisor_num_vms', 0)
                    
                    self._mark_success()
                    return stats
                else:
                    logger.warning(f"No stats data returned for host {host_uuid}")
                    return None
                    
            except (ClusterMgmtApiException, Exception) as stats_error:
                # If statistics endpoint is not available, return None gracefully
                logger.debug(f"Statistics not available for host {host_uuid}: {stats_error}")
                return None
            
        except Exception as e:
            logger.error(f"Error getting host stats for {host_uuid}: {e}")
            return None
    
    def get_vm_stats(self, vm_uuid: str) -> Optional[Dict]:
        """Get performance statistics for a specific VM"""
        try:
            logger.debug(f"Fetching VM stats for {vm_uuid} using v4 SDK")
            
            # Create time range for the last 5 minutes
            end_time = datetime.now()
            start_time = end_time - timedelta(minutes=5)
            
            # Prepare the request parameters
            kwargs = {
                'ext_id': vm_uuid,
                '_stat_type': 'AVG',  # Average values
                '_start_time': start_time.isoformat() + 'Z',
                '_end_time': end_time.isoformat() + 'Z'
            }
            
            try:
                # Try to get VM statistics
                response = self.vm_api.get_vm_stats_by_id(**kwargs)
                
                if hasattr(response, 'data') and response.data:
                    stats_data = response.data
                    
                    # Convert to the expected format
                    stats = {}
                    
                    # Map v4 SDK stats to our expected format
                    if hasattr(stats_data, 'hypervisor_cpu_usage_ppm'):
                        stats['hypervisor_cpu_usage_ppm'] = getattr(stats_data, 'hypervisor_cpu_usage_ppm', 0)
                    
                    if hasattr(stats_data, 'hypervisor_memory_usage_ppm'):
                        stats['hypervisor_memory_usage_ppm'] = getattr(stats_data, 'hypervisor_memory_usage_ppm', 0)
                    
                    if hasattr(stats_data, 'storage_usage_bytes'):
                        stats['storage_usage_bytes'] = getattr(stats_data, 'storage_usage_bytes', 0)
                    
                    self._mark_success()
                    return stats
                else:
                    logger.warning(f"No stats data returned for VM {vm_uuid}")
                    return None
                    
            except (VmmApiException, Exception) as stats_error:
                # If statistics endpoint is not available, return None gracefully
                logger.debug(f"Statistics not available for VM {vm_uuid}: {stats_error}")
                return None
            
        except Exception as e:
            logger.error(f"Error getting VM stats for {vm_uuid}: {e}")
            return None
    
    def close(self):
        """Close the API clients and cleanup"""
        try:
            # Close all API clients
            if hasattr(self, 'clustermgmt_client'):
                # Note: v4 SDK clients don't have explicit close methods
                # but we can clear references
                self.clustermgmt_client = None
                self.clusters_api = None
                self.hosts_api = None
            
            if hasattr(self, 'vmm_client'):
                self.vmm_client = None
                self.vm_api = None
            
            if hasattr(self, 'prism_client'):
                self.prism_client = None
            
            logger.debug("Nutanix v4 SDK clients closed")
            
        except Exception as e:
            logger.error(f"Error closing API clients: {e}")
