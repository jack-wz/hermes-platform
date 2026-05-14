#!/usr/bin/env python3
"""
hermes-connector — Multi-Channel Bot Connector Framework
========================================================

Unified interface for sending/receiving messages across Feishu, Slack, Discord.
Abstract base with platform-specific implementations.

Architecture:
    Hermes Workspace → Connector → [Feishu | Slack | Discord | Webhook]
                                   ↓
                             Bot receives message
                                   ↓
                         Coworker Engine processes
                                   ↓
                             Response sent back

Usage:
    # Start connector server
    python3 build/phase5/hermes-connector.py serve --port 5004

    # Send message via CLI
    python3 build/phase5/hermes-connector.py send --platform slack --channel "#general" --text "Hello"

    # List configured platforms
    python3 build/phase5/hermes-connector.py platforms

Configuration: connector-config.json (auto-generated on first run)
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import subprocess
import sys
import textwrap
import time
import urllib.request
import urllib.error
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ============================================================================
# Paths
# ============================================================================
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
CONFIG_FILE = PROJECT_ROOT / "connector-config.json"


# ============================================================================
# Data Models
# ============================================================================
@dataclass
class Message:
    """Unified message model across all platforms."""
    platform: str
    channel: str
    text: str
    user: str = "unknown"
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    thread_id: Optional[str] = None
    attachments: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "platform": self.platform,
            "channel": self.channel,
            "text": self.text,
            "user": self.user,
            "timestamp": self.timestamp,
            "thread_id": self.thread_id,
            "attachments": self.attachments,
        }


# ============================================================================
# Abstract Connector
# ============================================================================
class BaseConnector(ABC):
    """Abstract base for platform connectors."""

    def __init__(self, config: dict):
        self.config = config

    @abstractmethod
    def send_message(self, channel: str, text: str, **kwargs) -> dict:
        """Send a message to a channel. Returns {"success": bool, ...}"""
        ...

    @abstractmethod
    def list_channels(self) -> list[dict]:
        """List available channels."""
        ...

    def verify_webhook(self, body: bytes, headers: dict) -> bool:
        """Verify incoming webhook authenticity."""
        return True  # Override per platform


# ============================================================================
# Feishu Connector
# ============================================================================
class FeishuConnector(BaseConnector):
    """Feishu (Lark) bot connector via webhook."""

    def send_message(self, channel: str, text: str, **kwargs) -> dict:
        webhook_url = self.config.get("webhook_url", "")
        if not webhook_url:
            return {"success": False, "error": "Feishu webhook URL not configured"}

        payload = {
            "msg_type": "text" if not kwargs.get("markdown") else "interactive",
            "content": {
                "text": text,
            } if not kwargs.get("markdown") else {
                "config": {"wide_screen_mode": True},
                "elements": [{"tag": "markdown", "content": text}],
                "header": {"title": {"tag": "plain_text", "content": "Hermes Workspace"}},
            },
        }

        try:
            req = urllib.request.Request(
                webhook_url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            resp = urllib.request.urlopen(req, timeout=10)
            result = json.loads(resp.read())
            return {"success": result.get("code") == 0, "platform": "feishu", "response": result}
        except Exception as e:
            return {"success": False, "error": str(e), "platform": "feishu"}

    def list_channels(self) -> list[dict]:
        return [
            {"id": self.config.get("chat_id", "unknown"), "name": "Feishu Home", "platform": "feishu"}
        ]


# ============================================================================
# Slack Connector
# ============================================================================
class SlackConnector(BaseConnector):
    """Slack bot connector via webhook or API token."""

    def send_message(self, channel: str, text: str, **kwargs) -> dict:
        token = self.config.get("bot_token", "")
        if token:
            # Use API
            try:
                req = urllib.request.Request(
                    "https://slack.com/api/chat.postMessage",
                    data=json.dumps({
                        "channel": channel,
                        "text": text,
                        "thread_ts": kwargs.get("thread_id"),
                    }).encode("utf-8"),
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {token}",
                    },
                )
                resp = urllib.request.urlopen(req, timeout=10)
                result = json.loads(resp.read())
                return {"success": result.get("ok", False), "platform": "slack"}
            except Exception as e:
                return {"success": False, "error": str(e), "platform": "slack"}

        # Fallback to webhook
        webhook_url = self.config.get("webhook_url", "")
        if not webhook_url:
            return {"success": False, "error": "Slack not configured (need token or webhook URL)"}

        try:
            req = urllib.request.Request(
                webhook_url,
                data=json.dumps({"text": text, "channel": channel}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=10)
            return {"success": True, "platform": "slack"}
        except Exception as e:
            return {"success": False, "error": str(e), "platform": "slack"}

    def list_channels(self) -> list[dict]:
        return [
            {"id": self.config.get("channel_id", "C0AGY8BNKB8"), "name": "Home", "platform": "slack"}
        ]


# ============================================================================
# Discord Connector
# ============================================================================
class DiscordConnector(BaseConnector):
    """Discord bot connector via webhook."""

    def send_message(self, channel: str, text: str, **kwargs) -> dict:
        webhook_url = self.config.get("webhook_url", "")
        if not webhook_url:
            return {"success": False, "error": "Discord webhook URL not configured"}

        # Split long messages
        chunks = [text[i:i+1900] for i in range(0, len(text), 1900)]
        for i, chunk in enumerate(chunks):
            try:
                req = urllib.request.Request(
                    webhook_url,
                    data=json.dumps({
                        "content": chunk,
                        **(dict(thread_name=kwargs["thread_name"]) if "thread_name" in kwargs else {}),
                    }).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                )
                urllib.request.urlopen(req, timeout=10)
                if i < len(chunks) - 1:
                    time.sleep(0.5)
            except Exception as e:
                return {"success": False, "error": str(e), "platform": "discord"}

        return {"success": True, "platform": "discord"}

    def list_channels(self) -> list[dict]:
        return [
            {"id": "bot-home", "name": "#bot-home", "platform": "discord"},
            {"id": "engineering", "name": "#engineering", "platform": "discord"},
        ]


# ============================================================================
# Connector Registry
# ============================================================================
CONNECTORS = {
    "feishu": FeishuConnector,
    "slack": SlackConnector,
    "discord": DiscordConnector,
}


def get_connector(platform: str) -> Optional[BaseConnector]:
    """Get a connector instance for the given platform."""
    config = load_config()
    platform_config = config.get("platforms", {}).get(platform, {})
    connector_class = CONNECTORS.get(platform)
    if not connector_class:
        return None
    return connector_class(platform_config)


# ============================================================================
# Configuration
# ============================================================================
DEFAULT_CONFIG = {
    "version": "1.0.0",
    "platforms": {
        "feishu": {
            "enabled": False,
            "webhook_url": "",
            "chat_id": "",
            "app_id": "",
            "app_secret": "",
        },
        "slack": {
            "enabled": False,
            "webhook_url": "",
            "bot_token": "",
            "channel_id": "",
        },
        "discord": {
            "enabled": False,
            "webhook_url": "",
            "channel_id": "",
        },
    },
    "global": {
        "default_platform": "feishu",
        "rate_limit_per_minute": 30,
        "retry_attempts": 3,
    },
}


def load_config() -> dict:
    if not CONFIG_FILE.exists():
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(json.dumps(DEFAULT_CONFIG, indent=2, ensure_ascii=False))
        return DEFAULT_CONFIG
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return DEFAULT_CONFIG


def save_config(config: dict) -> None:
    CONFIG_FILE.write_text(json.dumps(config, indent=2, ensure_ascii=False))


# ============================================================================
# CLI Commands
# ============================================================================
def cmd_send(args: argparse.Namespace) -> int:
    """Send a message to a platform."""
    connector = get_connector(args.platform)
    if not connector:
        print(f"ERROR: Unknown platform '{args.platform}'", file=sys.stderr)
        print(f"       Supported: {', '.join(CONNECTORS.keys())}", file=sys.stderr)
        return 1

    result = connector.send_message(args.channel, args.text, markdown=args.markdown)
    if result.get("success"):
        print(f"✅ Message sent to {args.platform}/{args.channel}")
    else:
        print(f"❌ Failed: {result.get('error', 'unknown')}")
        return 1
    return 0


def cmd_platforms(args: argparse.Namespace) -> int:
    """List configured platforms and their status."""
    config = load_config()
    print(f"\n{'='*60}")
    print(f"🔌 Hermes Connector — Platform Status")
    print(f"{'='*60}")
    for platform, cfg in config.get("platforms", {}).items():
        enabled = cfg.get("enabled", False)
        status = "🟢 enabled" if enabled else "⚫ disabled"
        webhook = "✓" if cfg.get("webhook_url") else "✗"
        print(f"  {platform:<10} {status:<15} webhook: {webhook}")
    print(f"{'='*60}\n")
    return 0


def cmd_configure(args: argparse.Namespace) -> int:
    """Configure a platform."""
    config = load_config()
    platform = args.platform
    if platform not in config["platforms"]:
        print(f"ERROR: Unknown platform '{platform}'", file=sys.stderr)
        return 1

    if args.webhook_url:
        config["platforms"][platform]["webhook_url"] = args.webhook_url
    if args.token:
        config["platforms"][platform]["bot_token"] = args.token
    if args.enable:
        config["platforms"][platform]["enabled"] = True
    if args.disable:
        config["platforms"][platform]["enabled"] = False

    save_config(config)
    print(f"✅ {platform} configuration updated")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    """Start connector webhook server."""
    try:
        from flask import Flask, jsonify, request
    except ImportError:
        print("ERROR: Flask required. pip install flask", file=sys.stderr)
        return 1

    app = Flask(__name__)
    port = args.port

    @app.route("/health")
    def health():
        return jsonify({"status": "healthy", "service": "Hermes Connector"})

    @app.route("/webhook/<platform>", methods=["POST"])
    def webhook(platform: str):
        connector = get_connector(platform)
        if not connector:
            return jsonify({"error": f"Unknown platform: {platform}"}), 404

        body = request.get_data()
        verified = connector.verify_webhook(body, dict(request.headers))
        if not verified:
            return jsonify({"error": "Signature verification failed"}), 403

        # Parse message based on platform
        msg = None
        if platform == "feishu":
            data = request.get_json(silent=True) or {}
            event = data.get("event", {})
            msg = Message(
                platform="feishu",
                channel=event.get("chat_id", "unknown"),
                text=event.get("text", ""),
                user=event.get("sender", {}).get("id", "unknown"),
            )
        elif platform == "slack":
            data = request.get_json(silent=True) or {}
            event = data.get("event", {})
            msg = Message(
                platform="slack",
                channel=event.get("channel", "unknown"),
                text=event.get("text", ""),
                user=event.get("user", "unknown"),
            )
        elif platform == "discord":
            data = request.get_json(silent=True) or {}
            msg = Message(
                platform="discord",
                channel=data.get("channel_id", "unknown"),
                text=data.get("content", ""),
                user=data.get("author", {}).get("username", "unknown"),
            )

        if msg:
            print(f"[{msg.platform}] {msg.user} in {msg.channel}: {msg.text[:100]}")
            return jsonify({"success": True, "message": msg.to_dict()})
        return jsonify({"success": True, "note": "No message parsed"})

    @app.route("/send", methods=["POST"])
    def send():
        data = request.get_json(silent=True) or {}
        platform = data.get("platform", "feishu")
        channel = data.get("channel", "")
        text = data.get("text", "")
        if not channel or not text:
            return jsonify({"error": "channel and text required"}), 400

        connector = get_connector(platform)
        if not connector:
            return jsonify({"error": f"Unknown platform: {platform}"}), 404

        result = connector.send_message(channel, text, markdown=data.get("markdown", False))
        return jsonify(result)

    print(f"🔌 Hermes Connector Server")
    print(f"   URL: http://localhost:{port}")
    print(f"   Webhooks: http://localhost:{port}/webhook/<platform>")
    print(f"   Send API: POST http://localhost:{port}/send")
    app.run(host="0.0.0.0", port=port, debug=False)
    return 0


# ============================================================================
# Main
# ============================================================================
def main() -> int:
    parser = argparse.ArgumentParser(
        description="Hermes Multi-Channel Connector",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Examples:
              hermes-connector.py platforms
              hermes-connector.py send --platform slack --channel "#general" --text "Hello"
              hermes-connector.py configure --platform feishu --webhook-url "https://..."
              hermes-connector.py serve --port 5004
        """),
    )
    sub = parser.add_subparsers(dest="command")

    p_send = sub.add_parser("send", help="Send message to a platform")
    p_send.add_argument("--platform", "-p", required=True, choices=list(CONNECTORS.keys()))
    p_send.add_argument("--channel", "-c", required=True)
    p_send.add_argument("--text", "-t", required=True)
    p_send.add_argument("--markdown", action="store_true")

    sub.add_parser("platforms", help="List configured platforms")

    p_cfg = sub.add_parser("configure", help="Configure a platform")
    p_cfg.add_argument("--platform", "-p", required=True, choices=list(CONNECTORS.keys()))
    p_cfg.add_argument("--webhook-url")
    p_cfg.add_argument("--token")
    p_cfg.add_argument("--enable", action="store_true")
    p_cfg.add_argument("--disable", action="store_true")

    p_serve = sub.add_parser("serve", help="Start connector webhook server")
    p_serve.add_argument("--port", type=int, default=5004)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return 1

    commands = {
        "send": cmd_send,
        "platforms": cmd_platforms,
        "configure": cmd_configure,
        "serve": cmd_serve,
    }
    return commands[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
