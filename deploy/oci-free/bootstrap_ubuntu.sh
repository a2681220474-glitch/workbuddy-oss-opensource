#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run as root: sudo bash deploy/oci-free/bootstrap_ubuntu.sh" >&2
  exit 1
fi

apt-get update
apt-get install -y ca-certificates curl git python3 ufw fail2ban docker.io

if ! docker compose version >/dev/null 2>&1; then
  ARCH="$(uname -m)"
  case "${ARCH}" in
    x86_64)
      COMPOSE_ARCH="x86_64"
      ;;
    aarch64|arm64)
      COMPOSE_ARCH="aarch64"
      ;;
    *)
      echo "Unsupported architecture for docker compose plugin: ${ARCH}" >&2
      exit 1
      ;;
  esac
  COMPOSE_TAG="$(curl -fsSL https://api.github.com/repos/docker/compose/releases/latest | python3 -c 'import json,sys; print(json.load(sys.stdin)["tag_name"])')"
  install -d /usr/local/lib/docker/cli-plugins
  curl -fsSL "https://github.com/docker/compose/releases/download/${COMPOSE_TAG}/docker-compose-linux-${COMPOSE_ARCH}" \
    -o /usr/local/lib/docker/cli-plugins/docker-compose
  chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
fi

systemctl enable --now docker
systemctl enable --now fail2ban

ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

cat >/etc/fail2ban/jail.d/workbuddy-ssh.conf <<'EOF'
[sshd]
enabled = true
maxretry = 5
findtime = 10m
bantime = 1h
EOF

systemctl restart fail2ban

if [[ -n "${SUDO_USER:-}" && "${SUDO_USER}" != "root" ]]; then
  usermod -aG docker "${SUDO_USER}"
fi

echo "Bootstrap complete."
echo "Open only 22/80/443 in OCI security list or network security group."
echo "Log out and back in if your user was added to the docker group."
