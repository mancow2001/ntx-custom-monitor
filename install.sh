#!/bin/bash

# Nutanix SNMP Daemon Installation Script (v4 SDK Version)

set -e

# Configuration
DAEMON_USER="nutanix-snmp"
DAEMON_GROUP="nutanix-snmp"
INSTALL_DIR="/opt/nutanix-snmp-daemon"
CONFIG_DIR="/etc/nutanix-snmp-daemon"
CONFIG_FILE="$CONFIG_DIR/config.yaml"
SERVICE_FILE="/etc/systemd/system/nutanix-snmp-daemon.service"
LOG_FILE="/var/log/nutanix_snmp_daemon.log"
LOGROTATE_FILE="/etc/logrotate.d/nutanix-snmp-daemon"

# Script info
SCRIPT_NAME=$(basename "$0")
VERSION="2.0.0-v4SDK"

# Function to display help
show_help() {
    cat << EOF
Nutanix SNMP Daemon Installer v$VERSION (v4 SDK)

Usage: $SCRIPT_NAME [OPTIONS]

OPTIONS:
    -h, --help              Show this help message
    -u, --uninstall         Uninstall the daemon
    --keep-config          Keep configuration files during uninstall
    --keep-data            Keep data and log files during uninstall
    --keep-all             Keep both configuration and data during uninstall
    --fix-dependencies     Fix Python dependency issues
    --install-v4-sdk       Install/upgrade v4 SDK packages only
    -v, --version          Show version information

EXAMPLES:
    $SCRIPT_NAME                    # Install the daemon with v4 SDK
    $SCRIPT_NAME -u                 # Uninstall completely
    $SCRIPT_NAME -u --keep-config   # Uninstall but keep configuration
    $SCRIPT_NAME -u --keep-all      # Uninstall but keep config and data
    $SCRIPT_NAME --fix-dependencies # Fix Python import issues
    $SCRIPT_NAME --install-v4-sdk   # Install/upgrade only v4 SDK packages

EOF
}

# Function to display version
show_version() {
    echo "Nutanix SNMP Daemon Installer v$VERSION (v4 SDK)"
    echo "Uses official Nutanix v4 Python SDK packages"
}

# Function to check if running as root
check_root() {
    if [[ $EUID -ne 0 ]]; then
       echo "Error: This script must be run as root"
       exit 1
    fi
}

# Function to stop and disable service
stop_service() {
    echo "Stopping and disabling service..."
    if systemctl is-active --quiet nutanix-snmp-daemon; then
        systemctl stop nutanix-snmp-daemon
        echo "✓ Service stopped"
    fi
    
    if systemctl is-enabled --quiet nutanix-snmp-daemon 2>/dev/null; then
        systemctl disable nutanix-snmp-daemon
        echo "✓ Service disabled"
    fi
}

# Function to remove user and group
remove_user() {
    echo "Removing daemon user and group..."
    
    if getent passwd $DAEMON_USER > /dev/null 2>&1; then
        userdel $DAEMON_USER
        echo "✓ User '$DAEMON_USER' removed"
    fi
    
    if getent group $DAEMON_GROUP > /dev/null 2>&1; then
        groupdel $DAEMON_GROUP
        echo "✓ Group '$DAEMON_GROUP' removed"
    fi
}

