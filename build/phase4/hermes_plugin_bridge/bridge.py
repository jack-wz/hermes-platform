#!/usr/bin/env python3
"""
Hermes Plugin Bridge — 3-hook extension system for Hermes Platform.

Provides a pluggable middleware layer that wraps skill execution:
  - pre_execution:  validate / modify / reject before a skill runs
  - post_execution: augment / log / side-effect after a skill completes
  - error:          alert / cleanup / retry on failure

Handlers are registered via code or a JSON config file.  Multiple handlers
per hook point are supported and run in registration order.  Pre-execution
rejection short-circuits the chain.

Usage (importable module):
    from hermes_plugin_bridge import PluginBridge

    bridge = PluginBridge()
    bridge.load_config("~/.hermes/plugins/config.json")
    bridge.register_pre_execution(my_validator)
    ...
    decision = bridge.pre_execution(skill_meta, input_params)
    augmented = bridge.post_execution(skill_meta, result, receipt)
    action    = bridge.error(skill_meta, error_info)

JSON config structure (plugins/config.json):
    {
      "pre_execution": [
        {"name": "my_validator", "handler": "mypackage.hooks:validate_input"}
      ],
      "post_execution": [...],
      "error": [...]
    }

Dependencies:  Python 3.8+, importlib (stdlib).
"""

from __future__ import annotations

import importlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional, Union

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logger = logging.getLogger("hermes.plugin_bridge")
logger.addHandler(logging.NullHandler())


# ---------------------------------------------------------------------------
# Hook result types (lightweight data-classes for clarity)
# ---------------------------------------------------------------------------

@dataclass
class PreExecutionDecision:
    """Returned by pre_execution handlers and aggregated by the bridge."""

    allow: bool = True
    reason: str = ""
    modified_params: dict = field(default_factory=dict)


@dataclass
class PostExecutionResult:
    """Returned by post_execution handlers and merged by the bridge."""

    augmented: dict = field(default_factory=dict)


@dataclass
class ErrorAction:
    """Returned by error handlers and resolved by the bridge."""

    action: str = "abort"  # retry | abort | ignore
    reason: str = ""


# ---------------------------------------------------------------------------
# Type aliases for handler signatures
# ---------------------------------------------------------------------------

# pre_execution handler:
#   (skill_metadata: dict, input_params: dict) -> PreExecutionDecision | dict
PreExecHandler = Callable[[dict, dict], Union[PreExecutionDecision, dict[str, Any]]]

# post_execution handler:
#   (skill_metadata: dict, execution_result: dict, audit_receipt: dict) -> PostExecutionResult | dict
PostExecHandler = Callable[[dict, dict, dict], Union[PostExecutionResult, dict[str, Any]]]

# error handler:
#   (skill_metadata: dict, error_info: dict) -> ErrorAction | dict
ErrorHandler = Callable[[dict, dict], Union[ErrorAction, dict[str, Any]]]


# ---------------------------------------------------------------------------
# Plugin Bridge
# ---------------------------------------------------------------------------

