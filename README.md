# Nutanix SNMP Daemon (Modular Version)

A modular Python daemon that collects performance statistics from Nutanix Prism Central and exposes them via SNMPv3 for monitoring tools like SolarWinds, ScienceLogic, Observium, and others.

## 🆕 What's New in the Modular Version

- **YAML Configuration**: Modern YAML-based configuration instead of INI files
- **Modular Architecture**: Split into separate modules for easier maintenance
- **Enhanced Features**: Health monitoring, better error handling, performance optimization
- **Advanced Configuration**: Comprehensive settings for fine-tuning behavior
- **Better CLI**: Command-line options for testing, status checking, and configuration management

## Features

- **Secure SNMPv3**: Authentication and privacy encryption support
- **Comprehensive Metrics**: Collects cluster, host, and VM performance statistics
- **Real-time Data**: Configurable collection intervals with caching
- **Enterprise Ready**: Systemd service, health monitoring, and logging
- **Easy Integration**: Works with popular network monitoring tools
- **Modular Design**: Separate modules for API, metrics collection, and SNMP agent
- **Flexible Configuration**: YAML-based configuration with extensive options

## Architecture

The daemon is split into several modules:

- **`config_manager.py`**: Configuration loading and validation
- **`nutanix_api.py`**: Nutanix Prism Central API client
- **`metrics_collector.py`**: Performance metrics collection and processing
- **`snmp_agent.py`**: SNMPv3 agent implementation
- **`nutanix_snmp_daemon.py`**: Main daemon orchestrator

## Collected Metrics

### Cluster Metrics
- CPU usage percentage
- Memory usage percentage
- Average I/O latency (read/write/total)
- I/O bandwidth (Mbps)
- IOPS (Input/Output Operations Per Second)

### Host Metrics
- CPU usage percentage
- Memory usage percentage
- Average I/O latency
- I/O bandwidth (Mbps)
- IOPS
- Number of VMs

### VM Metrics (Optional)
- CPU usage percentage
- Memory usage percentage
- Disk usage (GB)

## Requirements

- Python 3.7+
- Nutanix Prism Central with API access
- Network access to Prism Central (default port 9440)
- SNMP port access (default port 161)

## Installation

### Quick Install

1. Download all files to a directory
2. Make the install script executable:
   ```bash
   chmod +x install.sh
   ```
3. Run the installation script as root:
   ```bash
   sudo ./install.sh
   ```

### Manual Installation

1. Install Python dependencies:
   ```bash
   pip3 install -r requirements.txt
   ```

2. Copy all Python modules to your installation directory:
   ```bash
   sudo mkdir -p /opt/nutanix-snmp-daemon
   sudo cp *.py /opt/nutanix-snmp-daemon/
   sudo chmod +x /opt/nutanix-snmp-daemon/nutanix_snmp_daemon.py
   ```

3. Copy and configure the configuration file:
   ```bash
   sudo mkdir -p /etc/nutanix-snmp-daemon
   sudo cp config.yaml /etc/nutanix-snmp-daemon/
   sudo nano /etc/nutanix-snmp-daemon/config.yaml
   ```

## Configuration

The daemon uses a YAML configuration file with comprehensive options:

```yaml
# Nutanix Prism Central Configuration
nutanix:
  prism_central_ip: "10.1.1.100"
  username: "admin"
  password: "your_password"
  port: 9440
  ssl_verify: false
  timeout: 30

# SNMP Agent Configuration
snmp:
  bind_ip: "0.0.0.0"
  bind_port: 161
  username: "nutanix_monitor"
  auth_key: "YourAuthKey123!"
  priv_key: "YourPrivKey123!"
  auth_protocol: "MD5"  # MD5 or SHA
  priv_protocol: "DES"  # DES or AES
  base_oid: "1.3.6.1.4.1.99999.1"

# Daemon Configuration
daemon:
  collection_interval: 60
  log_level: "INFO"
  log_file: "/var/log/nutanix_snmp_daemon.log"

# Metrics Configuration
metrics:
  cluster:
    cpu_usage: true
    memory_usage: true
    io_latency: true
    io_bandwidth: true
    iops: true
  host:
    cpu_usage: true
    memory_usage: true
    io_latency: true
    io_bandwidth: true
    iops: true
    vm_count: true
  vm:
    enabled: false

# Performance Optimization
performance:
  max_concurrent_requests: 10
  cache_timeout: 30
  enable_metrics_cache: true

# Health Monitoring
monitoring:
  enable_health_checks: true
  health_check_interval: 300
  alert_on_connection_failure: true

# Security Settings
security:
  allowed_snmp_clients: []  # Empty = allow all
  # Example: ["192.168.1.0/24", "10.0.0.0/8"]
```

## Running the Daemon

### Command Line Options

```bash
# Show help
python3 nutanix_snmp_daemon.py --help

# Use custom configuration file
python3 nutanix_snmp_daemon.py --config /path/to/config.yaml

# Test mode (don't require API connection)
python3 nutanix_snmp_daemon.py --test

# Create default configuration
python3 nutanix_snmp_daemon.py --create-config /path/to/new-config.yaml

# Show daemon status
python3 nutanix_snmp_daemon.py --status

# Show version
python3 nutanix_snmp_daemon.py --version
```

