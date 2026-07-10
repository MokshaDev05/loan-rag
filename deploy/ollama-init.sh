#!/usr/bin/env bash
# deploy/ollama-init.sh — EC2 user-data script.
# Runs as root on first boot. Installs Ollama, configures it to listen on all
# interfaces, and pulls the llama3.2 model.

set -euo pipefail

# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Override the default listen address (127.0.0.1:11434) so App Runner can reach
# the instance over the VPC. The systemd override takes effect on next start.
mkdir -p /etc/systemd/system/ollama.service.d
cat > /etc/systemd/system/ollama.service.d/override.conf <<'EOF'
[Service]
Environment="OLLAMA_HOST=0.0.0.0:11434"
EOF

systemctl daemon-reload
systemctl enable ollama
systemctl restart ollama

# Wait for Ollama to accept connections before pulling the model
for i in $(seq 1 24); do
  if curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
    break
  fi
  sleep 5
done

# Pull llama3.2 (~2 GB). This runs in the background after the instance starts,
# so the App Runner service may be up before the pull completes. The first
# /ask request will block until the model is ready.
ollama pull llama3.2

echo "Ollama ready with llama3.2" >> /var/log/ollama-init.log