class PluginBridge:
    """Extension bridge with 3 hook points for Hermes skill execution.

    Hook points
    -----------
    - pre_execution  : runs before the skill's command is dispatched.
    - post_execution : runs after the skill completes (success or failure).
    - error          : runs when execution raises an unhandled error.

    Registration
    ------------
    Handlers are stored as ordered lists.  Use ``register_*`` methods to add
    handlers programmatically, or ``load_config(path)`` to load from a JSON
    config file (module-path strings are resolved via ``importlib``).

    Execution order
    ---------------
    Handlers fire in registration order.  Pre-execution short-circuits on
    the first handler that returns ``allow=False`` — subsequent handlers are
    skipped and the rejection is propagated.  Post-execution always runs all
    handlers.  Error hooks are chained: each handler sees the previous
    handler's action and may override it.
    """

    def __init__(self) -> None:
        self._pre: list[tuple[str, PreExecHandler]] = []
        self._post: list[tuple[str, PostExecHandler]] = []
        self._error: list[tuple[str, ErrorHandler]] = []

    # ---- Registration API --------------------------------------------------

    def register_pre_execution(
        self,
        handler: PreExecHandler,
        *,
        name: Optional[str] = None,
    ) -> None:
        """Register a pre-execution handler.

        Parameters
        ----------
        handler : callable(skill_metadata, input_params) -> dict | PreExecutionDecision
            Must return a dict with at least ``{"allow": True/False}``.
        name : str, optional
            Human-readable label (defaults to the callable's ``__name__``).
        """
        hname = name or getattr(handler, "__name__", "anonymous")
        if isinstance(handler, type):  # guard against passing an uninstantiated class
            raise TypeError(
                f"Expected a callable, got class {handler.__name__}. "
                f"Did you mean to pass an instance?"
            )
        self._pre.append((hname, handler))
        logger.debug("Registered pre_execution handler: %s", hname)

    def register_post_execution(
        self,
        handler: PostExecHandler,
        *,
        name: Optional[str] = None,
    ) -> None:
        """Register a post-execution handler.

        Parameters
        ----------
        handler : callable(skill_metadata, execution_result, audit_receipt)
                  -> dict | PostExecutionResult
        name : str, optional
        """
        hname = name or getattr(handler, "__name__", "anonymous")
        if isinstance(handler, type):
            raise TypeError(
                f"Expected a callable, got class {handler.__name__}. "
                f"Did you mean to pass an instance?"
            )
        self._post.append((hname, handler))
        logger.debug("Registered post_execution handler: %s", hname)

    def register_error(
        self,
        handler: ErrorHandler,
        *,
        name: Optional[str] = None,
    ) -> None:
        """Register an error handler.

        Parameters
        ----------
        handler : callable(skill_metadata, error_info) -> dict | ErrorAction
            Must return a dict with at least ``{"action": "retry|abort|ignore"}``.
        name : str, optional
        """
        hname = name or getattr(handler, "__name__", "anonymous")
        if isinstance(handler, type):
            raise TypeError(
                f"Expected a callable, got class {handler.__name__}. "
                f"Did you mean to pass an instance?"
            )
        self._error.append((hname, handler))
        logger.debug("Registered error handler: %s", hname)

    # ---- Hook execution ----------------------------------------------------

    def pre_execution(
        self,
        skill_metadata: dict,
        input_params: dict,
    ) -> PreExecutionDecision:
        """Run all pre-execution handlers in registration order.

        Parameters
        ----------
        skill_metadata : dict
            Parsed SKILL.md frontmatter (skill_id, version, permissions, …).
        input_params : dict
            Key-value pairs the caller intends to pass to the skill.

        Returns
        -------
        PreExecutionDecision
            ``allow=True`` if all handlers approve (or no handlers registered).
            The ``modified_params`` field contains param mutations merged from
            all handlers (last-writer-wins for conflicts).
        """
        decision = PreExecutionDecision(allow=True)
        merged_params: dict = dict(input_params)  # start with originals

        for name, handler in self._pre:
            try:
                raw = handler(skill_metadata, merged_params)  # allow mutation
            except Exception as exc:
                logger.exception(
                    "pre_execution handler '%s' raised an exception", name
                )
                # On handler crash: reject (fail-safe)
                decision.allow = False
                decision.reason = (
                    f"pre_execution handler '{name}' crashed: {exc}"
                )
                return decision

            # Normalise return value
            if isinstance(raw, PreExecutionDecision):
                result: PreExecutionDecision = raw
            elif isinstance(raw, dict):
                result = PreExecutionDecision(
                    allow=raw.get("allow", True),
                    reason=raw.get("reason", ""),
                    modified_params=raw.get("modified_params", {}),
                )
            else:
                logger.warning(
                    "pre_execution handler '%s' returned unexpected type %s — ignored",
                    name, type(raw).__name__,
                )
                continue

            # Merge modified params
            merged_params.update(result.modified_params)

            if not result.allow:
                decision.allow = False
                decision.reason = (
                    f"[{name}] {result.reason}" if result.reason
                    else f"[{name}] rejected (no reason given)"
                )
                decision.modified_params = merged_params
                logger.info(
                    "pre_execution short-circuited by handler '%s': %s",
                    name, decision.reason,
                )
                return decision  # SHORT-CIRCUIT

        # All handlers approved
        decision.modified_params = merged_params
        return decision

    def post_execution(
        self,
        skill_metadata: dict,
        execution_result: dict,
        audit_receipt: Optional[dict] = None,
    ) -> PostExecutionResult:
        """Run all post-execution handlers in registration order.

        All handlers fire regardless of earlier handler results.

        Parameters
        ----------
        skill_metadata : dict
        execution_result : dict
            Should contain at minimum ``{"status": "success|failure|error",
            "exit_code": int, "stdout": str, "stderr": str, "duration_ms": int}``.
        audit_receipt : dict, optional
            Audit receipt from hermes-audit (Phase 3).

        Returns
        -------
        PostExecutionResult
            Merged ``augmented`` dict from all handlers.
        """
        merged: dict = {}
        for name, handler in self._post:
            try:
                raw = handler(skill_metadata, execution_result, audit_receipt or {})
            except Exception:
                logger.exception(
                    "post_execution handler '%s' raised an exception", name
                )
                continue

            if isinstance(raw, PostExecutionResult):
                merged.update(raw.augmented)
            elif isinstance(raw, dict):
                merged.update(raw.get("augmented", {}))
        return PostExecutionResult(augmented=merged)

    def error(
        self,
        skill_metadata: dict,
        error_info: dict,
    ) -> ErrorAction:
        """Run error handlers in registration order.

        Each handler can inspect/override the previous handler's action.
        The final action is returned.

        Parameters
        ----------
        skill_metadata : dict
        error_info : dict
            Should contain at minimum ``{"error_type": str, "error_message": str,
            "traceback": str, "skill_id": str, "input_params": dict}``.

        Returns
        -------
        ErrorAction
            Resolved action after chaining all error handlers.
        """
        action = ErrorAction(action="abort")  # default if no handlers
        for name, handler in self._error:
            try:
                raw = handler(skill_metadata, error_info)
            except Exception:
                logger.exception(
                    "error handler '%s' raised an exception", name
                )
                continue

            if isinstance(raw, ErrorAction):
                action = raw
            elif isinstance(raw, dict):
                action = ErrorAction(
                    action=raw.get("action", "abort"),
                    reason=raw.get("reason", ""),
                )
            logger.info(
                "error handler '%s' resolved action=%s reason=%s",
                name, action.action, action.reason,
            )
            # Allow early-exit: if a handler says "ignore" we can stop
            if action.action == "ignore":
                break

        return action

    # ---- Config loading ----------------------------------------------------

    def load_config(self, config_path: Union[str, Path]) -> None:
        """Load handler registrations from a JSON config file.

        Each entry in the JSON is ``{"name": "…", "handler": "module.path:func"}``.
        The ``handler`` string is split on the last ``:`` — the left part is
        the module, the right part is the callable attribute name.

        Example config::

            {
              "pre_execution": [
                {"name": "rate_limit", "handler": "myplugins.guards:rate_limit_check"}
              ],
              "post_execution": [
                {"name": "log_to_db", "handler": "myplugins.sinks:log_execution"}
              ],
              "error": [
                {"name": "pagerduty", "handler": "myplugins.alerts:page_on_call"}
              ]
            }
        """
        config_path = Path(config_path).expanduser().resolve()

        if not config_path.exists():
            logger.warning("Plugin config file not found: %s", config_path)
            return

        with open(config_path, "r", encoding="utf-8") as fh:
            cfg = json.load(fh)

        if not isinstance(cfg, dict):
            raise ValueError(f"Config must be a JSON object, got {type(cfg).__name__}")

        for hook, entries in cfg.items():
            if hook not in ("pre_execution", "post_execution", "error"):
                logger.warning("Unknown hook section in config: '%s' — skipped", hook)
                continue
            if not isinstance(entries, list):
                logger.warning(
                    "Config section '%s' must be a list — skipped", hook
                )
                continue

            register = {
                "pre_execution": self.register_pre_execution,
                "post_execution": self.register_post_execution,
                "error": self.register_error,
            }[hook]

            for entry in entries:
                if not isinstance(entry, dict):
                    logger.warning("Entry in '%s' is not a dict — skipped", hook)
                    continue
                name = entry.get("name", "unnamed")
                handler_ref = entry.get("handler", "")
                if not handler_ref:
                    logger.warning(
                        "Entry '%s' in '%s' has no 'handler' — skipped", name, hook
                    )
                    continue

                callable_obj = self._resolve_handler(handler_ref, name)
                if callable_obj:
                    register(callable_obj, name=name)

    @staticmethod
    def _resolve_handler(
        handler_ref: str, name: str
    ) -> Optional[Callable[..., Any]]:
        """Resolve ``module.path:callable_name`` to a Python callable."""
        if ":" not in handler_ref:
            logger.error(
                "Handler '%s' has invalid format '%s' (expected 'module:callable')",
                name, handler_ref,
            )
            return None

        module_path, attr_name = handler_ref.rsplit(":", 1)
        try:
            mod = importlib.import_module(module_path)
        except ImportError:
            logger.exception(
                "Cannot import module '%s' for handler '%s'", module_path, name
            )
            return None

        obj = getattr(mod, attr_name, None)
        if obj is None:
            logger.error(
                "Module '%s' has no attribute '%s' (handler '%s')",
                module_path, attr_name, name,
            )
            return None
        if not callable(obj):
            logger.error(
                "Attribute '%s' in module '%s' is not callable (handler '%s')",
                attr_name, module_path, name,
            )
            return None
        return obj

    # ---- Introspection -----------------------------------------------------

    @property
    def registered_handlers(self) -> dict[str, list[str]]:
        """Return a summary of all registered handler names."""
        return {
            "pre_execution": [name for name, _ in self._pre],
            "post_execution": [name for name, _ in self._post],
            "error": [name for name, _ in self._error],
        }

    def clear(self) -> None:
        """Remove all registered handlers."""
        self._pre.clear()
        self._post.clear()
        self._error.clear()


