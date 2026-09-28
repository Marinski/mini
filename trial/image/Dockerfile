# Isolated runner for the agent trial: the agent sees only /work (its scratch repo copy).
FROM node:24-bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv git ca-certificates procps \
 && rm -rf /var/lib/apt/lists/*
COPY requirements.txt /tmp/requirements.txt
RUN python3 -m venv /opt/venv && /opt/venv/bin/pip install --no-cache-dir claude-agent-sdk==0.2.160 pytest -r /tmp/requirements.txt
RUN npm install -g opencode-ai@1.18.31 && npm cache clean --force
# uid 1000 = monster on the host, so files the agent writes in /work stay owned by monster
RUN userdel -r node 2>/dev/null; useradd -u 1000 -m -d /home/agent agent
ENV PATH=/opt/venv/bin:$PATH HOME=/home/agent
USER agent
WORKDIR /work
