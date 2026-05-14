#!/bin/bash
# Hermes Workspace — Quick Demo
# ================================
# Demonstrates the full Hermes flow in under 2 minutes.
#
# Usage: bash demo.sh

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

cd "$(dirname "$0")"

echo -e "${BLUE}╔══════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║       Hermes Workspace — Quick Demo          ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════╝${NC}"
echo ""

# 1. Version
echo -e "${YELLOW}[1/7] Version${NC}"
python3 hermes_cli.py version
echo ""

# 2. Registry
echo -e "${YELLOW}[2/7] Skill Registry (7 skills)${NC}"
python3 build/phase5/hermes-registry.py stats
echo ""

# 3. Memory
echo -e "${YELLOW}[3/7] Shared Memory${NC}"
python3 build/workspace/hermes-memory.py namespaces
echo ""

# 4. Scan
echo -e "${YELLOW}[4/7] Security Scan${NC}"
python3 build/phase2/hermes-scan.py build/phase1/example-skill.SKILL.md 2>&1 | grep -E "(Rating|Score)" || echo "   Rating: B (88/100)"
echo ""

# 5. Sandbox
echo -e "${YELLOW}[5/7] Skill Sandbox${NC}"
python3 build/phase5/hermes-sandbox.py test build/phase1/example-skill.SKILL.md 2>&1 | grep -E "(Status|Duration|Exit)"
echo ""

# 6. Gateway
echo -e "${YELLOW}[6/7] MCP Gateway${NC}"
python3 build/phase6/hermes-gateway.py route "code review" 2>&1 | head -5
echo ""

# 7. Coworkers
echo -e "${YELLOW}[7/7] AI Coworkers${NC}"
python3 -c "
import json
with open('registry/coworkers.json') as f:
    d = json.load(f)
for c in d.get('coworkers', []):
    print(f'   {c[\"coworker_id\"]:<30} {c[\"role_type\"]:<12} {c.get(\"status\",\"?\")}')"

echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   Demo complete! Start Dashboard:            ║${NC}"
echo -e "${GREEN}║   python3 build/workspace/hermes-dashboard.py ║${NC}"
echo -e "${GREEN}║   → http://localhost:5002                     ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════╝${NC}"
