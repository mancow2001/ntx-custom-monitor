# Nutanix SNMP Daemon

A Python daemon that collects performance statistics from Nutanix Prism Central and exposes them via SNMPv3 for monitoring tools like SolarWinds, ScienceLogic, Observium, and others.

## Features

- **Secure SNMPv3**: Authentication and privacy encryption support
- **Comprehensive Metrics**: Collects cluster and host performance statistics
- **Real-time Data**: Configurable collection intervals
- **Enterprise Ready**: Systemd service, logging, and monitoring
- **Easy Integration**: Works with popular network monitoring tools

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

2. Copy the daemon script to your preferred location:
   ```bash
   sudo cp nutanix_snmp_daemon.py /opt/nutanix-snmp-daemon/
   sudo chmod +x /opt/nutanix-snmp-daemon/nutanix_snmp_daemon.py
   ```

3. Copy and configure the configuration file:
   ```bash
   sudo cp nutanix_snmp_daemon.conf /etc/
   sudo nano /etc/nutanix_snmp_daemon.conf
   ```

4. Install the systemd service:
   ```bash
   sudo cp nutanix-snmp-daemon.service /etc/systemd/system/
   sudo systemctl daemon-reload
   ```

## Configuration

Edit `/etc/nutanix_snmp_daemon.conf`:

```ini
[nutanix]
prism_central_ip = 192.168.1.100
username = your_username
password = your_password
port = 9440

[snmp]
bind_ip = 0.0.0.0
bind_port = 161
username = snmp_username
auth_key = your_auth_key_here
priv_key = your_privacy_key_here

[daemon]
collection_interval = 60
log_level = INFO
```

### Configuration Parameters

#### Nutanix Section
- `prism_central_ip`: IP address of your Nutanix Prism Central
- `username`: Prism Central username with read access
- `password`: Prism Central password
- `port`: Prism Central port (default: 9440)

#### SNMP Section
- `bind_ip`: IP address to bind SNMP agent (0.0.0.0 for all interfaces)
- `bind_port`: SNMP port (default: 161, requires root for ports < 1024)
- `username`: SNMPv3 username
- `auth_key`: SNMPv3 authentication key (minimum 8 characters)
- `priv_key`: SNMPv3 privacy/encryption key (minimum 8 characters)

#### Daemon Section
- `collection_interval`: How often to collect metrics (seconds)
- `log_level`: Logging level (DEBUG, INFO, WARNING, ERROR)

## Running the Daemon

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

### Manual Execution

```bash
python3 nutanix_snmp_daemon.py
```

## SNMP OID Structure

The daemon uses a custom OID tree structure (you should register your own Enterprise OID):

```
1.3.6.1.4.1.99999.1 (Base OID - replace with your registered OID)
├── 1.1 (Cluster metrics)
│   ├── 1.1.1.{cluster_index}.1 (CPU usage)
│   ├── 1.1.1.{cluster_index}.2 (Memory usage)
│   ├── 1.1.1.{cluster_index}.3 (Average I/O latency)
│   ├── 1.1.1.{cluster_index}.4 (I/O bandwidth)
│   └── 1.1.1.{cluster_index}.5 (IOPS)
└── 1.2 (Host metrics)
    ├── 1.2.1.{host_index}.1 (CPU usage)
    ├── 1.2.1.{host_index}.2 (Memory usage)
    ├── 1.2.1.{host_index}.3 (Average I/O latency)
    ├── 1.2.1.{host_index}.4 (I/O bandwidth)
    ├── 1.2.1.{host_index}.5 (IOPS)
    └── 1.2.1.{host_index}.6 (Number of VMs)
```

## Monitoring Tool Configuration

### SolarWinds Orion

1. Add the server as an SNMP node
2. Configure SNMPv3 credentials:
   - Username: (from your config)
   - Authentication: MD5
   - Authentication Key: (from your config)
   - Privacy: DES
   - Privacy Key: (from your config)
3. Import custom MIB or configure custom pollers for the OIDs

### ScienceLogic

1. Add device with SNMP discovery
2. Configure SNMPv3 credentials in device properties
3. Create custom dynamic applications for Nutanix metrics

### Observium

1. Add device: `./add_device.php <hostname> <community> v3`
2. Configure SNMPv3 authentication in device settings
3. Custom metrics will appear in device overview

### PRTG Network Monitor

1. Add device with SNMP v3 sensor
2. Configure authentication parameters
3. Use "SNMP Custom" sensors for specific OIDs

## Security Considerations

- Use strong authentication and privacy keys (minimum 8 characters)
- Restrict SNMP access using firewall rules
- Use a dedicated service account for Nutanix API access
- Regularly rotate SNMP credentials
- Monitor daemon logs for authentication failures

## Troubleshooting

### Common Issues

1. **Permission Denied (Port 161)**
   - Run daemon as root or use port > 1024
   - Solution: `sudo systemctl start nutanix-snmp-daemon`

2. **Nutanix API Connection Failed**
   - Check network connectivity to Prism Central
   - Verify credentials and SSL certificate settings
   - Check firewall rules

3. **SNMP Authentication Failures**
   - Verify SNMPv3 credentials match monitoring tool configuration
   - Check key lengths (minimum 8 characters)
   - Review daemon logs for specific error messages

4. **Missing Metrics**
   - Check Nutanix API permissions
   - Verify cluster/host UUIDs are valid
   - Review collection interval vs. monitoring tool polling

### Log Files

- Daemon logs: `/var/log/nutanix_snmp_daemon.log`
- System logs: `journalctl -u nutanix-snmp-daemon`

### Debug Mode

Enable debug logging in configuration:
```ini
[daemon]
log_level = DEBUG
```

## API Rate Limiting

The daemon respects Nutanix API rate limits:
- Default collection interval: 60 seconds
- Concurrent API calls are limited
- Automatic retry with exponential backoff

## Performance Impact

- Minimal CPU usage (~1-2% during collection)
- Low memory footprint (~50-100MB)
- Network traffic: ~1-5MB per collection cycle
- Nutanix API load: Minimal impact on cluster performance

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For issues and questions:
1. Check the troubleshooting section
2. Review daemon logs
3. Submit an issue with log excerpts and configuration (redacted)

## Version History

- v1.0.0 - Initial release with basic cluster and host metrics
- Future: VM-level metrics, custom MIB files, additional monitoring integrations
