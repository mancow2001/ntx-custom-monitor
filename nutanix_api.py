#!/usr/bin/env python3
"""
Nutanix API Client Module

Handles communication with Nutanix Prism Central API.
"""

import logging
import time
from typing import Dict, List, Optional, Any
import requests
import urllib3
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

class NutanixAPIError(Exception):
    """Custom exception for Nutanix API errors"""
    pass

class NutanixAPIClient:
    """Handles communication with Nutanix Prism Central API"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.base_url = f"https://{config['prism_central_ip']}:{config.get('port', 9440)}/api/nutanix/v3"
        self.auth = (config['username'], config['password'])
        
        # Disable SSL warnings if verification is disabled
        if not config.get('ssl_verify', False):
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        # Setup session with retry strategy
        self.session = self._create_session()
        
        # Connection health tracking
        self.last_successful_request = None
        self.consecutive_failures = 0
        self.max_failures = config.get('retry_count', 3)
        
    def _create_session(self) -> requests.Session:
        """Create requests session with retry strategy"""
        session = requests.Session()
        session.auth = self.auth
        session.verify = self.config.get('ssl_verify', False)
        
        # Setup retry strategy
        retry_strategy = Retry(
            total=self.config.get('retry_count', 3),
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            method_whitelist=["HEAD", "GET", "PUT", "DELETE", "OPTIONS", "TRACE", "POST"]
        )
        
        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=self.config.get('connection_pool_size', 5),
            pool_maxsize=self.config.get('connection_pool_size', 5)
        )
        
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        return session
    
    def _make_request(self, method: str, endpoint: str, data: Optional[dict] = None) -> Optional[dict]:
        """Make HTTP request to Nutanix API with error handling"""
        url = f"{self.base_url}/{endpoint}"
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        
        timeout = self.config.get('timeout', 30)
        
        try:
            start_time = time.time()
            
            if method.upper() == 'GET':
                response = self.session.get(url, headers=headers, timeout=timeout)
            elif method.upper() == 'POST':
                response = self.session.post(url, headers=headers, json=data, timeout=timeout)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            # Log request details if debugging is enabled
            if logger.isEnabledFor(logging.DEBUG):
                duration = time.time() - start_time
                logger.debug(f"{method} {endpoint} - {response.status_code} ({duration:.2f}s)")
            
            response.raise_for_status()
            
            # Reset failure counter on success
            self.consecutive_failures = 0
            self.last_successful_request = time.time()
            
            return response.json()
            
        except requests.exceptions.HTTPError as e:
            self.consecutive_failures += 1
            logger.error(f"HTTP Error {response.status_code} for {endpoint}: {e}")
            
            if response.status_code == 401:
                raise NutanixAPIError("Authentication failed - check credentials")
            elif response.status_code == 403:
                raise NutanixAPIError("Access forbidden - check user permissions")
            elif response.status_code == 404:
                logger.warning(f"Endpoint not found: {endpoint}")
                return None
            else:
                raise NutanixAPIError(f"HTTP {response.status_code}: {e}")
                
        except requests.exceptions.ConnectionError as e:
            self.consecutive_failures += 1
            logger.error(f"Connection error for {endpoint}: {e}")
            raise NutanixAPIError(f"Connection failed: {e}")
            
        except requests.exceptions.Timeout as e:
            self.consecutive_failures += 1
            logger.error(f"Timeout error for {endpoint}: {e}")
            raise NutanixAPIError(f"Request timeout: {e}")
            
        except requests.exceptions.RequestException as e:
            self.consecutive_failures += 1
            logger.error(f"Request error for {endpoint}: {e}")
            raise NutanixAPIError(f"Request failed: {e}")
    
    def health_check(self) -> bool:
        """Perform a health check on the API connection"""
        try:
            # Simple API call to test connectivity
            response = self._make_request("GET", "clusters/list")
            return response is not None
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
            data = {"kind": "cluster"}
            response = self._make_request("POST", "clusters/list", data)
            clusters = response.get("entities", []) if response else []
            logger.info(f"Retrieved {len(clusters)} clusters")
            return clusters
        except Exception as e:
            logger.error(f"Failed to get clusters: {e}")
            return []
    
    def get_hosts(self) -> List[Dict]:
        """Get list of all hosts"""
        try:
            data = {"kind": "host"}
            response = self._make_request("POST", "hosts/list", data)
            hosts = response.get("entities", []) if response else []
            logger.info(f"Retrieved {len(hosts)} hosts")
            return hosts
        except Exception as e:
            logger.error(f"Failed to get hosts: {e}")
            return []
    
    def get_vms(self) -> List[Dict]:
        """Get list of all VMs"""
        try:
            data = {"kind": "vm"}
            response = self._make_request("POST", "vms/list", data)
            vms = response.get("entities", []) if response else []
            logger.info(f"Retrieved {len(vms)} VMs")
            return vms
        except Exception as e:
            logger.error(f"Failed to get VMs: {e}")
            return []
    
    def get_cluster_stats(self, cluster_uuid: str) -> Optional[Dict]:
        """Get performance statistics for a specific cluster"""
        try:
            endpoint = f"clusters/{cluster_uuid}/stats"
            return self._make_request("GET", endpoint)
        except Exception as e:
            logger.error(f"Failed to get stats for cluster {cluster_uuid}: {e}")
            return None
    
    def get_host_stats(self, host_uuid: str) -> Optional[Dict]:
        """Get performance statistics for a specific host"""
        try:
            endpoint = f"hosts/{host_uuid}/stats"
            return self._make_request("GET", endpoint)
        except Exception as e:
            logger.error(f"Failed to get stats for host {host_uuid}: {e}")
            return None
    
    def get_vm_stats(self, vm_uuid: str) -> Optional[Dict]:
        """Get performance statistics for a specific VM"""
        try:
            endpoint = f"vms/{vm_uuid}/stats"
            return self._make_request("GET", endpoint)
        except Exception as e:
            logger.error(f"Failed to get stats for VM {vm_uuid}: {e}")
            return None
    
    def close(self):
        """Close the session and cleanup"""
        if self.session:
            self.session.close()
            logger.debug("Nutanix API session closed")
