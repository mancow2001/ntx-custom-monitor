#!/usr/bin/env python3
"""
Metrics Collector Module

Collects and processes performance statistics from Nutanix infrastructure.
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

from nutanix_api import NutanixAPIClient

logger = logging.getLogger(__name__)

class MetricsCollector:
    """Collects and processes performance statistics"""
    
    def __init__(self, api_client: NutanixAPIClient, config: Dict[str, Any]):
        self.api = api_client
        self.config = config
        self.metrics_config = config.get('metrics', {})
        self.performance_config = config.get('performance', {})
        
        # Cache for storing collected metrics
        self.stats_cache = {}
        self.last_update = None
        self.cache_timeout = self.performance_config.get('cache_timeout', 30)
        self.cache_lock = threading.RLock()
        
        # Performance tracking
        self.collection_times = []
        self.max_collection_history = 10
        
        # Async semaphore for controlling concurrent requests
        self.max_concurrent = self.performance_config.get('max_concurrent_requests', 10)
    
    async def collect_all_stats(self) -> Dict[str, Any]:
        """Collect performance statistics from all infrastructure components"""
        start_time = time.time()
        
        try:
            # Check if cached data is still valid
            if self._is_cache_valid():
                logger.debug("Using cached metrics data")
                return self.stats_cache
            
            logger.info("Starting metrics collection...")
            
            stats = {
                'clusters': {},
                'hosts': {},
                'vms': {},
                'timestamp': datetime.now().isoformat(),
                'collection_time': 0,
                'metadata': {
                    'collector_version': '1.0.0',
                    'api_healthy': self.api.is_healthy(),
                    'cache_enabled': self.performance_config.get('enable_metrics_cache', True)
                }
            }
            
            # Collect different types of metrics concurrently
            tasks = []
            
            if self.metrics_config.get('cluster', {}).get('enabled', True):
                tasks.append(self._collect_cluster_metrics())
            
            if self.metrics_config.get('host', {}).get('enabled', True):
                tasks.append(self._collect_host_metrics())
            
            if self.metrics_config.get('vm', {}).get('enabled', False):
                tasks.append(self._collect_vm_metrics())
            
            # Execute all collection tasks
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(f"Collection task {i} failed: {result}")
                    continue
                
                if isinstance(result, dict):
                    stats.update(result)
            
            # Calculate collection time
            collection_time = time.time() - start_time
            stats['collection_time'] = round(collection_time, 2)
            
            # Update cache
            with self.cache_lock:
                self.stats_cache = stats
                self.last_update = datetime.now()
            
            # Track performance
            self._track_collection_performance(collection_time)
            
            logger.info(f"Metrics collection completed in {collection_time:.2f} seconds")
            return stats
            
        except Exception as e:
            logger.error(f"Failed to collect metrics: {e}")
            # Return cached data if available, otherwise empty stats
            return self.stats_cache if self.stats_cache else self._empty_stats()
    
    async def _collect_cluster_metrics(self) -> Dict[str, Any]:
        """Collect cluster performance metrics"""
        cluster_stats = {}
        cluster_config = self.metrics_config.get('cluster', {})
        
        try:
            clusters = self.api.get_clusters()
            if not clusters:
                logger.warning("No clusters found")
                return {'clusters': cluster_stats}
            
            # Create semaphore for controlling concurrent requests
            semaphore = asyncio.Semaphore(self.max_concurrent)
            
            async def collect_single_cluster(cluster):
                async with semaphore:
                    return await self._collect_single_cluster_stats(cluster, cluster_config)
            
            # Collect stats for all clusters concurrently
            tasks = [collect_single_cluster(cluster) for cluster in clusters]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results
            for result in results:
                if isinstance(result, Exception):
                    logger.error(f"Cluster collection failed: {result}")
                    continue
                
                if isinstance(result, dict) and result:
                    cluster_stats.update(result)
            
            logger.debug(f"Collected metrics for {len(cluster_stats)} clusters")
            
        except Exception as e:
            logger.error(f"Failed to collect cluster metrics: {e}")
        
        return {'clusters': cluster_stats}
    
    async def _collect_single_cluster_stats(self, cluster: Dict, config: Dict) -> Dict[str, Any]:
        """Collect statistics for a single cluster"""
        cluster_uuid = cluster.get('metadata', {}).get('uuid')
        cluster_name = cluster.get('spec', {}).get('name', 'Unknown')
        
        if not cluster_uuid:
            logger.warning(f"Cluster {cluster_name} has no UUID")
            return {}
        
        try:
            # Run API call in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            raw_stats = await loop.run_in_executor(
                None, self.api.get_cluster_stats, cluster_uuid
            )
            
            if not raw_stats:
                logger.warning(f"No stats returned for cluster {cluster_name}")
                return {}
            
            processed_stats = self._process_cluster_stats(raw_stats, config)
            
            return {
                cluster_uuid: {
                    'name': cluster_name,
                    'uuid': cluster_uuid,
                    'stats': processed_stats,
                    'last_updated': datetime.now().isoformat()
                }
            }
            
        except Exception as e:
            logger.error(f"Failed to collect stats for cluster {cluster_name}: {e}")
            return {}
    
    async def _collect_host_metrics(self) -> Dict[str, Any]:
        """Collect host performance metrics"""
        host_stats = {}
        host_config = self.metrics_config.get('host', {})
        
        try:
            hosts = self.api.get_hosts()
            if not hosts:
                logger.warning("No hosts found")
                return {'hosts': host_stats}
            
            # Create semaphore for controlling concurrent requests
            semaphore = asyncio.Semaphore(self.max_concurrent)
            
            async def collect_single_host(host):
                async with semaphore:
                    return await self._collect_single_host_stats(host, host_config)
            
            # Collect stats for all hosts concurrently
            tasks = [collect_single_host(host) for host in hosts]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results
            for result in results:
                if isinstance(result, Exception):
                    logger.error(f"Host collection failed: {result}")
                    continue
                
                if isinstance(result, dict) and result:
                    host_stats.update(result)
            
            logger.debug(f"Collected metrics for {len(host_stats)} hosts")
            
        except Exception as e:
            logger.error(f"Failed to collect host metrics: {e}")
        
        return {'hosts': host_stats}
    
    async def _collect_single_host_stats(self, host: Dict, config: Dict) -> Dict[str, Any]:
        """Collect statistics for a single host"""
        host_uuid = host.get('metadata', {}).get('uuid')
        host_name = host.get('spec', {}).get('name', 'Unknown')
        
        if not host_uuid:
            logger.warning(f"Host {host_name} has no UUID")
            return {}
        
        try:
            # Run API call in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            raw_stats = await loop.run_in_executor(
                None, self.api.get_host_stats, host_uuid
            )
            
            if not raw_stats:
                logger.warning(f"No stats returned for host {host_name}")
                return {}
            
            processed_stats = self._process_host_stats(raw_stats, config)
            
            return {
                host_uuid: {
                    'name': host_name,
                    'uuid': host_uuid,
                    'stats': processed_stats,
                    'last_updated': datetime.now().isoformat()
                }
            }
            
        except Exception as e:
            logger.error(f"Failed to collect stats for host {host_name}: {e}")
            return {}
    
    async def _collect_vm_metrics(self) -> Dict[str, Any]:
        """Collect VM performance metrics (if enabled)"""
        vm_stats = {}
        vm_config = self.metrics_config.get('vm', {})
        
        if not vm_config.get('enabled', False):
            return {'vms': vm_stats}
        
        try:
            vms = self.api.get_vms()
            if not vms:
                logger.warning("No VMs found")
                return {'vms': vm_stats}
            
            # Limit VM collection to avoid overwhelming the API
            max_vms = 100  # Reasonable limit for VM stats collection
            if len(vms) > max_vms:
                logger.warning(f"Limiting VM collection to {max_vms} VMs (found {len(vms)})")
                vms = vms[:max_vms]
            
            # Create semaphore for controlling concurrent requests
            semaphore = asyncio.Semaphore(min(self.max_concurrent, 5))  # Limit VM concurrency
            
            async def collect_single_vm(vm):
                async with semaphore:
                    return await self._collect_single_vm_stats(vm, vm_config)
            
            # Collect stats for VMs concurrently
            tasks = [collect_single_vm(vm) for vm in vms]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results
            for result in results:
                if isinstance(result, Exception):
                    logger.error(f"VM collection failed: {result}")
                    continue
                
                if isinstance(result, dict) and result:
                    vm_stats.update(result)
            
            logger.debug(f"Collected metrics for {len(vm_stats)} VMs")
            
        except Exception as e:
            logger.error(f"Failed to collect VM metrics: {e}")
        
        return {'vms': vm_stats}
    
    async def _collect_single_vm_stats(self, vm: Dict, config: Dict) -> Dict[str, Any]:
        """Collect statistics for a single VM"""
        vm_uuid = vm.get('metadata', {}).get('uuid')
        vm_name = vm.get('spec', {}).get('name', 'Unknown')
        
        if not vm_uuid:
            logger.warning(f"VM {vm_name} has no UUID")
            return {}
        
        try:
            # Run API call in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            raw_stats = await loop.run_in_executor(
                None, self.api.get_vm_stats, vm_uuid
            )
            
            if not raw_stats:
                logger.debug(f"No stats returned for VM {vm_name}")
                return {}
            
            processed_stats = self._process_vm_stats(raw_stats, config)
            
            return {
                vm_uuid: {
                    'name': vm_name,
                    'uuid': vm_uuid,
                    'stats': processed_stats,
                    'last_updated': datetime.now().isoformat()
                }
            }
            
        except Exception as e:
            logger.debug(f"Failed to collect stats for VM {vm_name}: {e}")
            return {}
    
    def _process_cluster_stats(self, raw_stats: Dict, config: Dict) -> Dict[str, Union[float, int]]:
        """Process and normalize cluster statistics"""
        processed = {}
        
        # CPU usage
        if config.get('cpu_usage', True) and 'hypervisor_cpu_usage_ppm' in raw_stats:
            processed['cpu_usage_percent'] = round(raw_stats['hypervisor_cpu_usage_ppm'] / 10000, 2)
        
        # Memory usage
        if config.get('memory_usage', True) and 'hypervisor_memory_usage_ppm' in raw_stats:
            processed['memory_usage_percent'] = round(raw_stats['hypervisor_memory_usage_ppm'] / 10000, 2)
        
        # I/O Latency
        if config.get('io_latency', True) and 'controller_avg_io_latency_usecs' in raw_stats:
            processed['avg_io_latency_ms'] = round(raw_stats['controller_avg_io_latency_usecs'] / 1000, 2)
        
        # Read Latency
        if config.get('read_latency', True) and 'controller_avg_read_io_latency_usecs' in raw_stats:
            processed['avg_read_latency_ms'] = round(raw_stats['controller_avg_read_io_latency_usecs'] / 1000, 2)
        
        # Write Latency
        if config.get('write_latency', True) and 'controller_avg_write_io_latency_usecs' in raw_stats:
            processed['avg_write_latency_ms'] = round(raw_stats['controller_avg_write_io_latency_usecs'] / 1000, 2)
        
        # I/O Bandwidth
        if config.get('io_bandwidth', True) and 'controller_io_bandwidth_kBps' in raw_stats:
            processed['io_bandwidth_mbps'] = round(raw_stats['controller_io_bandwidth_kBps'] / 1024, 2)
        
        # IOPS
        if config.get('iops', True) and 'controller_num_iops' in raw_stats:
            processed['iops'] = int(raw_stats['controller_num_iops'])
        
        return processed
    
    def _process_host_stats(self, raw_stats: Dict, config: Dict) -> Dict[str, Union[float, int]]:
        """Process and normalize host statistics"""
        processed = {}
        
        # CPU usage
        if config.get('cpu_usage', True) and 'hypervisor_cpu_usage_ppm' in raw_stats:
            processed['cpu_usage_percent'] = round(raw_stats['hypervisor_cpu_usage_ppm'] / 10000, 2)
        
        # Memory usage
        if config.get('memory_usage', True) and 'hypervisor_memory_usage_ppm' in raw_stats:
            processed['memory_usage_percent'] = round(raw_stats['hypervisor_memory_usage_ppm'] / 10000, 2)
        
        # I/O Latency
        if config.get('io_latency', True) and 'controller_avg_io_latency_usecs' in raw_stats:
            processed['avg_io_latency_ms'] = round(raw_stats['controller_avg_io_latency_usecs'] / 1000, 2)
        
        # I/O Bandwidth
        if config.get('io_bandwidth', True) and 'controller_io_bandwidth_kBps' in raw_stats:
            processed['io_bandwidth_mbps'] = round(raw_stats['controller_io_bandwidth_kBps'] / 1024, 2)
        
        # IOPS
        if config.get('iops', True) and 'controller_num_iops' in raw_stats:
            processed['iops'] = int(raw_stats['controller_num_iops'])
        
        # VM Count
        if config.get('vm_count', True) and 'hypervisor_num_vms' in raw_stats:
            processed['num_vms'] = int(raw_stats['hypervisor_num_vms'])
        
        return processed
    
    def _process_vm_stats(self, raw_stats: Dict, config: Dict) -> Dict[str, Union[float, int]]:
        """Process and normalize VM statistics"""
        processed = {}
        
        # CPU usage
        if config.get('cpu_usage', True) and 'hypervisor_cpu_usage_ppm' in raw_stats:
            processed['cpu_usage_percent'] = round(raw_stats['hypervisor_cpu_usage_ppm'] / 10000, 2)
        
        # Memory usage
        if config.get('memory_usage', True) and 'hypervisor_memory_usage_ppm' in raw_stats:
            processed['memory_usage_percent'] = round(raw_stats['hypervisor_memory_usage_ppm'] / 10000, 2)
        
        # Disk usage (if available)
        if config.get('disk_usage', True) and 'storage_usage_bytes' in raw_stats:
            processed['disk_usage_gb'] = round(raw_stats['storage_usage_bytes'] / (1024**3), 2)
        
        return processed
    
    def _is_cache_valid(self) -> bool:
        """Check if cached data is still valid"""
        if not self.performance_config.get('enable_metrics_cache', True):
            return False
        
        if not self.stats_cache or not self.last_update:
            return False
        
        age = (datetime.now() - self.last_update).total_seconds()
        return age < self.cache_timeout
    
    def _track_collection_performance(self, collection_time: float):
        """Track collection performance metrics"""
        self.collection_times.append(collection_time)
        
        # Keep only recent collection times
        if len(self.collection_times) > self.max_collection_history:
            self.collection_times = self.collection_times[-self.max_collection_history:]
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics for the collector"""
        if not self.collection_times:
            return {}
        
        return {
            'avg_collection_time': round(sum(self.collection_times) / len(self.collection_times), 2),
            'min_collection_time': round(min(self.collection_times), 2),
            'max_collection_time': round(max(self.collection_times), 2),
            'collections_count': len(self.collection_times),
            'cache_enabled': self.performance_config.get('enable_metrics_cache', True),
            'cache_valid': self._is_cache_valid()
        }
    
    def _empty_stats(self) -> Dict[str, Any]:
        """Return empty stats structure"""
        return {
            'clusters': {},
            'hosts': {},
            'vms': {},
            'timestamp': datetime.now().isoformat(),
            'collection_time': 0,
            'metadata': {
                'collector_version': '1.0.0',
                'api_healthy': False,
                'cache_enabled': False
            }
        }
    
    def clear_cache(self):
        """Clear the metrics cache"""
        with self.cache_lock:
            self.stats_cache = {}
            self.last_update = None
        logger.debug("Metrics cache cleared")
