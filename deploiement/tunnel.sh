#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Tunnel HTTPS temporaire — pour déclarer le webhook Meta aujourd'hui même,
# sans nom de domaine ni certificat.
#
#   ./deploiement/tunnel.sh            (port 8080 par défaut)
#   PORT=8080 ./deploiement/tunnel.sh
#
# cloudflared affiche une adresse du type https://xxxx.trycloudflare.com.
# Coller cette adresse suivie de /webhook/whatsapp dans Meta, puis dans
# « WhatsApp → Adresse publique du tableau de bord ».
#
# C'est un tunnel de test : il s'arrête avec le terminal. Pour la production,
# utiliser un nom de domaine et Caddy (voir deploiement/Caddyfile).
# ---------------------------------------------------------------------------
set -euo pipefail
PORT="${PORT:-8080}"

if ! command -v cloudflared >/dev/null 2>&1; then
  echo "cloudflared n'est pas installé." >&2
  echo "Sur Debian/Ubuntu :" >&2
  echo "  curl -L -o /tmp/cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb" >&2
  echo "  sudo dpkg -i /tmp/cloudflared.deb" >&2
  exit 1
fi

if ! curl -s -m 2 "http://127.0.0.1:${PORT}/sante" >/dev/null; then
  echo "Le serveur ne répond pas sur le port ${PORT}." >&2
  echo "Lancez d'abord : python3 run.py servir --port ${PORT}" >&2
  exit 1
fi

echo "Tunnel vers http://127.0.0.1:${PORT}"
echo "Adresse du webhook à déclarer dans Meta : <adresse affichée>/webhook/whatsapp"
echo ""
exec cloudflared tunnel --url "http://127.0.0.1:${PORT}"
