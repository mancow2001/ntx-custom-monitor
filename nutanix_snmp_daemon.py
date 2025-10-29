#!/usr/bin/env python3
"""
Nutanix SNMP Daemon - Main Module

This is the main daemon that orchestrates data collection and SNMP exposure.
"""

import asyncio
import signal
import sys
import time
import logging
import threading
import os
from datetime import datetime
from typing import Optional

from config_manager import ConfigManager
from nutanix_api import NutanixAPIClient, NutanixAPIError
from metrics_collector import MetricsCollector
from snmp_agent import SNMPAgent, SNMPAgentError

logger = logging.getLogger(__name__)

class HealthMonitor:
    """Monitors the health of daemon components"""
    
    def __init__(self, config: dict):
        self.config = config
        self.monitoring_config = config.get('monitoring', {})
        self.enabled = self.monitoring_config.get('enable_health_checks', True)
        self.check_interval = self.monitoring_config.get('health_check_interval', 300)
        
        self.last_check = None
        self.health_status = {
            'api_client': False,
            'metrics_collector': False,
            'snmp_agent': False,
            'overall': False
        }
        
    def check_health(self, api_client, collector, snmp_agent) -> dict:
        """Perform health checks on all components"""
        if not self.enabled:
            return {'enabled': False}
        
        health = {
            'timestamp': datetime.now().isoformat(),
            'enabled': True,
            'components': {}
        }
        
        # Check API client health
        try:
            api_healthy = api_client.health_check() if api_client else False
            health['components']['api_client'] = {
                'healthy': api_healthy,
                'consecutive_failures': getattr(api_client, 'consecutive_failures', 0),
                'last_successful_request': getattr(api_client, 'last_successful_request', None)
            }
        except Exception as e:
            health['components']['api_client'] = {
                'healthy': False,
                'error': str(e)
            }
        
        # Check metrics collector
        try:
            collector_stats = collector.get_performance_stats() if collector else {}
            health['components']['metrics_collector'] = {
                'healthy': bool(collector_stats),
                'stats': collector_stats
            }
        except Exception as e:
            health['components']['metrics_collector'] = {
                'healthy': False,
                'error': str(e)
            }
        
        # Check SNMP agent
        try:
            snmp_healthy = snmp_agent.is_running() if snmp_agent else False
            snmp_stats = snmp_agent.get_stats() if snmp_agent else {}
            health['components']['snmp_agent'] = {
                'healthy': snmp_healthy,
                'stats': snmp_stats
            }
        except Exception as e:
            health['components']['snmp_agent'] = {
                'healthy': False,
                'error': str(e)
            }
        
        # Overall health
        all_healthy = all(
            comp.get('healthy', False) 
            for comp in health['components'].values()
        )
        health['overall_healthy'] = all_healthy
        
        self.last_check = datetime.now()
        self.health_status = {
            comp_name: comp_data.get('healthy', False)
            for comp_name, comp_data in health['components'].items()
        }
        self.health_status['overall'] = all_healthy
        
        return health