### As a System Service

1. Enable the service:
   ```bash
   sudo systemctl enable nutanix-snmp-daemon
   ```

2. Start the service:
   ```bash
   sudo systemctl start nutanix-snmp-daemon
   ```

3. Check status:
   ```bash
   sudo systemctl status nutanix-snmp-daemon
   ```

4. View logs:
   ```bash
   sudo journalctl -u nutanix-snmp-daemon -f
   ```

5. Reload configuration (sends SIGHUP):
   ```bash
   sudo systemctl reload nutanix-snmp-daemon
   ```

## Testing

Use the included test script to validate your setup:

```bash
# Test with default configuration locations
python3 test_modular_daemon.py

# Test with specific configuration file
python3 test_modular_daemon.py /path/to/config.yaml
```

The test script will:
- Validate configuration loading
- Test Nutanix API connectivity
- Verify SNMP settings
- Check system permissions
- Test component initialization

## SNMP OID Structure

The daemon uses a hierarchical OID tree structure:

```
{base_oid} (Default: 1.3.6.1.4.1.99999.1)
├── 1.1.{index}.{metric} (Cluster metrics)
├── 2.1.{index}.{metric} (Host metrics)
└── 3.1.{index}.{metric} (VM metrics)
```

### Metric IDs
- **1**: CPU usage (percentage * 100)
- **2**: Memory usage (percentage * 100)
- **3**: I/O latency (milliseconds * 100)
- **4**: I/O bandwidth (Mbps * 100)
- **5**: IOPS
- **6**: VM count (hosts only)

## Monitoring Tool Configuration

### SolarWinds Orion

1. Add device with SNMP v3
2. Configure credentials:
   - Security Level: authPriv
   - Username: (from config)
   - Auth Protocol: MD5/SHA
   - Auth Password: (auth_key from config)
   - Priv Protocol: DES/AES
   - Priv Password: (priv_key from config)
3. Create custom pollers for Nutanix OIDs

### ScienceLogic

1. Add device with SNMP discovery
2. Configure SNMPv3 credentials
3. Create dynamic applications for metrics

### PRTG Network Monitor

1. Add device with SNMP v3 sensor
2. Configure authentication
3. Use "SNMP Custom" sensors for specific OIDs

## Health Monitoring

The daemon includes comprehensive health monitoring:

- **API Health**: Connection status and response times
- **Collection Performance**: Metrics collection timing
- **SNMP Agent Status**: Agent availability and statistics
- **Component Health**: Individual module status

Health checks run periodically and can trigger alerts when issues are detected.

## Performance Optimization

Several features optimize performance:

- **Concurrent Collection**: Parallel API requests
- **Metrics Caching**: Configurable cache timeout
- **Connection Pooling**: Reuse HTTP connections
- **Request Limiting**: Prevent API overload

## Security Features

- **SNMPv3 Encryption**: Authentication and privacy
- **Client Access Control**: IP-based restrictions
- **Secure Configuration**: Protected config files
- **Minimal Privileges**: Runs as non-root user

## Troubleshooting

### Common Issues

1. **Configuration Errors**
   ```bash
   # Test configuration
   python3 test_modular_daemon.py /etc/nutanix-snmp-daemon/config.yaml
   ```

2. **API Connection Issues**
   ```bash
   # Check connectivity and credentials
   python3 nutanix_snmp_daemon.py --test --config /path/to/config.yaml
   ```

3. **SNMP Permission Issues**
   ```bash
   # For port 161, run as root or use higher port
   sudo systemctl start nutanix-snmp-daemon
   ```

4. **Debug Logging**
   ```yaml
   daemon:
     log_level: "DEBUG"
   ```

### Log Files

- Daemon logs: `/var/log/nutanix_snmp_daemon.log`
- System logs: `journalctl -u nutanix-snmp-daemon`

## Development

### Adding New Metrics

1. Modify `metrics_collector.py` to collect new data
2. Update `snmp_agent.py` to expose new OIDs
3. Add configuration options in `config.yaml`

### Custom Authentication

Extend `nutanix_api.py` to support additional authentication methods.

### Monitoring Integration

Add new monitoring tool configurations in the documentation.

## Migration from Legacy Version

To migrate from the single-file version:

1. Install the modular version
2. Convert INI config to YAML:
   ```bash
   python3 nutanix_snmp_daemon.py --create-config /etc/nutanix-snmp-daemon/config.yaml
   ```
3. Copy your settings from the old config
4. Test the new configuration
5. Update systemd service

## Contributing

1. Fork the repository
2. Create a feature branch
3. Follow the modular architecture
4. Add tests for new functionality
5. Submit a pull request

## License

This project is licensed under the MIT License.

## Support

For issues and questions:
1. Check the troubleshooting section
2. Run the test script
3. Review daemon logs
4. Submit an issue with configuration (redacted)

## Version History

- **v2.0.0** - Modular architecture, YAML configuration, enhanced features
- **v1.0.0** - Initial monolithic release

---

**Note**: Remember to register your own Enterprise OID and update the `base_oid` setting in your configuration.
