#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# Small-Merchant AI Readiness Agent — One-Command Initializer
# Razorpay AI Buildathon 2026 · Track 01
# ═══════════════════════════════════════════════════════════════════════════════

set -e
RESET='\033[0m'
BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'

echo ""
echo -e "${BOLD}════════════════════════════════════════════════════════════${RESET}"
echo -e "${BOLD}  Small-Merchant AI Readiness Agent — Setup${RESET}"
echo -e "${BOLD}  Razorpay AI Buildathon 2026 · Track 01${RESET}"
echo -e "${BOLD}════════════════════════════════════════════════════════════${RESET}"
echo ""

# ── Step 1: Prerequisites ──────────────────────────────────────────────────────
echo -e "${BLUE}[1/5] Checking prerequisites...${RESET}"

if ! command -v python3 &>/dev/null; then
    echo -e "${RED}✗ Python 3 not found. Install from https://python.org${RESET}"
    exit 1
fi
PYTHON_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo -e "${GREEN}  ✓ Python ${PYTHON_VER}${RESET}"

if ! command -v node &>/dev/null; then
    echo -e "${RED}✗ Node.js not found. Install from https://nodejs.org${RESET}"
    exit 1
fi
NODE_VER=$(node --version)
echo -e "${GREEN}  ✓ Node ${NODE_VER}${RESET}"

# ── Step 2: Backend setup ──────────────────────────────────────────────────────
echo ""
echo -e "${BLUE}[2/5] Setting up backend...${RESET}"

cd backend/

# Copy .env if it doesn't exist
if [ ! -f .env ]; then
    cp .env.example .env
    echo -e "${YELLOW}  ⚠ Created .env from template. Edit it to add your API keys.${RESET}"
    echo -e "${YELLOW}    (System works without keys using template fallback)${RESET}"
else
    echo -e "${GREEN}  ✓ .env already exists${RESET}"
fi

# Install Python deps
echo "  Installing Python dependencies..."
pip install -r requirements.txt -q --break-system-packages 2>/dev/null || pip install -r requirements.txt -q
echo -e "${GREEN}  ✓ Python dependencies installed${RESET}"

# Create data dirs
mkdir -p data/merchant_fixtures results
echo -e "${GREEN}  ✓ Data directories ready${RESET}"

# ── Step 3: Frontend setup ─────────────────────────────────────────────────────
echo ""
echo -e "${BLUE}[3/5] Setting up frontend...${RESET}"
cd ../frontend/
echo "  Installing Node dependencies..."
npm install --silent
echo -e "${GREEN}  ✓ Node dependencies installed${RESET}"

# ── Step 4: Verify ─────────────────────────────────────────────────────────────
echo ""
echo -e "${BLUE}[4/5] Verifying system...${RESET}"
cd ../backend/
python3 -c "
import sys
sys.path.insert(0, '.')
from src.models import MerchantCatalog, BuyerSession
from src.ai_provider import get_ai_provider, get_embedding_provider
from src.onboarding.parsers import parse_csv
print('  ✓ All core modules importable')
ai = get_ai_provider()
print(f'  ✓ AI provider: {ai.get_available_provider().value}')
emb = get_embedding_provider()
print(f'  ✓ Embedding provider: {emb.provider_name}')
"
echo -e "${GREEN}  ✓ System verified${RESET}"

# ── Step 5: Launch ─────────────────────────────────────────────────────────────
echo ""
echo -e "${BLUE}[5/5] Starting services...${RESET}"

# Check what's available for terminals
if command -v gnome-terminal &>/dev/null; then
    TERM_CMD="gnome-terminal --"
elif command -v xterm &>/dev/null; then
    TERM_CMD="xterm -e"
else
    TERM_CMD=""
fi

echo ""
echo -e "${BOLD}════════════════════════════════════════════════════════════${RESET}"
echo -e "${BOLD}  Ready! Start the services in two terminals:${RESET}"
echo ""
echo -e "${BOLD}  Terminal 1 (Backend):${RESET}"
echo -e "    cd backend/"
echo -e "    uvicorn api.main:app --reload --host 0.0.0.0 --port 8000"
echo ""
echo -e "${BOLD}  Terminal 2 (Frontend):${RESET}"
echo -e "    cd frontend/"
echo -e "    npm run dev"
echo ""
echo -e "${BOLD}  Then open: http://localhost:5173${RESET}"
echo ""
echo -e "${BOLD}  Run batch evaluation:${RESET}"
echo -e "    cd backend/"
echo -e "    python -m src.evaluator --scenario all"
echo ""
echo -e "${BOLD}  Test the API:${RESET}"
echo -e "    curl http://localhost:8000/health"
echo -e "${BOLD}════════════════════════════════════════════════════════════${RESET}"
echo ""

# Auto-start if in a capable environment
if [ -n "$TERM_CMD" ]; then
    echo -e "${YELLOW}  Auto-starting services...${RESET}"
    $TERM_CMD bash -c "cd $(pwd) && uvicorn api.main:app --reload --port 8000; exec bash" &
    sleep 2
    cd ../frontend/
    $TERM_CMD bash -c "cd $(pwd) && npm run dev; exec bash" &
    echo -e "${GREEN}  ✓ Services started in new terminals${RESET}"
else
    echo -e "${YELLOW}  To auto-start, run in your environment:${RESET}"
    echo "    bash start.sh"
fi

# Create a convenience start script
cat > ../start.sh << 'STARTSCRIPT'
#!/bin/bash
# Start both backend and frontend
echo "Starting backend on :8000 and frontend on :5173..."
cd backend/
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!
cd ../frontend/
npm run dev &
FRONTEND_PID=$!
echo "Backend PID: $BACKEND_PID | Frontend PID: $FRONTEND_PID"
echo "Press Ctrl+C to stop both"
wait
STARTSCRIPT
chmod +x ../start.sh

echo -e "${GREEN}  Created start.sh for convenience.${RESET}"
echo ""
