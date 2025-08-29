# Systemd Service Deployment Guide

This guide explains how to deploy the Invisible Watermark API as a systemd service.

## Prerequisites

- Linux system with systemd
- Python 3.11+ installed
- Required dependencies installed

## Installation Steps

### 1. Create System User

```bash
# Create a dedicated user for the service
sudo useradd -r -s /bin/false -d /opt/invisible-watermark-api watermark

# Create the application directory
sudo mkdir -p /opt/invisible-watermark-api
sudo chown watermark:watermark /opt/invisible-watermark-api
```

### 2. Deploy Application Files

```bash
# Copy application files to the deployment directory
sudo cp -r . /opt/invisible-watermark-api/
sudo chown -R watermark:watermark /opt/invisible-watermark-api

# Create storage directory with proper permissions
sudo mkdir -p /opt/invisible-watermark-api/storage/embeds
sudo chown -R watermark:watermark /opt/invisible-watermark-api/storage
```

### 3. Set Up Python Virtual Environment

```bash
# Switch to the application directory
cd /opt/invisible-watermark-api

# Create virtual environment as the watermark user
sudo -u watermark python3 -m venv .venv

# Upgrade pip and install build tools first (Python 3.12+ compatibility)
sudo -u watermark .venv/bin/pip install --upgrade pip setuptools wheel

# Install dependencies
sudo -u watermark .venv/bin/pip install -r requirements.txt
```

### 4. Configure Environment

```bash
# Create environment file
sudo -u watermark cp .env.example .env

# Edit environment variables as needed
sudo -u watermark nano .env
```

Example `.env` configuration:
```env
WATERMARK_ADAPTER=trustmark
WM_PASS_IMG=1
WM_PASS_WM=1
```

### 5. Install Systemd Service

```bash
# Copy service file to systemd directory
sudo cp invisible-watermark-api.service /etc/systemd/system/

# Reload systemd configuration
sudo systemctl daemon-reload

# Enable the service to start on boot
sudo systemctl enable invisible-watermark-api

# Start the service
sudo systemctl start invisible-watermark-api
```

### 6. Verify Installation

```bash
# Check service status
sudo systemctl status invisible-watermark-api

# View logs
sudo journalctl -u invisible-watermark-api -f

# Test API endpoint
curl http://localhost:8001/docs
```

## Service Management

### Basic Commands

```bash
# Start the service
sudo systemctl start invisible-watermark-api

# Stop the service
sudo systemctl stop invisible-watermark-api

# Restart the service
sudo systemctl restart invisible-watermark-api

# Reload configuration
sudo systemctl reload invisible-watermark-api

# Check status
sudo systemctl status invisible-watermark-api

# Enable/disable auto-start
sudo systemctl enable invisible-watermark-api
sudo systemctl disable invisible-watermark-api
```

### Monitoring

```bash
# View live logs
sudo journalctl -u invisible-watermark-api -f

# View recent logs
sudo journalctl -u invisible-watermark-api -n 100

# View logs since boot
sudo journalctl -u invisible-watermark-api -b
```

## Configuration Details

### Service Configuration

The systemd service file includes several important configurations:

**Security Features:**
- Runs as non-root user (`watermark`)
- Restricted file system access
- Private temporary directory
- Network restrictions
- System call filtering

**Resource Limits:**
- File descriptor limit: 65536
- Process limit: 4096
- Automatic restart on failure

**Environment Variables:**
- `WATERMARK_ADAPTER`: Watermarking library selection
- `WM_PASS_IMG` / `WM_PASS_WM`: Blind watermark passwords
- `PYTHONPATH`: Application path

### File Permissions

```bash
# Recommended permissions
chmod 755 /opt/invisible-watermark-api
chmod 644 /opt/invisible-watermark-api/*.py
chmod 600 /opt/invisible-watermark-api/.env
chmod 755 /opt/invisible-watermark-api/storage
chmod 755 /opt/invisible-watermark-api/storage/embeds
```

## Firewall Configuration

Ensure the service is only accessible internally:

```bash
# Using ufw (Ubuntu/Debian)
sudo ufw deny 8001
sudo ufw allow from 127.0.0.1 to any port 8001

# Using firewalld (CentOS/RHEL/Fedora)
sudo firewall-cmd --permanent --add-rich-rule='rule family="ipv4" source address="127.0.0.1" port port="8001" protocol="tcp" accept'
sudo firewall-cmd --reload

# Using iptables (manual configuration)
sudo iptables -A INPUT -p tcp --dport 8001 -s 127.0.0.1 -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 8001 -j DROP
```

