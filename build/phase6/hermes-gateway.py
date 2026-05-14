#!/usr/bin/env python3
"""
hermes-gateway — MCP Gateway for Multi-Model, Multi-Provider
=============================================================

Unified entry point for multiple AI models and providers.
Routes requests to the best model for each task based on cost, capability, and availability.

Architecture:
    Client → Gateway (port 5005) → [Claude | GPT | Gemini | Local]
                                       ↓
                              Hermes Tools (scan, audit, memory, coworker)

Usage:
    hermes-gateway serve                    Start gateway server
    hermes-gateway models                   List available models
    hermes-gateway route "code review"      Show which model handles a task type

Configuration: gateway-config.json (auto-generated on first run)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import textwrap
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
CONFIG_FILE = PROJECT_ROOT / "gateway-config.json"


# ============================================================================
# Data Models
# ============================================================================
@dataclass
class ModelConfig:
    """Configuration for a specific model."""
    id: str
    provider: str
    model_name: str
    capabilities: list[str] = field(default_factory=list)
    cost_per_1k_tokens: float = 0.0
    max_tokens: int = 8000
    enabled: bool = True
    priority: int = 0  # Higher = preferred for matching tasks


@dataclass
class RouteRequest:
    """A routing request."""
    task_type: str
    messages: list[dict]
    max_tokens: int = 8000
    budget_limit: float = 0.0
    require_capabilities: list[str] = field(default_factory=list)


# ============================================================================
# Model Registry
# ============================================================================
DEFAULT_MODELS = [
    ModelConfig(
        id="claude-sonnet",
        provider="anthropic",
        model_name="claude-sonnet-4-20250514",
        capabilities=["reasoning", "code", "writing", "analysis", "long-context"],
        cost_per_1k_tokens=0.003,
        max_tokens=8000,
        priority=10,
    ),
    ModelConfig(
        id="claude-opus",
        provider="anthropic",
        model_name="claude-opus-4-20250514",
        capabilities=["reasoning", "code", "writing", "complex-analysis", "long-context"],
        cost_per_1k_tokens=0.015,
        max_tokens=8000,
        priority=8,
    ),
    ModelConfig(
        id="gpt-5.4",
        provider="openai",
        model_name="gpt-5.4",
        capabilities=["code", "reasoning", "data-analysis", "tool-use"],
        cost_per_1k_tokens=0.005,
        max_tokens=8000,
        priority=9,
    ),
    ModelConfig(
        id="gpt-5.4-mini",
        provider="openai",
        model_name="gpt-5.4-mini",
        capabilities=["fast", "classification", "summarization", "simple-tasks"],
        cost_per_1k_tokens=0.0005,
        max_tokens=4000,
        priority=6,
    ),
    ModelConfig(
        id="gemini-pro",
        provider="google",
        model_name="gemini-2.5-pro",
        capabilities=["multimodal", "reasoning", "code", "long-context"],
        cost_per_1k_tokens=0.0035,
        max_tokens=8000,
        priority=7,
    ),
    ModelConfig(
        id="deepseek-v4",
        provider="deepseek",
        model_name="deepseek-v4-pro",
        capabilities=["code", "reasoning", "cost-efficient"],
        cost_per_1k_tokens=0.001,
        max_tokens=8000,
        priority=5,
    ),
]

# Task-to-capability mapping
TASK_ROUTING = {
    "code review": {"prefer": ["code", "reasoning"], "budget": "mid"},
    "code generation": {"prefer": ["code"], "budget": "mid"},
    "writing": {"prefer": ["writing", "reasoning"], "budget": "low"},
    "analysis": {"prefer": ["analysis", "reasoning"], "budget": "high"},
    "summarization": {"prefer": ["summarization", "fast"], "budget": "low"},
    "data analysis": {"prefer": ["data-analysis", "reasoning"], "budget": "high"},
    "multimodal": {"prefer": ["multimodal"], "budget": "mid"},
    "simple task": {"prefer": ["fast", "simple-tasks"], "budget": "low"},
    "complex reasoning": {"prefer": ["complex-analysis", "reasoning"], "budget": "high"},
    "chat": {"prefer": ["reasoning", "writing"], "budget": "low"},
}


# ============================================================================
# Configuration
# ============================================================================
def load_config() -> dict:
    if not CONFIG_FILE.exists():
        default = {
            "version": "1.0.0",
            "models": [
                {
                    "id": m.id, "provider": m.provider, "model_name": m.model_name,
                    "capabilities": m.capabilities, "cost_per_1k_tokens": m.cost_per_1k_tokens,
                    "max_tokens": m.max_tokens, "enabled": m.enabled, "priority": m.priority,
                }
                for m in DEFAULT_MODELS
            ],
            "default_model": "claude-sonnet",
            "fallback_model": "gpt-5.4-mini",
            "rate_limit_per_minute": 30,
        }
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(default, indent=2, ensure_ascii=False))
        return default
    return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))


# ============================================================================
# Routing Engine
# ============================================================================
def route_request(task_type: str, config: dict) -> list[dict]:
    """Route a task to the best matching model(s)."""
    routing = TASK_ROUTING.get(task_type, TASK_ROUTING["chat"])
    preferred = routing["prefer"]

    models = [
        ModelConfig(**m) for m in config.get("models", [])
        if m.get("enabled", True)
    ]

    # Score each model by capability match
    scored = []
    for model in models:
        score = 0
        for cap in preferred:
            if cap in model.capabilities:
                score += 10
        # Bonus for shared capabilities
        overlap = len(set(model.capabilities) & set(preferred))
        score += overlap * 5
        # Priority bonus
        score += model.priority
        # Cost penalty for high-budget tasks
        if routing["budget"] == "low":
            score -= int(model.cost_per_1k_tokens * 1000)
        scored.append({
            "model_id": model.id,
            "provider": model.provider,
            "model_name": model.model_name,
            "score": score,
            "cost_per_1k": model.cost_per_1k_tokens,
            "capabilities": model.capabilities,
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:3]


# ============================================================================
# CLI
# ============================================================================
def cmd_models(args: argparse.Namespace) -> int:
    config = load_config()
    print(f"\n{'='*70}")
    print(f"🤖 Hermes MCP Gateway — Available Models")
    print(f"{'='*70}")
    for m in config.get("models", []):
        status = "🟢" if m.get("enabled") else "⚫"
        cost = f"${m['cost_per_1k_tokens']:.4f}/1k tokens"
        caps = ", ".join(m.get("capabilities", [])[:4])
        print(f"  {status} {m['id']:<18} {m['provider']:<10} {cost:<20} [{caps}]")
    print(f"{'='*70}\n")
    return 0


def cmd_route(args: argparse.Namespace) -> int:
    config = load_config()
    results = route_request(args.task_type, config)

    print(f"\n🧭 Routing: \"{args.task_type}\"")
    print(f"{'='*60}")
    for i, r in enumerate(results):
        marker = "👉" if i == 0 else "  "
        print(f"  {marker} {r['model_id']} ({r['provider']}) — score: {r['score']}")
        print(f"       Cost: ${r['cost_per_1k']:.4f}/1k | Caps: {', '.join(r['capabilities'][:4])}")
    print(f"{'='*60}\n")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    try:
        from flask import Flask, jsonify, request
    except ImportError:
        print("ERROR: Flask required. pip install flask", file=sys.stderr)
        return 1

    app = Flask(__name__)
    port = args.port
    config = load_config()

    @app.route("/health")
    def health():
        return jsonify({
            "status": "healthy",
            "service": "Hermes MCP Gateway",
            "models": len(config.get("models", [])),
            "version": config.get("version"),
        })

    @app.route("/models")
    def list_models():
        return jsonify({
            "success": True,
            "count": len(config.get("models", [])),
            "models": config.get("models", []),
        })

    @app.route("/route", methods=["POST"])
    def route():
        data = request.get_json(silent=True) or {}
        task_type = data.get("task_type", "chat")
        results = route_request(task_type, config)
        return jsonify({
            "success": True,
            "task_type": task_type,
            "recommendations": results,
            "routing_rules": TASK_ROUTING.get(task_type, TASK_ROUTING["chat"]),
        })

    @app.route("/tasks")
    def list_tasks():
        return jsonify({
            "success": True,
            "task_types": list(TASK_ROUTING.keys()),
            "routing_rules": TASK_ROUTING,
        })

    print(f"🤖 Hermes MCP Gateway")
    print(f"   URL: http://localhost:{port}")
    print(f"   Models: http://localhost:{port}/models")
    print(f"   Route: POST http://localhost:{port}/route")
    app.run(host="0.0.0.0", port=port, debug=False)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Hermes MCP Gateway — Multi-Model Routing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Examples:
              hermes-gateway models
              hermes-gateway route "code review"
              hermes-gateway route "data analysis"
              hermes-gateway serve --port 5005
        """),
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("models", help="List available models")

    p_route = sub.add_parser("route", help="Show model routing for a task")
    p_route.add_argument("task_type", help="Task type (code review, writing, analysis, etc.)")

    p_serve = sub.add_parser("serve", help="Start MCP Gateway server")
    p_serve.add_argument("--port", type=int, default=5005)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return 1

    commands = {"models": cmd_models, "route": cmd_route, "serve": cmd_serve}
    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