# Function to uninstall the daemon
uninstall_daemon() {
    local keep_config=false
    local keep_data=false
    
    # Parse uninstall options
    while [[ $# -gt 0 ]]; do
        case $1 in
            --keep-config)
                keep_config=true
                shift
                ;;
            --keep-data)
                keep_data=true
                shift
                ;;
            --keep-all)
                keep_config=true
                keep_data=true
                shift
                ;;
            *)
                shift
                ;;
        esac
    done
    
    echo "Uninstalling Nutanix SNMP Daemon (v4 SDK)..."
    echo "Keep config: $keep_config"
    echo "Keep data: $keep_data"
    echo ""
    
    # Stop and disable service
    stop_service
    
    # Remove systemd service file
    if [ -f "$SERVICE_FILE" ]; then
        rm -f "$SERVICE_FILE"
        systemctl daemon-reload
        echo "✓ Systemd service file removed"
    fi
    
    # Remove installation directory
    if [ -d "$INSTALL_DIR" ]; then
        rm -rf "$INSTALL_DIR"
        echo "✓ Installation directory removed: $INSTALL_DIR"
    fi
    
    # Remove configuration directory (if not keeping config)
    if [ "$keep_config" = false ] && [ -d "$CONFIG_DIR" ]; then
        rm -rf "$CONFIG_DIR"
        echo "✓ Configuration directory removed: $CONFIG_DIR"
    elif [ "$keep_config" = true ] && [ -d "$CONFIG_DIR" ]; then
        echo "✓ Configuration directory preserved: $CONFIG_DIR"
    fi
    
    # Remove log files and logrotate (if not keeping data)
    if [ "$keep_data" = false ]; then
        if [ -f "$LOG_FILE" ]; then
            rm -f "$LOG_FILE"
            echo "✓ Log file removed: $LOG_FILE"
        fi
        
        if [ -f "$LOGROTATE_FILE" ]; then
            rm -f "$LOGROTATE_FILE"
            echo "✓ Logrotate configuration removed"
        fi
        
        # Remove any compressed log files
        rm -f "${LOG_FILE}".*.gz 2>/dev/null || true
        
    elif [ "$keep_data" = true ]; then
        echo "✓ Log files preserved"
    fi
    
    # Remove user and group
    remove_user
    
    echo ""
    echo "✓ Nutanix SNMP Daemon (v4 SDK) uninstalled successfully!"
    
    if [ "$keep_config" = true ] || [ "$keep_data" = true ]; then
        echo ""
        echo "Preserved files:"
        [ "$keep_config" = true ] && [ -d "$CONFIG_DIR" ] && echo "  - Configuration: $CONFIG_DIR"
        [ "$keep_data" = true ] && [ -f "$LOG_FILE" ] && echo "  - Log files: $LOG_FILE*"
    fi
}

# Function to install system dependencies
install_dependencies() {
    echo "Installing system dependencies..."
    
    # Detect package manager
    if command -v apt-get &> /dev/null; then
        apt-get update
        apt-get install -y python3 python3-pip python3-venv python3-dev build-essential
    elif command -v yum &> /dev/null; then
        yum update -y
        yum install -y python3 python3-pip python3-venv python3-devel gcc
    elif command -v dnf &> /dev/null; then
        dnf update -y
        dnf install -y python3 python3-pip python3-venv python3-devel gcc
    else
        echo "Error: Unsupported package manager. Please install Python 3.7+ manually."
        exit 1
    fi
    
    echo "✓ System dependencies installed"
}

# Function to create daemon user and group
create_user() {
    echo "Creating daemon user and group..."
    
    if ! getent group $DAEMON_GROUP > /dev/null 2>&1; then
        groupadd --system $DAEMON_GROUP
        echo "✓ Group '$DAEMON_GROUP' created"
    else
        echo "✓ Group '$DAEMON_GROUP' already exists"
    fi

    if ! getent passwd $DAEMON_USER > /dev/null 2>&1; then
        useradd --system --gid $DAEMON_GROUP --home $INSTALL_DIR \
                --shell /bin/false --comment "Nutanix SNMP Daemon" $DAEMON_USER
        echo "✓ User '$DAEMON_USER' created"
    else
        echo "✓ User '$DAEMON_USER' already exists"
    fi
}

# Function to create directories
create_directories() {
    echo "Creating directories..."
    
    mkdir -p $INSTALL_DIR
    mkdir -p $CONFIG_DIR
    
    chown $DAEMON_USER:$DAEMON_GROUP $INSTALL_DIR
    chown root:$DAEMON_GROUP $CONFIG_DIR
    chmod 750 $CONFIG_DIR
    
    echo "✓ Directories created and configured"
}