## Log Rotation

Create a logrotate configuration:

```bash
sudo tee /etc/logrotate.d/invisible-watermark-api << 'EOF'
/var/log/journal/*/system@invisible-watermark-api.service*.journal {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    copytruncate
    create 644 root root
}
EOF
```

## Troubleshooting

### Common Issues

**Service fails to start:**
```bash
# Check detailed status
sudo systemctl status invisible-watermark-api -l

# Check logs for errors
sudo journalctl -u invisible-watermark-api --no-pager

# Verify file permissions
ls -la /opt/invisible-watermark-api/
```

**Permission errors:**
```bash
# Fix ownership
sudo chown -R watermark:watermark /opt/invisible-watermark-api

# Fix storage permissions
sudo chmod -R 755 /opt/invisible-watermark-api/storage
```

**Python/dependency errors:**
```bash
# For Python 3.12+ distutils issues, upgrade build tools first
sudo -u watermark /opt/invisible-watermark-api/.venv/bin/pip install --upgrade pip setuptools wheel

# Test virtual environment
sudo -u watermark /opt/invisible-watermark-api/.venv/bin/python -c "import trustmark, blind_watermark"

# Reinstall dependencies
sudo -u watermark /opt/invisible-watermark-api/.venv/bin/pip install -r requirements.txt --force-reinstall
```

**Network connectivity:**
```bash
# Test local connectivity
curl -v http://localhost:8001/docs

# Check if port is bound
sudo netstat -tlnp | grep 8001

# Verify firewall rules
sudo ufw status verbose
```

### Service Health Check

Create a health check script:

```bash
sudo tee /opt/invisible-watermark-api/healthcheck.sh << 'EOF'
#!/bin/bash
response=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8001/docs)
if [ "$response" = "200" ]; then
    echo "Service is healthy"
    exit 0
else
    echo "Service is unhealthy (HTTP $response)"
    exit 1
fi
EOF

sudo chmod +x /opt/invisible-watermark-api/healthcheck.sh
```

## Updates and Maintenance

### Updating the Application

```bash
# Stop the service
sudo systemctl stop invisible-watermark-api

# Backup current version
sudo cp -r /opt/invisible-watermark-api /opt/invisible-watermark-api.backup

# Deploy new version
sudo cp -r /path/to/new/version/* /opt/invisible-watermark-api/
sudo chown -R watermark:watermark /opt/invisible-watermark-api

# Update dependencies if needed (Python 3.12+ compatibility)
sudo -u watermark /opt/invisible-watermark-api/.venv/bin/pip install --upgrade pip setuptools wheel
sudo -u watermark /opt/invisible-watermark-api/.venv/bin/pip install -r requirements.txt

# Restart service
sudo systemctl start invisible-watermark-api

# Verify update
sudo systemctl status invisible-watermark-api
```

### Backup Strategy

```bash
# Create backup script
sudo tee /opt/backup-watermark-api.sh << 'EOF'
#!/bin/bash
BACKUP_DIR="/opt/backups"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR
tar -czf $BACKUP_DIR/invisible-watermark-api_$DATE.tar.gz \
    -C /opt invisible-watermark-api \
    --exclude='invisible-watermark-api/.venv' \
    --exclude='invisible-watermark-api/storage/embeds'

# Keep only last 30 days of backups
find $BACKUP_DIR -name "invisible-watermark-api_*.tar.gz" -mtime +30 -delete
EOF

sudo chmod +x /opt/backup-watermark-api.sh

# Add to cron for daily backups
echo "0 2 * * * /opt/backup-watermark-api.sh" | sudo crontab -
```

## Production Considerations

1. **Monitoring**: Consider using monitoring tools like Prometheus, Grafana, or Nagios
2. **Load Balancing**: For high availability, run multiple instances behind a load balancer
3. **Database**: Consider using a persistent database instead of in-memory storage for production
4. **SSL/TLS**: If exposing through reverse proxy, ensure SSL termination
5. **Rate Limiting**: Implement rate limiting in your Node.js gateway
6. **Security Auditing**: Regular security updates and vulnerability scanning
7. **Performance Tuning**: Monitor memory usage and adjust resource limits as needed