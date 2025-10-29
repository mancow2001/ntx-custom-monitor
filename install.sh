#!/bin/bash

# Nutanix SNMP Daemon Installation Script

set -e

# Configuration
DAEMON_USER="nutanix-snmp"
DAEMON_GROUP="nutanix-snmp"
INSTALL_DIR="/opt/nutanix-snmp-daemon"
CONFIG_FILE="/etc/nutanix_snmp_daemon.conf"
SERVICE_FILE="/etc/systemd/system/nutanix-snmp-daemon.service"
LOG_FILE="/var/log/nutanix_snmp_daemon.log"

echo "Installing Nutanix SNMP Daemon..."

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo "This script must be run as root" 
   exit 1
fi

# Install system dependencies
echo "Installing system dependencies..."
apt-get update
apt-get install -y python3 python3-pip python3-venv git

# Create daemon user and group
echo "Creating daemon user and group..."
if ! getent group $DAEMON_GROUP > /dev/null 2>&1; then
    groupadd --system $DAEMON_GROUP
fi

if ! getent passwd $DAEMON_USER > /dev/null 2>&1; then
    useradd --system --gid $DAEMON_GROUP --home $INSTALL_DIR \
            --shell /bin/false --comment "Nutanix SNMP Daemon" $DAEMON_USER
fi

# Create installation directory
echo "Creating installation directory..."
mkdir -p $INSTALL_DIR
chown $DAEMON_USER:$DAEMON_GROUP $INSTALL_DIR

# Create virtual environment
echo "Creating Python virtual environment..."
sudo -u $DAEMON_USER python3 -m venv $INSTALL_DIR/venv

# Install Python dependencies
echo "Installing Python dependencies..."
sudo -u $DAEMON_USER $INSTALL_DIR/venv/bin/pip install --upgrade pip
sudo -u $DAEMON_USER $INSTALL_DIR/venv/bin/pip install -r requirements.txt

# Copy daemon files
echo "Installing daemon files..."
cp nutanix_snmp_daemon.py $INSTALL_DIR/
chown $DAEMON_USER:$DAEMON_GROUP $INSTALL_DIR/nutanix_snmp_daemon.py
chmod +x $INSTALL_DIR/nutanix_snmp_daemon.py

# Install configuration file
echo "Installing configuration file..."
if [ ! -f $CONFIG_FILE ]; then
    cp nutanix_snmp_daemon.conf $CONFIG_FILE
    chmod 640 $CONFIG_FILE
    chown root:$DAEMON_GROUP $CONFIG_FILE
    echo "Configuration file installed at $CONFIG_FILE"
    echo "Please edit this file with your Nutanix and SNMP settings before starting the service."
else
    echo "Configuration file already exists at $CONFIG_FILE"
fi

# Install systemd service
echo "Installing systemd service..."
cp nutanix-snmp-daemon.service $SERVICE_FILE
systemctl daemon-reload

# Create log file
echo "Setting up logging..."
touch $LOG_FILE
chown $DAEMON_USER:$DAEMON_GROUP $LOG_FILE
chmod 644 $LOG_FILE

# Setup logrotate
cat > /etc/logrotate.d/nutanix-snmp-daemon << EOF
$LOG_FILE {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    copytruncate
    su $DAEMON_USER $DAEMON_GROUP
}
EOF

# Set up Python path in the service
sed -i "s|ExecStart=/usr/bin/python3|ExecStart=$INSTALL_DIR/venv/bin/python3|g" $SERVICE_FILE
systemctl daemon-reload

echo "Installation completed successfully!"
echo ""
echo "Next steps:"
echo "1. Edit the configuration file: sudo nano $CONFIG_FILE"
echo "2. Enable the service: sudo systemctl enable nutanix-snmp-daemon"
echo "3. Start the service: sudo systemctl start nutanix-snmp-daemon"
echo "4. Check status: sudo systemctl status nutanix-snmp-daemon"
echo "5. View logs: sudo journalctl -u nutanix-snmp-daemon -f"
echo ""
echo "IMPORTANT: Make sure to:"
echo "- Configure your Nutanix Prism Central credentials in $CONFIG_FILE"
echo "- Set strong SNMP v3 authentication and privacy keys"
echo "- Configure your monitoring tool to use the SNMP v3 credentials"
echo "- Ensure firewall allows SNMP traffic on the configured port (default: 161)"