# Function to install v4 SDK packages only
install_v4_sdk_packages() {
    echo "Installing/upgrading Nutanix v4 SDK packages..."
    
    # Check if virtual environment exists
    if [ ! -d "$INSTALL_DIR/venv" ]; then
        echo "Error: Virtual environment not found at $INSTALL_DIR/venv"
        echo "Please run the full installation first."
        exit 1
    fi
    
    # Upgrade pip first
    sudo -u $DAEMON_USER $INSTALL_DIR/venv/bin/pip install --upgrade pip
    
    # Install v4 SDK packages with specific order
    echo "Installing Core v4 SDK packages..."
    sudo -u $DAEMON_USER $INSTALL_DIR/venv/bin/pip install --upgrade "ntnx-clustermgmt-py-client>=4.0.1,<5.0.0"
    sudo -u $DAEMON_USER $INSTALL_DIR/venv/bin/pip install --upgrade "ntnx-vmm-py-client>=4.0.1,<5.0.0"
    sudo -u $DAEMON_USER $INSTALL_DIR/venv/bin/pip install --upgrade "ntnx-prism-py-client>=4.0.1,<5.0.0"
    
    echo "Installing Optional v4 SDK packages..."
    # These might fail if not available, so we use || true
    sudo -u $DAEMON_USER $INSTALL_DIR/venv/bin/pip install --upgrade "ntnx-networking-py-client>=4.0.1,<5.0.0" || echo "⚠ Networking SDK not available"
    sudo -u $DAEMON_USER $INSTALL_DIR/venv/bin/pip install --upgrade "ntnx-volumes-py-client>=4.0.1,<5.0.0" || echo "⚠ Volumes SDK not available"
    sudo -u $DAEMON_USER $INSTALL_DIR/venv/bin/pip install --upgrade "ntnx-opsmgmt-py-client>=4.0.1,<5.0.0" || echo "⚠ OpsMgmt SDK not available"
    
    # Test critical imports
    echo "Testing v4 SDK imports..."
    sudo -u $DAEMON_USER $INSTALL_DIR/venv/bin/python3 -c "
try:
    from ntnx_clustermgmt_py_client import Configuration, ApiClient
    from ntnx_clustermgmt_py_client.api.clusters_api import ClustersApi
    from ntnx_vmm_py_client import Configuration as VmmConfig
    from ntnx_vmm_py_client.api.vm_api import VmApi
    from ntnx_prism_py_client import Configuration as PrismConfig
    print('✓ All critical v4 SDK imports successful')
except ImportError as e:
    print(f'✗ v4 SDK import error: {e}')
    exit(1)
" || {
        echo "Error: Failed to import v4 SDK modules"
        echo "Please check the error messages above"
        exit 1
    }
    
    echo "✓ v4 SDK packages installed and tested successfully"
}

# Function to setup Python environment
setup_python_env() {
    echo "Setting up Python virtual environment..."
    
    # Create virtual environment
    sudo -u $DAEMON_USER python3 -m venv $INSTALL_DIR/venv
    
    # Upgrade pip
    sudo -u $DAEMON_USER $INSTALL_DIR/venv/bin/pip install --upgrade pip
    
    # Check if requirements.txt exists
    if [ ! -f "requirements_v4.txt" ]; then
        echo "Error: requirements_v4.txt not found in current directory"
        echo "Creating minimal requirements..."
        
        # Create minimal requirements for v4 SDK
        cat > requirements_v4.txt << EOF
# Nutanix SNMP Daemon Requirements (v4 SDK)
PyYAML>=6.0,<7.0.0
pysnmp>=6.0.0,<7.0.0
pyasn1>=0.4.6,<1.0.0
pyasn1-modules>=0.2.6,<1.0.0
pycryptodomex>=3.15.0,<4.0.0
ntnx-clustermgmt-py-client>=4.0.1,<5.0.0
ntnx-vmm-py-client>=4.0.1,<5.0.0
ntnx-prism-py-client>=4.0.1,<5.0.0
urllib3>=1.26.0,<3.0.0
EOF
    fi
    
    # Install Python dependencies
    echo "Installing Python dependencies from requirements_v4.txt..."
    
    # Install standard libraries first
    echo "Installing standard libraries..."
    sudo -u $DAEMON_USER $INSTALL_DIR/venv/bin/pip install "PyYAML>=6.0,<7.0.0"
    sudo -u $DAEMON_USER $INSTALL_DIR/venv/bin/pip install "urllib3>=1.26.0,<3.0.0"
    
    # Install ASN.1 libraries
    echo "Installing ASN.1 libraries..."
    sudo -u $DAEMON_USER $INSTALL_DIR/venv/bin/pip install "pyasn1>=0.4.6,<1.0.0"
    sudo -u $DAEMON_USER $INSTALL_DIR/venv/bin/pip install "pyasn1-modules>=0.2.6,<1.0.0"
    
    # Install cryptographic libraries
    echo "Installing cryptographic libraries..."
    sudo -u $DAEMON_USER $INSTALL_DIR/venv/bin/pip install "pycryptodomex>=3.15.0,<4.0.0"
    
    # Install SNMP libraries
    echo "Installing SNMP libraries..."
    sudo -u $DAEMON_USER $INSTALL_DIR/venv/bin/pip install "pysnmp>=6.0.0,<7.0.0"
    
    # Install v4 SDK packages
    install_v4_sdk_packages
    
    # Install any remaining dependencies
    echo "Installing remaining dependencies..."
    sudo -u $DAEMON_USER $INSTALL_DIR/venv/bin/pip install -r requirements_v4.txt
    
    echo "✓ Python environment configured successfully with v4 SDK"
}