# ---------------------------------------------------------------------------
# Built-in example handlers (demonstrate the contract)
# ---------------------------------------------------------------------------

def builtin_permission_check(
    skill_metadata: dict, input_params: dict
) -> dict:
    """Pre-execution: verify that the skill's permissions are not empty."""
    perms = skill_metadata.get("permissions", {})
    tools = perms.get("tools", []) if isinstance(perms, dict) else []
    if not tools:
        return {
            "allow": False,
            "reason": "Skill declares no tools — execution blocked by builtin_permission_check",
            "modified_params": {},
        }
    return {"allow": True, "reason": "ok", "modified_params": {}}


def builtin_cost_guard(
    skill_metadata: dict, input_params: dict
) -> dict:
    """Pre-execution: guard against CRITICAL-cost skills without explicit approval."""
    cost = skill_metadata.get("cost", {})
    risk = cost.get("api_cost_risk", "LOW") if isinstance(cost, dict) else "LOW"
    if str(risk).upper() == "CRITICAL":
        return {
            "allow": False,
            "reason": (
                "Skill api_cost_risk is CRITICAL — requires manual override. "
                "Set input_params['_allow_critical'] = true to bypass."
            ),
            "modified_params": {},
        }
    return {"allow": True, "reason": "ok", "modified_params": {}}


