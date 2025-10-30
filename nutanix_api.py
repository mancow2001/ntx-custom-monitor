#!/usr/bin/env python3
"""
Nutanix API Client Module (Modern SDK) - CORRECTED VERSION

Handles communication with Nutanix Prism Central using the official modern SDK.
"""

import logging
import time
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Nutanix modern SDK imports with error handling
try:
    from ntnx_clustermgmt_py_client import Configuration as ClusterMgmtConfig
    from ntnx_clustermgmt_py_client import ApiClient as ClusterMgmtApiClient
    from ntnx_clustermgmt_py_client.api.clusters_api import ClustersApi
    from ntnx_clustermgmt_py_client.rest import ApiException as ClusterMgmtApiException
    CLUSTERMGMT_AVAILABLE = True
    logger.debug("Cluster Management SDK imported successfully")
except ImportError as e:
    logger.warning(f"Cluster Management SDK not available: {e}")
    CLUSTERMGMT_AVAILABLE = False
    ClusterMgmtConfig = None
    ClusterMgmtApiClient = None
    ClustersApi = None
    ClusterMgmtApiException = Exception

# Try to import hosts API separately as it might not be available
try:
    from ntnx_clustermgmt_py_client.api.hosts_api import HostsApi
    HOSTS_API_AVAILABLE = True
    logger.debug("Hosts API imported successfully")
except ImportError as e:
    logger.warning(f"Hosts API not available: {e}")
    HOSTS_API_AVAILABLE = False
    HostsApi = None

try:
    from ntnx_vmm_py_client import Configuration as VmmConfig
    from ntnx_vmm_py_client import ApiClient as VmmApiClient
    from ntnx_vmm_py_client.api.vms_api import VmsApi  # Fixed: was VmApi, should be VmsApi
    from ntnx_vmm_py_client.rest import ApiException as VmmApiException
    VMM_AVAILABLE = True
    logger.debug("VMM SDK imported successfully")
except ImportError as e:
    logger.warning(f"VMM SDK not available: {e}")
    VMM_AVAILABLE = False
    VmmConfig = None
    VmmApiClient = None
    VmsApi = None
    VmmApiException = Exception

try:
    from ntnx_prism_py_client import Configuration as PrismConfig
    from ntnx_prism_py_client import ApiClient as PrismApiClient
    from ntnx_prism_py_client.rest import ApiException as PrismApiException
    PRISM_AVAILABLE = True
    logger.debug("Prism SDK imported successfully")
except ImportError as e:
    logger.warning(f"Prism SDK not available: {e}")
    PRISM_AVAILABLE = False
    PrismConfig = None
    PrismApiClient = None
    PrismApiException = Exception

class NutanixAPIError(Exception):
    """Custom exception for Nutanix API errors"""
    pass