# Function to install daemon files
install_daemon_files() {
    echo "Installing daemon files (v4 SDK version)..."
    
    # Required Python files for v4 SDK version
    local required_files=(
        "nutanix_snmp_daemon_v4.py"
        "config_manager.py"
        "nutanix_api_v4.py"
        "metrics_collector.py"
        "snmp_agent.py"
    )
    
    # Check if all required files exist
    for file in "${required_files[@]}"; do
        if [ ! -f "$file" ]; then
            echo "Error: Required file '$file' not found in current directory"
            echo "Please make sure you have the v4 SDK version of the files"
            exit 1
        fi
    done
    
    # Copy daemon files
    for file in "${required_files[@]}"; do
        cp "$file" $INSTALL_DIR/
        chown $DAEMON_USER:$DAEMON_GROUP $INSTALL_DIR/"$file"
        echo "✓ Installed $file"
    done
    
    # Make main daemon executable
    chmod +x $INSTALL_DIR/nutanix_snmp_daemon_v4.py
    
    # Copy test script if it exists
    if [ -f "test_v4_daemon.py" ]; then
        cp test_v4_daemon.py $INSTALL_DIR/
        chown $DAEMON_USER:$DAEMON_GROUP $INSTALL_DIR/test_v4_daemon.py
        chmod +x $INSTALL_DIR/test_v4_daemon.py
        echo "✓ Installed test_v4_daemon.py"
    fi
    
    echo "✓ Daemon files installed (v4 SDK version)"
}

# Function to install configuration
install_configuration() {
    echo "Installing configuration file..."
    
    if [ ! -f $CONFIG_FILE ]; then
        if [ -f "config_v4.yaml" ]; then
            cp config_v4.yaml $CONFIG_FILE
            chmod 640 $CONFIG_FILE
            chown root:$DAEMON_GROUP $CONFIG_FILE
            echo "✓ Configuration file installed at $CONFIG_FILE"
            echo "⚠  Please edit this file with your Nutanix and SNMP settings before starting the service."
        elif [ -f "config.yaml" ]; then
            cp config.yaml $CONFIG_FILE
            chmod 640 $CONFIG_FILE
            chown root:$DAEMON_GROUP $CONFIG_FILE
            echo "✓ Configuration file installed at $CONFIG_FILE"
            echo "⚠  Please edit this file with your settings and consider adding v4 SDK specific options."
        else
            echo "Warning: No configuration file found. Creating default configuration..."
            # Create default configuration using the daemon itself
            sudo -u $DAEMON_USER $INSTALL_DIR/venv/bin/python3 $INSTALL_DIR/nutanix_snmp_daemon_v4.py --create-config $CONFIG_FILE 2>/dev/null || {
                echo "Error: Could not create default configuration"
                exit 1
            }
            chmod 640 $CONFIG_FILE
            chown root:$DAEMON_GROUP $CONFIG_FILE
            echo "✓ Default configuration created at $CONFIG_FILE"
        fi
    else
        echo "✓ Configuration file already exists at $CONFIG_FILE"
    fi
}

# Function to create systemd service
create_systemd_service() {
    echo "Creating systemd service file..."
    
    cat > $SERVICE_FILE << EOF
[Unit]
Description=Nutanix SNMP Daemon (v4 SDK)
Documentation=https://github.com/your-repo/nutanix-snmp-daemon
After=network.target
Wants=network.target

[Service]
Type=simple
User=$DAEMON_USER
Group=$DAEMON_GROUP
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/venv/bin/python3 $INSTALL_DIR/nutanix_snmp_daemon_v4.py --config $CONFIG_FILE
ExecReload=/bin/kill -HUP \$MAINPID
KillMode=mixed
KillSignal=SIGTERM
TimeoutStopSec=30
Restart=always
RestartSec=10

# Security settings
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=/var/log /tmp $CONFIG_DIR
CapabilityBoundingSet=CAP_NET_BIND_SERVICE

# Environment
Environment=PYTHONPATH=$INSTALL_DIR
Environment=CONFIG_FILE=$CONFIG_FILE

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    echo "✓ Systemd service file created"
}

# Function to setup logging
setup_logging() {
    echo "Setting up logging..."
    
    # Create log file
    touch $LOG_FILE
    chown $DAEMON_USER:$DAEMON_GROUP $LOG_FILE
    chmod 644 $LOG_FILE
    
    # Setup logrotate
    cat > $LOGROTATE_FILE << EOF
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

    echo "✓ Logging configured"
}

