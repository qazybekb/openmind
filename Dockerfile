FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

# Install Node.js + system deps
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl ca-certificates gnupg git && \
    mkdir -p /etc/apt/keyrings && \
    curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg && \
    echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_20.x nodistro main" > /etc/apt/sources.list.d/nodesource.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends nodejs && \
    apt-get purge -y gnupg && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

# Clone and install nanobot
WORKDIR /app
RUN git clone https://github.com/HKUDS/nanobot.git . && \
    uv pip install --system --no-cache .

# Build WhatsApp bridge
WORKDIR /app/bridge
RUN npm install && npm run build
WORKDIR /app

# Install tools: Playwright, Chromium, pymupdf, MCP servers
RUN npm install -g @playwright/mcp@latest && \
    npx -y playwright install chromium --with-deps && \
    pip install pymupdf

# Create directories
RUN mkdir -p /root/.nanobot/workspace

# Copy bot personality files
COPY workspace/SOUL.md /root/.nanobot/workspace/
COPY workspace/AGENTS.md /root/.nanobot/workspace/
COPY workspace/HEARTBEAT.md /root/.nanobot/workspace/
COPY workspace/read_pdf.py /root/.nanobot/workspace/

EXPOSE 18790

ENTRYPOINT ["nanobot"]
CMD ["gateway"]
