#!/usr/bin/env bash
# =============================================================================
# Maintenance Intelligence — VPS Setup Script
# Run this as root on your Hostinger VPS (72.62.231.202)
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/connectwithrbalaa-prog/maintenance-intelligence/claude/deploy-lovable-hostinger-0Uzgu/deploy/vps-setup.sh | bash
#   OR: bash deploy/vps-setup.sh
#
# Options (env vars):
#   DOMAIN=maintenance.example.com  — set your domain for SSL setup
#   SKIP_SSL=true                   — skip Let's Encrypt (IP-only mode)
# =============================================================================

set -euo pipefail

REPO_DIR="/opt/apps/maintenance-intelligence"
BRANCH="claude/deploy-lovable-hostinger-0Uzgu"
DOMAIN="${DOMAIN:-}"
SKIP_SSL="${SKIP_SSL:-false}"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# ── 1. System packages ───────────────────────────────────────────────────────
info "Updating system and installing dependencies..."
apt-get update -qq
apt-get install -y -qq \
    curl git nginx certbot python3-certbot-nginx \
    ufw

# ── 2. Docker ────────────────────────────────────────────────────────────────
if ! command -v docker &>/dev/null; then
    info "Installing Docker..."
    curl -fsSL https://get.docker.com | sh
else
    info "Docker already installed: $(docker --version)"
fi

if ! docker compose version &>/dev/null; then
    info "Installing Docker Compose plugin..."
    apt-get install -y -qq docker-compose-plugin
fi

# ── 3. Firewall ──────────────────────────────────────────────────────────────
info "Configuring firewall..."
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw --force enable

# ── 4. Clone / update repo ───────────────────────────────────────────────────
if [ -d "$REPO_DIR/.git" ]; then
    info "Updating existing repo..."
    git -C "$REPO_DIR" fetch origin "$BRANCH"
    git -C "$REPO_DIR" checkout "$BRANCH"
    git -C "$REPO_DIR" pull origin "$BRANCH"
else
    info "Cloning repository..."
    mkdir -p /opt/apps
    git clone \
        --branch "$BRANCH" \
        https://github.com/connectwithrbalaa-prog/maintenance-intelligence.git \
        "$REPO_DIR"
fi

# ── 5. .env file ─────────────────────────────────────────────────────────────
if [ ! -f "$REPO_DIR/.env" ]; then
    warn ".env not found — creating from template. EDIT IT before continuing!"
    cat > "$REPO_DIR/.env" <<'EOF'
# !! CHANGE ALL VALUES BEFORE STARTING !!
POSTGRES_DB=maintenance
POSTGRES_USER=postgres
POSTGRES_PASSWORD=CHANGE_THIS_STRONG_PASSWORD
POSTGRES_HOST=postgres
KAFKA_BOOTSTRAP_SERVERS=kafka:9092
MI_RUN_SUMMARY_DIR=outputs
MI_DEV_ALLOW_HEADERS=false
OPENAI_API_KEY=sk-REPLACE_ME
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=CHANGE_THIS_GRAFANA_PASSWORD
EOF
    echo ""
    warn "============================================================"
    warn "  Edit /opt/apps/maintenance-intelligence/.env now!"
    warn "  Then re-run this script or run: docker compose -f docker-compose.prod.yml up -d --build"
    warn "============================================================"
    exit 0
fi

# ── 6. Nginx config — always start HTTP-only, certbot adds SSL after ─────────
info "Configuring Nginx..."
rm -f /etc/nginx/sites-enabled/default

if [ -n "$DOMAIN" ] && [ "$SKIP_SSL" != "true" ]; then
    # HTTP-only first (no SSL directives) — certbot will upgrade this to HTTPS
    cat > /etc/nginx/sites-available/maintenance-intelligence <<NGINXEOF