# Function to install the daemon
install_daemon() {
    echo "Installing Nutanix SNMP Daemon (v4 SDK Version) v$VERSION..."
    echo ""
    
    check_root
    install_dependencies
    create_user
    create_directories
    setup_python_env
    install_daemon_files
    install_configuration
    create_systemd_service
    setup_logging
    
    echo ""
    echo "✓ Installation completed successfully!"
    echo ""
    echo "Next steps:"
    echo "1. Edit the configuration file: sudo nano $CONFIG_FILE"
    echo "2. Test the configuration: sudo -u $DAEMON_USER $INSTALL_DIR/venv/bin/python3 $INSTALL_DIR/test_v4_daemon.py $CONFIG_FILE"
    echo "3. Enable the service: sudo systemctl enable nutanix-snmp-daemon"
    echo "4. Start the service: sudo systemctl start nutanix-snmp-daemon"
    echo "5. Check status: sudo systemctl status nutanix-snmp-daemon"
    echo "6. View logs: sudo journalctl -u nutanix-snmp-daemon -f"
    echo ""
    echo "Configuration file location: $CONFIG_FILE"
    echo "Installation directory: $INSTALL_DIR"
    echo ""
    echo "IMPORTANT: Make sure to:"
    echo "- Configure your Nutanix Prism Central credentials in $CONFIG_FILE"
    echo "- Set strong SNMP v3 authentication and privacy keys"
    echo "- Register your own enterprise OID and update the base_oid setting"
    echo "- Configure your monitoring tool to use the SNMP v3 credentials"
    echo "- Ensure firewall allows SNMP traffic on the configured port (default: 161)"
    echo "- Verify your Prism Central supports v4 APIs (PC 2024.1+ recommended)"
    echo ""
    echo "v4 SDK Features:"
    echo "- Uses official Nutanix Python SDK packages"
    echo "- Improved error handling and retry mechanisms"
    echo "- Better performance and connection management"
    echo "- Enhanced statistics collection capabilities"
    echo ""
    echo "For CLI options, run: sudo -u $DAEMON_USER $INSTALL_DIR/venv/bin/python3 $INSTALL_DIR/nutanix_snmp_daemon_v4.py --help"
}

# Function to fix dependencies
fix_dependencies() {
    echo "Fixing Python dependencies (v4 SDK)..."
    
    check_root
    
    # Check if virtual environment exists
    if [ ! -d "$INSTALL_DIR/venv" ]; then
        echo "Error: Virtual environment not found at $INSTALL_DIR/venv"
        echo "Please run the full installation first."
        exit 1
    fi
    
    echo "Reinstalling Python dependencies in correct order..."
    
    # Remove and recreate virtual environment
    echo "Recreating virtual environment..."
    sudo -u $DAEMON_USER rm -rf $INSTALL_DIR/venv
    sudo -u $DAEMON_USER python3 -m venv $INSTALL_DIR/venv
    
    # Upgrade pip first
    sudo -u $DAEMON_USER $INSTALL_DIR/venv/bin/pip install --upgrade pip
    
    # Install dependencies in specific order
    install_v4_sdk_packages
    
    # Install other dependencies if requirements file exists
    if [ -f "requirements_v4.txt" ]; then
        echo "Installing remaining dependencies..."
        sudo -u $DAEMON_USER $INSTALL_DIR/venv/bin/pip install -r requirements_v4.txt
    fi
    
    # Test imports
    echo "Testing imports..."
    sudo -u $DAEMON_USER $INSTALL_DIR/venv/bin/python3 -c "
try:
    from ntnx_clustermgmt_py_client import Configuration, ApiClient
    from ntnx_vmm_py_client import Configuration as VmmConfig
    from ntnx_prism_py_client import Configuration as PrismConfig
    import yaml
    print('✓ All imports successful')
except ImportError as e:
    print(f'✗ Import error: {e}')
    exit(1)
"
    
    if [ $? -eq 0 ]; then
        echo "✓ Dependencies fixed successfully"
        echo ""
        echo "You can now restart the service:"
        echo "  sudo systemctl restart nutanix-snmp-daemon"
        echo "  sudo systemctl status nutanix-snmp-daemon"
    else
        echo "✗ There are still import issues"
        echo "You may need to check your system Python installation"
        exit 1
    fi
}

# Main script logic
main() {
    case "${1:-}" in
        -h|--help)
            show_help
            exit 0
            ;;
        -v|--version)
            show_version
            exit 0
            ;;
        -u|--uninstall)
            check_root
            shift
            uninstall_daemon "$@"
            exit 0
            ;;
        --fix-dependencies)
            fix_dependencies
            exit 0
            ;;
        --install-v4-sdk)
            check_root
            install_v4_sdk_packages
            exit 0
            ;;
        "")
            install_daemon
            ;;
        *)
            echo "Error: Unknown option '$1'"
            echo "Use '$SCRIPT_NAME --help' for usage information."
            exit 1
            ;;
    esac
}

# Run main function with all arguments
main "$@"