class NutanixSNMPDaemon:
    """Main daemon class that orchestrates data collection and SNMP exposure"""
    
    def __init__(self, config_path: Optional[str] = None):
        # Load configuration
        self.config_manager = ConfigManager(config_path)
        self.config = self.config_manager.to_dict()
        
        # Setup logging
        self._setup_logging()
        
        # Initialize components
        self.api_client: Optional[NutanixAPIClient] = None
        self.collector: Optional[MetricsCollector] = None
        self.snmp_agent: Optional[SNMPAgent] = None
        self.health_monitor: Optional[HealthMonitor] = None
        
        # Runtime state
        self.running = False
        self.collection_thread: Optional[threading.Thread] = None
        self.snmp_thread: Optional[threading.Thread] = None
        self.health_thread: Optional[threading.Thread] = None
        
        # Statistics
        self.start_time = None
        self.collection_count = 0
        self.last_collection_time = None
        self.error_count = 0
        
        # Setup signal handlers
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGHUP, self._reload_config)
        
        logger.info("Nutanix SNMP Daemon initialized")
    
    def _setup_logging(self):
        """Setup logging configuration"""
        daemon_config = self.config.get('daemon', {})
        log_level = daemon_config.get('log_level', 'INFO').upper()
        log_file = daemon_config.get('log_file', '/var/log/nutanix_snmp_daemon.log')
        
        # Configure root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(getattr(logging, log_level, logging.INFO))
        
        # Clear existing handlers
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        
        # Create formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        # File handler
        try:
            file_handler = logging.FileHandler(log_file)
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)
        except Exception as e:
            print(f"Warning: Could not setup file logging: {e}")
        
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
        
        logger.info(f"Logging configured: level={log_level}, file={log_file}")
    
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        logger.info(f"Received signal {signum}, shutting down...")
        self.stop()
    
    def _reload_config(self, signum, frame):
        """Handle configuration reload signal (SIGHUP)"""
        logger.info("Received SIGHUP, reloading configuration...")
        try:
            self.config_manager.reload()
            self.config = self.config_manager.to_dict()
            self._setup_logging()
            logger.info("Configuration reloaded successfully")
        except Exception as e:
            logger.error(f"Failed to reload configuration: {e}")
    
    def _initialize_components(self):
        """Initialize all daemon components"""
        try:
            # Initialize API client
            nutanix_config = self.config.get('nutanix', {})
            self.api_client = NutanixAPIClient(nutanix_config)
            logger.info("Nutanix API client initialized")
            
            # Initialize metrics collector
            self.collector = MetricsCollector(self.api_client, self.config)
            logger.info("Metrics collector initialized")
            
            # Initialize SNMP agent
            self.snmp_agent = SNMPAgent(self.config)
            logger.info("SNMP agent initialized")
            
            # Initialize health monitor
            self.health_monitor = HealthMonitor(self.config)
            logger.info("Health monitor initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize components: {e}")
            raise
    
    def _collection_worker(self):
        """Background worker for collecting performance data"""
        daemon_config = self.config.get('daemon', {})
        collection_interval = daemon_config.get('collection_interval', 60)
        
        logger.info(f"Collection worker started (interval: {collection_interval}s)")
        
        while self.running:
            try:
                start_time = time.time()
                
                # Collect performance statistics
                logger.info("Starting metrics collection...")
                
                # Create new event loop for this thread
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                try:
                    stats = loop.run_until_complete(self.collector.collect_all_stats())
                    
                    # Update SNMP agent with new data
                    self.snmp_agent.update_performance_data(stats)
                    
                    # Update statistics
                    self.collection_count += 1
                    self.last_collection_time = datetime.now()
                    
                    collection_time = time.time() - start_time
                    logger.info(f"Metrics collection completed in {collection_time:.2f}s")
                    
                    # Log collection summary
                    cluster_count = len(stats.get('clusters', {}))
                    host_count = len(stats.get('hosts', {}))
                    vm_count = len(stats.get('vms', {}))
                    logger.info(f"Collected metrics: {cluster_count} clusters, {host_count} hosts, {vm_count} VMs")
                    
                finally:
                    loop.close()
                
                # Sleep for remaining interval time
                sleep_time = max(0, collection_interval - (time.time() - start_time))
                if sleep_time > 0:
                    time.sleep(sleep_time)
                
            except Exception as e:
                self.error_count += 1
                logger.error(f"Error in collection worker: {e}")
                # Wait before retrying
                time.sleep(min(30, collection_interval / 2))
        
        logger.info("Collection worker stopped")
    
    def _snmp_worker(self):
        """Background worker for SNMP agent"""
        logger.info("SNMP worker starting...")
        
        try:
            self.snmp_agent.start()
        except Exception as e:
            self.error_count += 1
            logger.error(f"SNMP worker error: {e}")
        finally:
            logger.info("SNMP worker stopped")
    
    def _health_worker(self):
        """Background worker for health monitoring"""
        if not self.health_monitor.enabled:
            logger.info("Health monitoring disabled")
            return
        
        logger.info(f"Health monitor started (interval: {self.health_monitor.check_interval}s)")
        
        while self.running:
            try:
                health = self.health_monitor.check_health(
                    self.api_client, self.collector, self.snmp_agent
                )
                
                if not health.get('overall_healthy', False):
                    logger.warning("System health check failed")
                    if self.config.get('monitoring', {}).get('alert_on_connection_failure', True):
                        self._handle_health_alert(health)
                else:
                    logger.debug("System health check passed")
                
                # Sleep until next check
                time.sleep(self.health_monitor.check_interval)
                
            except Exception as e:
                logger.error(f"Error in health worker: {e}")
                time.sleep(60)  # Wait before retrying
        
        logger.info("Health monitor stopped")
    
    def _handle_health_alert(self, health: dict):
        """Handle health check alerts"""
        # Log detailed health status
        for component, status in health.get('components', {}).items():
            if not status.get('healthy', False):
                error = status.get('error', 'Unknown error')
                logger.error(f"Component {component} is unhealthy: {error}")
        
        # Could implement additional alerting here (email, webhook, etc.)
    
    def start(self):
        """Start the daemon"""
        if self.running:
            logger.warning("Daemon is already running")
            return
        
        logger.info("Starting Nutanix SNMP Daemon...")
        self.start_time = datetime.now()
        
        try:
            # Initialize components
            self._initialize_components()
            
            # Test API connectivity
            if not self.api_client.health_check():
                logger.error("Initial API health check failed")
                if not self.config.get('debug', {}).get('test_mode', False):
                    raise RuntimeError("Cannot start daemon - API connection failed")
            
            # Set running flag
            self.running = True
            
            # Start worker threads
            self.collection_thread = threading.Thread(
                target=self._collection_worker, 
                daemon=True, 
                name="CollectionWorker"
            )
            self.collection_thread.start()
            
            self.snmp_thread = threading.Thread(
                target=self._snmp_worker, 
                daemon=True, 
                name="SNMPWorker"
            )
            self.snmp_thread.start()
            
            self.health_thread = threading.Thread(
                target=self._health_worker, 
                daemon=True, 
                name="HealthWorker"
            )
            self.health_thread.start()
            
            logger.info("Daemon started successfully")
            
            # Keep main thread alive
            try:
                while self.running:
                    time.sleep(1)
            except KeyboardInterrupt:
                logger.info("Received keyboard interrupt")
                self.stop()
                
        except Exception as e:
            logger.error(f"Failed to start daemon: {e}")
            self.stop()
            raise
    
    def stop(self):
        """Stop the daemon"""
        if not self.running:
            return
        
        logger.info("Stopping daemon...")
        self.running = False
        
        # Stop SNMP agent
        if self.snmp_agent:
            try:
                self.snmp_agent.stop()
            except Exception as e:
                logger.error(f"Error stopping SNMP agent: {e}")
        
        # Close API client
        if self.api_client:
            try:
                self.api_client.close()
            except Exception as e:
                logger.error(f"Error closing API client: {e}")
        
        # Wait for threads to finish
        for thread in [self.collection_thread, self.snmp_thread, self.health_thread]:
            if thread and thread.is_alive():
                thread.join(timeout=5)
        
        logger.info("Daemon stopped")
    
    def get_status(self) -> dict:
        """Get daemon status information"""
        uptime = None
        if self.start_time:
            uptime = (datetime.now() - self.start_time).total_seconds()
        
        status = {
            'running': self.running,
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'uptime_seconds': uptime,
            'collection_count': self.collection_count,
            'last_collection': self.last_collection_time.isoformat() if self.last_collection_time else None,
            'error_count': self.error_count,
            'components': {
                'api_client': bool(self.api_client),
                'collector': bool(self.collector),
                'snmp_agent': bool(self.snmp_agent),
                'health_monitor': bool(self.health_monitor)
            }
        }
        
        # Add health status if available
        if self.health_monitor:
            status['health'] = self.health_monitor.health_status
        
        return status

def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Nutanix SNMP Daemon')
    parser.add_argument('--config', '-c', help='Configuration file path')
    parser.add_argument('--test', '-t', action='store_true', help='Test mode (don\'t require API connection)')
    parser.add_argument('--create-config', help='Create default configuration file at specified path')
    parser.add_argument('--status', action='store_true', help='Show daemon status and exit')
    parser.add_argument('--version', action='store_true', help='Show version and exit')
    
    args = parser.parse_args()
    
    if args.version:
        print("Nutanix SNMP Daemon v1.0.0")
        sys.exit(0)
    
    if args.create_config:
        try:
            ConfigManager.create_default_config(args.create_config)
            sys.exit(0)
        except Exception as e:
            print(f"Error creating configuration: {e}")
            sys.exit(1)
    
    try:
        daemon = NutanixSNMPDaemon(args.config)
        
        if args.test:
            daemon.config['debug']['test_mode'] = True
        
        if args.status:
            status = daemon.get_status()
            print("Daemon Status:")
            for key, value in status.items():
                print(f"  {key}: {value}")
            sys.exit(0)
        
        daemon.start()
        
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Daemon failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