server {
    listen 80;
    server_name $DOMAIN www.$DOMAIN;

    location /.well-known/acme-challenge/ {
        root /var/www/html;
    }

    set \$cors_origin "";
    if (\$http_origin ~* "^https://asset-wise-look\\.lovable\\.app\$") {
        set \$cors_origin \$http_origin;
    }

    location / {
        proxy_pass         http://127.0.0.1:8001;
        proxy_http_version 1.1;
        proxy_set_header   Host              \$host;
        proxy_set_header   X-Real-IP         \$remote_addr;
        proxy_set_header   X-Forwarded-For   \$proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto \$scheme;
        proxy_read_timeout 300s;
        proxy_connect_timeout 10s;
        client_max_body_size 20M;

        add_header Access-Control-Allow-Origin  "\$cors_origin" always;
        add_header Access-Control-Allow-Methods "GET, POST, PUT, PATCH, DELETE, OPTIONS" always;
        add_header Access-Control-Allow-Headers "Authorization, Content-Type, X-Dev-User" always;
        add_header Access-Control-Max-Age       3600 always;

        if (\$request_method = OPTIONS) {
            return 204;
        }
    }

    location /grafana/ {
        proxy_pass         http://127.0.0.1:3000/;
        proxy_http_version 1.1;
        proxy_set_header   Host              \$host;
        proxy_set_header   X-Real-IP         \$remote_addr;
        proxy_set_header   X-Forwarded-For   \$proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto \$scheme;
    }
}
NGINXEOF
else
    # IP-only mode
    cp "$REPO_DIR/deploy/nginx/maintenance-intelligence-ip-only.conf" \
        /etc/nginx/sites-available/maintenance-intelligence
fi

ln -sf \
    /etc/nginx/sites-available/maintenance-intelligence \
    /etc/nginx/sites-enabled/maintenance-intelligence

nginx -t
systemctl reload nginx
info "Nginx configured and reloaded (HTTP only)."

# ── 7. SSL (Let's Encrypt) — certbot modifies the nginx config above ─────────
if [ -n "$DOMAIN" ] && [ "$SKIP_SSL" != "true" ]; then
    info "Obtaining SSL certificate for $DOMAIN..."
    # certbot --nginx patches the existing HTTP config to add SSL + redirect
    certbot --nginx \
        --non-interactive \
        --agree-tos \
        --email "admin@$DOMAIN" \
        -d "$DOMAIN" \
        -d "www.$DOMAIN" \
        --redirect \
        && info "SSL certificate issued for $DOMAIN." \
        || warn "Certbot failed — ensure DNS A record for $DOMAIN points to $(curl -sf https://api.ipify.org 2>/dev/null || echo 'this server') before re-running."

    # Backup renewal cron
    (crontab -l 2>/dev/null; echo "0 3 * * * certbot renew --quiet --nginx") | sort -u | crontab -
fi

# ── 8. Launch Docker Compose ─────────────────────────────────────────────────
info "Building and starting all services..."
cd "$REPO_DIR"
docker compose -f docker-compose.prod.yml pull --ignore-pull-failures 2>/dev/null || true
docker compose -f docker-compose.prod.yml up -d --build

# ── 9. Systemd service for auto-start on reboot ──────────────────────────────
info "Creating systemd service..."
cat > /etc/systemd/system/maintenance-intelligence.service <<EOF
[Unit]
Description=Maintenance Intelligence Application
After=docker.service network-online.target
Requires=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=$REPO_DIR
ExecStart=/usr/bin/docker compose -f docker-compose.prod.yml up -d
ExecStop=/usr/bin/docker compose -f docker-compose.prod.yml down
TimeoutStartSec=300

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable maintenance-intelligence

# ── 10. Status ───────────────────────────────────────────────────────────────
info "Waiting 20s for containers to initialize..."
sleep 20

echo ""
info "=== Container status ==="
docker compose -f "$REPO_DIR/docker-compose.prod.yml" ps

echo ""
info "=== Health check ==="
curl -sf http://127.0.0.1:8001/healthz && info "API is UP" || warn "API not ready yet — check logs: docker compose -f $REPO_DIR/docker-compose.prod.yml logs api"

echo ""
info "=== Done! ==="
if [ -n "$DOMAIN" ]; then
    info "App available at: https://$DOMAIN"
    info "Grafana at:       https://$DOMAIN/grafana"
else
    IP=$(curl -sf https://api.ipify.org 2>/dev/null || hostname -I | awk '{print $1}')
    info "App available at: http://$IP"
    info "Grafana at:       http://$IP/grafana"
fi
info "Logs: docker compose -f $REPO_DIR/docker-compose.prod.yml logs -f api"