def builtin_log_execution(
    skill_metadata: dict,
    execution_result: dict,
    audit_receipt: dict,
) -> dict:
    """Post-execution: simple structured logger (stdout)."""
    import sys

    sid = skill_metadata.get("skill_id", "?")
    status = execution_result.get("status", "?")
    duration = execution_result.get("duration_ms", "?")
    print(
        f"[plugin-bridge] skill={sid} status={status} duration_ms={duration}",
        file=sys.stderr,
    )
    return {"augmented": {"logged": True}}


def builtin_alert_on_error(
    skill_metadata: dict, error_info: dict
) -> dict:
    """Error: log the error and recommend retry for transient errors."""
    import sys

    etype = error_info.get("error_type", "UnknownError")
    msg = error_info.get("error_message", "")
    print(
        f"[plugin-bridge:ALERT] skill={skill_metadata.get('skill_id','?')} "
        f"error={etype}: {msg}",
        file=sys.stderr,
    )

    # Heuristic: retry on timeout / network errors, abort otherwise
    transient_keywords = ("timeout", "network", "connection", "temporary", "429")
    lower_msg = msg.lower()
    if any(kw in lower_msg for kw in transient_keywords):
        return {"action": "retry", "reason": "Transient error detected — retrying"}
    return {"action": "abort", "reason": f"Non-transient error: {etype}"}


# ---------------------------------------------------------------------------
# Convenience: create a bridge pre-loaded with built-ins
# ---------------------------------------------------------------------------

def create_default_bridge() -> PluginBridge:
    """Return a PluginBridge pre-loaded with safe built-in handlers."""
    bridge = PluginBridge()
    bridge.register_pre_execution(builtin_permission_check, name="builtin.permission_check")
    bridge.register_pre_execution(builtin_cost_guard, name="builtin.cost_guard")
    bridge.register_post_execution(builtin_log_execution, name="builtin.log_execution")
    bridge.register_error(builtin_alert_on_error, name="builtin.alert_on_error")
    return bridge