class NutanixAPIClient:
    """Handles communication with Nutanix Prism Central using modern SDK"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.prism_central_ip = config['prism_central_ip']
        self.port = config.get('port', 9440)
        self.username = config['username']
        self.password = config['password']
        self.ssl_verify = config.get('ssl_verify', False)
        self.timeout = config.get('timeout', 30)
        
        # Get SDK configuration
        self.sdk_config = config.get('sdk_config', {})
        
        # Connection health tracking
        self.last_successful_request = None
        self.consecutive_failures = 0
        self.max_failures = config.get('retry_count', 3)
        
        # Check which SDKs are available vs enabled
        self.available_sdks = {
            'clustermgmt': CLUSTERMGMT_AVAILABLE and self.sdk_config.get('enable_clustermgmt', True),
            'hosts_api': HOSTS_API_AVAILABLE and self.sdk_config.get('enable_clustermgmt', True),
            'vmm': VMM_AVAILABLE and self.sdk_config.get('enable_vmm', True),
            'prism': PRISM_AVAILABLE and self.sdk_config.get('enable_prism', True)
        }
        
        logger.info(f"SDK availability: {self.available_sdks}")
        
        if not any(self.available_sdks.values()):
            raise NutanixAPIError("No Nutanix SDK modules are available or enabled")
        
        # Initialize SDK configurations
        self._setup_sdk_configs()
        
        # Initialize API clients
        self._setup_api_clients()
        
        logger.info(f"Nutanix modern SDK client initialized for {self.prism_central_ip}:{self.port}")
    
    def _setup_sdk_configs(self):
        """Setup SDK configurations for all namespaces"""
        # CORRECTED: Proper configuration setup for modern SDK
        base_url = f"https://{self.prism_central_ip}:{self.port}"
        
        # Cluster Management configuration
        if CLUSTERMGMT_AVAILABLE:
            self.clustermgmt_config = ClusterMgmtConfig()
            self.clustermgmt_config.host = base_url
            self.clustermgmt_config.username = self.username
            self.clustermgmt_config.password = self.password
            self.clustermgmt_config.verify_ssl = self.ssl_verify
            self.clustermgmt_config.connection_pool_maxsize = self.config.get('connection_pool_size', 5)
            # IMPORTANT: Disable SSL warnings if SSL verification is disabled
            if not self.ssl_verify:
                import urllib3
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        # VMM configuration
        if VMM_AVAILABLE:
            self.vmm_config = VmmConfig()
            self.vmm_config.host = base_url
            self.vmm_config.username = self.username
            self.vmm_config.password = self.password
            self.vmm_config.verify_ssl = self.ssl_verify
            self.vmm_config.connection_pool_maxsize = self.config.get('connection_pool_size', 5)
        
        # Prism configuration
        if PRISM_AVAILABLE:
            self.prism_config = PrismConfig()
            self.prism_config.host = base_url
            self.prism_config.username = self.username
            self.prism_config.password = self.password
            self.prism_config.verify_ssl = self.ssl_verify
            self.prism_config.connection_pool_maxsize = self.config.get('connection_pool_size', 5)
    
    def _setup_api_clients(self):
        """Setup API clients for all namespaces"""
        try:
            # Cluster Management API client
            if CLUSTERMGMT_AVAILABLE:
                self.clustermgmt_client = ClusterMgmtApiClient(configuration=self.clustermgmt_config)
                self.clusters_api = ClustersApi(api_client=self.clustermgmt_client)
                
                # Only setup hosts API if available
                if HOSTS_API_AVAILABLE:
                    self.hosts_api = HostsApi(api_client=self.clustermgmt_client)
                else:
                    self.hosts_api = None
                    logger.warning("Hosts API not available, host metrics will be disabled")
            else:
                self.clustermgmt_client = None
                self.clusters_api = None
                self.hosts_api = None
            
            # VMM API client
            if VMM_AVAILABLE:
                self.vmm_client = VmmApiClient(configuration=self.vmm_config)
                self.vms_api = VmsApi(api_client=self.vmm_client)  # CORRECTED: VmsApi not VmApi
            else:
                self.vmm_client = None
                self.vms_api = None
            
            # Prism API client
            if PRISM_AVAILABLE:
                self.prism_client = PrismApiClient(configuration=self.prism_config)
            else:
                self.prism_client = None
            
            logger.info("Modern SDK API clients initialized successfully")
            
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
        """Get list of all clusters with pagination support - CORRECTED VERSION"""
        if not CLUSTERMGMT_AVAILABLE or not self.clusters_api:
            logger.warning("Cluster Management API not available")
            return []
        
        try:
            logger.debug("Fetching clusters using modern SDK")
            
            all_clusters = []
            page = 1
            limit = 100  # Maximum allowed by API
            
            while True:
                # CORRECTED: Use proper SDK method and parameters with pagination
                try:
                    # Method 1: Try list_clusters with correct parameters
                    response = self.clusters_api.list_clusters(
                        _limit=limit,  # FIXED: Maximum allowed by API is 100
                        _page=page     # FIXED: Added underscore prefix
                    )
                except AttributeError:
                    try:
                        # Method 2: Try get_clusters
                        response = self.clusters_api.get_clusters(
                            _limit=limit,
                            _page=page
                        )
                    except AttributeError:
                        # Method 3: Try without parameters (no pagination)
                        response = self.clusters_api.list_clusters()
                        # If no pagination support, just process once and break
                        page = None
                
                # CORRECTED: Proper response handling
                if response:
                    # Check different possible response structures
                    if hasattr(response, 'data') and response.data:
                        cluster_list = response.data
                    elif hasattr(response, 'entities'):
                        cluster_list = response.entities
                    elif isinstance(response, list):
                        cluster_list = response
                    else:
                        cluster_list = [response]
                    
                    # If no results, we're done
                    if not cluster_list:
                        break
                    
                    for cluster in cluster_list:
                        # CORRECTED: Proper attribute extraction
                        cluster_dict = {
                            'metadata': {
                                'uuid': self._safe_get_attr(cluster, ['ext_id', 'uuid', 'id']),
                                'name': self._safe_get_attr(cluster, ['name', 'cluster_name'])
                            },
                            'spec': {
                                'name': self._safe_get_attr(cluster, ['name', 'cluster_name'])
                            },
                            'status': {
                                'state': 'COMPLETE'  # Assume complete for listed clusters
                            }
                        }
                        
                        # Only add if we have a valid UUID
                        if cluster_dict['metadata']['uuid']:
                            all_clusters.append(cluster_dict)
                            logger.debug(f"Added cluster: {cluster_dict['metadata']['name']} ({cluster_dict['metadata']['uuid']})")
                    
                    # Check if we got fewer results than the limit (last page)
                    if page is None or len(cluster_list) < limit:
                        break
                    
                    # Move to next page
                    page += 1
                else:
                    break
            
            self._mark_success()
            logger.info(f"Retrieved {len(all_clusters)} clusters using modern SDK")
            return all_clusters
            
        except (ClusterMgmtApiException, Exception) as e:
            logger.error(f"Error fetching clusters: {e}")
            logger.debug(f"Available methods on clusters_api: {[method for method in dir(self.clusters_api) if not method.startswith('_')]}")
            self._handle_api_exception("get_clusters", e)
            return []
    
    def get_hosts(self) -> List[Dict]:
        """Get list of all hosts with pagination support - CORRECTED VERSION"""
        if not HOSTS_API_AVAILABLE or not self.hosts_api:
            logger.warning("Hosts API not available")
            return []
        
        try:
            logger.debug("Fetching hosts using modern SDK")
            
            all_hosts = []
            page = 1
            limit = 100  # Maximum allowed by API
            
            while True:
                # CORRECTED: Use proper SDK method and parameters with pagination
                try:
                    # Method 1: Try list_hosts with correct parameters
                    response = self.hosts_api.list_hosts(
                        _limit=limit,  # FIXED: Maximum allowed by API is 100
                        _page=page     # FIXED: Added underscore prefix
                    )
                except AttributeError:
                    try:
                        # Method 2: Try get_hosts
                        response = self.hosts_api.get_hosts(
                            _limit=limit,
                            _page=page
                        )
                    except AttributeError:
                        # Method 3: Try without parameters (no pagination)
                        response = self.hosts_api.list_hosts()
                        # If no pagination support, just process once and break
                        page = None
                
                # CORRECTED: Proper response handling
                if response:
                    # Check different possible response structures
                    if hasattr(response, 'data') and response.data:
                        host_list = response.data
                    elif hasattr(response, 'entities'):
                        host_list = response.entities
                    elif isinstance(response, list):
                        host_list = response
                    else:
                        host_list = [response]
                    
                    # If no results, we're done
                    if not host_list:
                        break
                    
                    for host in host_list:
                        # CORRECTED: Proper attribute extraction
                        host_dict = {
                            'metadata': {
                                'uuid': self._safe_get_attr(host, ['ext_id', 'uuid', 'id']),
                                'name': self._safe_get_attr(host, ['name', 'host_name'])
                            },
                            'spec': {
                                'name': self._safe_get_attr(host, ['name', 'host_name'])
                            },
                            'status': {
                                'state': 'COMPLETE'  # Assume complete for listed hosts
                            }
                        }
                        
                        # Only add if we have a valid UUID
                        if host_dict['metadata']['uuid']:
                            all_hosts.append(host_dict)
                            logger.debug(f"Added host: {host_dict['metadata']['name']} ({host_dict['metadata']['uuid']})")
                    
                    # Check if we got fewer results than the limit (last page)
                    if page is None or len(host_list) < limit:
                        break
                    
                    # Move to next page
                    page += 1
                else:
                    break
            
            self._mark_success()
            logger.info(f"Retrieved {len(all_hosts)} hosts using modern SDK")
            return all_hosts
            
        except (ClusterMgmtApiException, Exception) as e:
            logger.error(f"Error fetching hosts: {e}")
            logger.debug(f"Available methods on hosts_api: {[method for method in dir(self.hosts_api) if not method.startswith('_')]}")
            self._handle_api_exception("get_hosts", e)
            return []
    
    def get_vms(self) -> List[Dict]:
        """Get list of all VMs with pagination support - CORRECTED VERSION"""
        if not VMM_AVAILABLE or not self.vms_api:
            logger.warning("VMM API not available")
            return []
        
        try:
            logger.debug("Fetching VMs using modern SDK")
            
            all_vms = []
            page = 1
            limit = 100  # Maximum allowed by API
            
            while True:
                # CORRECTED: Use proper SDK method and parameters with pagination
                try:
                    # Method 1: Try list_vms with correct parameters
                    response = self.vms_api.list_vms(
                        _limit=limit,  # FIXED: Maximum allowed by API is 100
                        _page=page     # FIXED: Added underscore prefix
                    )
                except AttributeError:
                    try:
                        # Method 2: Try get_vms
                        response = self.vms_api.get_vms(
                            _limit=limit,
                            _page=page
                        )
                    except AttributeError:
                        # Method 3: Try without parameters (no pagination)
                        response = self.vms_api.list_vms()
                        # If no pagination support, just process once and break
                        page = None
                
                # CORRECTED: Proper response handling
                if response:
                    # Check different possible response structures
                    if hasattr(response, 'data') and response.data:
                        vm_list = response.data
                    elif hasattr(response, 'entities'):
                        vm_list = response.entities
                    elif isinstance(response, list):
                        vm_list = response
                    else:
                        vm_list = [response]
                    
                    # If no results, we're done
                    if not vm_list:
                        break
                    
                    for vm in vm_list:
                        # CORRECTED: Proper attribute extraction
                        vm_dict = {
                            'metadata': {
                                'uuid': self._safe_get_attr(vm, ['ext_id', 'uuid', 'id']),
                                'name': self._safe_get_attr(vm, ['name', 'vm_name'])
                            },
                            'spec': {
                                'name': self._safe_get_attr(vm, ['name', 'vm_name'])
                            },
                            'status': {
                                'state': 'COMPLETE'  # Assume complete for listed VMs
                            }
                        }
                        
                        # Only add if we have a valid UUID
                        if vm_dict['metadata']['uuid']:
                            all_vms.append(vm_dict)
                            logger.debug(f"Added VM: {vm_dict['metadata']['name']} ({vm_dict['metadata']['uuid']})")
                    
                    # Check if we got fewer results than the limit (last page)
                    if page is None or len(vm_list) < limit:
                        break
                    
                    # Move to next page
                    page += 1
                else:
                    break
            
            self._mark_success()
            logger.info(f"Retrieved {len(all_vms)} VMs using modern SDK")
            return all_vms
            
        except (VmmApiException, Exception) as e:
            logger.error(f"Error fetching VMs: {e}")
            logger.debug(f"Available methods on vms_api: {[method for method in dir(self.vms_api) if not method.startswith('_')]}")
            self._handle_api_exception("get_vms", e)
            return []
    
    def _safe_get_attr(self, obj, attr_names: List[str]) -> Optional[str]:
        """Safely get attribute from object, trying multiple possible names"""
        for attr_name in attr_names:
            try:
                value = getattr(obj, attr_name, None)
                if value:
                    return str(value)
            except (AttributeError, TypeError):
                continue
        return None
    
    def get_cluster_stats(self, cluster_uuid: str) -> Optional[Dict]:
        """Get performance statistics for a specific cluster"""
        if not CLUSTERMGMT_AVAILABLE or not self.clusters_api:
            logger.debug("Cluster Management API not available for stats")
            return None
        
        try:
            logger.debug(f"Fetching cluster stats for {cluster_uuid} using modern SDK")
            
            # Create time range for the last 5 minutes
            end_time = datetime.now()
            start_time = end_time - timedelta(minutes=5)
            
            # Try different possible methods for getting stats
            stats_methods = [
                'get_cluster_stats_by_id',
                'get_cluster_stats',
                'get_stats_by_id',
                'list_cluster_stats'
            ]
            
            for method_name in stats_methods:
                if hasattr(self.clusters_api, method_name):
                    try:
                        method = getattr(self.clusters_api, method_name)
                        response = method(cluster_uuid)
                        
                        if response:
                            # Process the response
                            stats = self._process_stats_response(response)
                            if stats:
                                self._mark_success()
                                return stats
                    except Exception as e:
                        logger.debug(f"Method {method_name} failed: {e}")
                        continue
            
            logger.debug(f"No stats methods available for cluster {cluster_uuid}")
            return None
            
        except Exception as e:
            logger.error(f"Error getting cluster stats for {cluster_uuid}: {e}")
            return None
    
    def get_host_stats(self, host_uuid: str) -> Optional[Dict]:
        """Get performance statistics for a specific host"""
        if not HOSTS_API_AVAILABLE or not self.hosts_api:
            logger.debug("Hosts API not available for stats")
            return None
        
        try:
            logger.debug(f"Fetching host stats for {host_uuid} using modern SDK")
            
            # Try different possible methods for getting stats
            stats_methods = [
                'get_host_stats_by_id',
                'get_host_stats',
                'get_stats_by_id',
                'list_host_stats'
            ]
            
            for method_name in stats_methods:
                if hasattr(self.hosts_api, method_name):
                    try:
                        method = getattr(self.hosts_api, method_name)
                        response = method(host_uuid)
                        
                        if response:
                            # Process the response
                            stats = self._process_stats_response(response)
                            if stats:
                                self._mark_success()
                                return stats
                    except Exception as e:
                        logger.debug(f"Method {method_name} failed: {e}")
                        continue
            
            logger.debug(f"No stats methods available for host {host_uuid}")
            return None
            
        except Exception as e:
            logger.error(f"Error getting host stats for {host_uuid}: {e}")
            return None
    
    def get_vm_stats(self, vm_uuid: str) -> Optional[Dict]:
        """Get performance statistics for a specific VM"""
        if not VMM_AVAILABLE or not self.vms_api:
            logger.debug("VMM API not available for stats")
            return None
        
        try:
            logger.debug(f"Fetching VM stats for {vm_uuid} using modern SDK")
            
            # Try different possible methods for getting stats
            stats_methods = [
                'get_vm_stats_by_id',
                'get_vm_stats',
                'get_stats_by_id',
                'list_vm_stats'
            ]
            
            for method_name in stats_methods:
                if hasattr(self.vms_api, method_name):
                    try:
                        method = getattr(self.vms_api, method_name)
                        response = method(vm_uuid)
                        
                        if response:
                            # Process the response
                            stats = self._process_stats_response(response)
                            if stats:
                                self._mark_success()
                                return stats
                    except Exception as e:
                        logger.debug(f"Method {method_name} failed: {e}")
                        continue
            
            logger.debug(f"No stats methods available for VM {vm_uuid}")
            return None
            
        except Exception as e:
            logger.error(f"Error getting VM stats for {vm_uuid}: {e}")
            return None
    
    def _process_stats_response(self, response) -> Optional[Dict]:
        """Process statistics response into common format"""
        try:
            stats = {}
            
            # Handle different response types
            if hasattr(response, 'data'):
                stats_data = response.data
            elif hasattr(response, 'stats'):
                stats_data = response.stats
            else:
                stats_data = response
            
            # Extract common metrics
            if hasattr(stats_data, '__dict__'):
                for attr_name, attr_value in stats_data.__dict__.items():
                    if attr_value is not None:
                        stats[attr_name] = attr_value
            
            return stats if stats else None
            
        except Exception as e:
            logger.debug(f"Error processing stats response: {e}")
            return None
    
    def get_available_apis(self) -> Dict[str, bool]:
        """Get information about which APIs are available"""
        return self.available_sdks.copy()
    
    def close(self):
        """Close the API clients and cleanup"""
        try:
            # Close all API clients
            if hasattr(self, 'clustermgmt_client'):
                # Note: modern SDK clients don't have explicit close methods
                # but we can clear references
                self.clustermgmt_client = None
                self.clusters_api = None
                self.hosts_api = None
            
            if hasattr(self, 'vmm_client'):
                self.vmm_client = None
                self.vms_api = None
            
            if hasattr(self, 'prism_client'):
                self.prism_client = None
            
            logger.debug("Nutanix modern SDK clients closed")
            
        except Exception as e:
            logger.error(f"Error closing API clients: {e}")
