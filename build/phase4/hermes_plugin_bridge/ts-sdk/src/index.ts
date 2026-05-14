/**
 * Hermes Plugin Bridge — TypeScript SDK
 * ======================================
 *
 * Typed interfaces and utilities for building Hermes Workspace plugins.
 * Compatible with OpenClaw-Hawkins, SKILL.md, and the Hermes Plugin Bridge.
 *
 * Usage:
 *   import { Plugin, PluginManifest, registerPlugin } from '@hermes-workspace/plugin-sdk';
 */

// ============================================================================
// Core Types
// ============================================================================

/** Plugin manifest — what your plugin declares to the Hermes runtime */
export interface PluginManifest {
  /** Unique plugin identifier (e.g., "openclaw-hawkins") */
  id: string;
  /** Human-readable name */
  name: string;
  /** Semver version */
  version: string;
  /** Plugin author */
  author: string;
  /** Short description (max 200 chars) */
  description: string;
  /** License identifier */
  license: string;
  /** Tags for discovery */
  tags: string[];
  /** Minimum Hermes runtime version required */
  hermesVersion: string;
  /** Plugin category */
  category: "tool" | "connector" | "memory" | "skill" | "ui" | "governance";
}

/** Hook types supported by the Plugin Bridge */
export type HookType = "onStartup" | "onShutdown" | "onMessage" | "onSkillExecute" | "onMemoryWrite";

/** Hook handler signature */
export type HookHandler = (context: HookContext) => Promise<HookResult>;

/** Context passed to hook handlers */
export interface HookContext {
  /** Hook type that triggered this handler */
  hook: HookType;
  /** Plugin instance that owns this handler */
  plugin: Plugin;
  /** Event-specific payload */
  payload: Record<string, unknown>;
  /** Timestamp of the event */
  timestamp: string;
}

/** Result returned by hook handlers */
export interface HookResult {
  /** Whether the hook completed successfully */
  success: boolean;
  /** Optional data to pass to next handler in chain */
  data?: Record<string, unknown>;
  /** If false, stop processing further handlers for this hook */
  continue?: boolean;
  /** Error message if success is false */
  error?: string;
}

// ============================================================================
// Plugin Base Class
// ============================================================================

/** Base class for Hermes plugins */
export abstract class Plugin {
  public readonly manifest: PluginManifest;
  private hooks: Map<HookType, HookHandler[]> = new Map();

  constructor(manifest: PluginManifest) {
    this.manifest = manifest;
  }

  /** Register a hook handler */
  protected on(hook: HookType, handler: HookHandler): this {
    const handlers = this.hooks.get(hook) || [];
    handlers.push(handler);
    this.hooks.set(hook, handlers);
    return this;
  }

  /** Get all registered hooks */
  getHooks(): Map<HookType, HookHandler[]> {
    return this.hooks;
  }

  /** Initialize the plugin (called once at startup) */
  abstract initialize(): Promise<void>;

  /** Cleanup the plugin (called at shutdown) */
  abstract shutdown(): Promise<void>;
}

// ============================================================================
// Plugin Registry
// ============================================================================

/** Global plugin registry */
class PluginRegistry {
  private plugins: Map<string, Plugin> = new Map();

  /** Register a plugin */
  register(plugin: Plugin): void {
    if (this.plugins.has(plugin.manifest.id)) {
      throw new Error(`Plugin already registered: ${plugin.manifest.id}`);
    }
    this.plugins.set(plugin.manifest.id, plugin);
  }

  /** Get a registered plugin by ID */
  get(id: string): Plugin | undefined {
    return this.plugins.get(id);
  }

  /** List all registered plugins */
  list(): PluginManifest[] {
    return Array.from(this.plugins.values()).map(p => p.manifest);
  }

  /** Execute a hook across all registered plugins */
  async executeHook(hook: HookType, payload: Record<string, unknown>): Promise<HookResult[]> {
    const results: HookResult[] = [];
    for (const plugin of this.plugins.values()) {
      const handlers = plugin.getHooks().get(hook) || [];
      for (const handler of handlers) {
        const result = await handler({
          hook,
          plugin,
          payload,
          timestamp: new Date().toISOString(),
        });
        results.push(result);
        if (result.continue === false) break;
      }
    }
    return results;
  }

  /** Initialize all plugins */
  async initializeAll(): Promise<void> {
    for (const plugin of this.plugins.values()) {
      await plugin.initialize();
    }
  }

  /** Shutdown all plugins */
  async shutdownAll(): Promise<void> {
    for (const plugin of this.plugins.values()) {
      await plugin.shutdown();
    }
  }
}

/** Singleton registry instance */
export const registry = new PluginRegistry();

// ============================================================================
// Utility Functions
// ============================================================================

/** Create a plugin manifest with defaults */
export function createManifest(overrides: Partial<PluginManifest> & Pick<PluginManifest, "id" | "name">): PluginManifest {
  return {
    version: "1.0.0",
    author: "unknown",
    description: "",
    license: "MIT",
    tags: [],
    hermesVersion: ">=1.0.0",
    category: "tool",
    ...overrides,
  };
}

/** Validate a plugin manifest */
export function validateManifest(manifest: PluginManifest): string[] {
  const errors: string[] = [];
  if (!manifest.id) errors.push("id is required");
  if (!manifest.name) errors.push("name is required");
  if (!manifest.version) errors.push("version is required");
  if (!/^\d+\.\d+\.\d+/.test(manifest.version)) errors.push("version must be semver");
  if (manifest.description && manifest.description.length > 200) {
    errors.push("description must be <= 200 chars");
  }
  return errors;
}

// ============================================================================
// SKILL.md Types (for TypeScript consumers)
// ============================================================================

/** SKILL.md frontmatter schema */
export interface SkillMetadata {
  name: string;
  skill_id?: string;
  version: string;
  description: string;
  author: string;
  source?: string;
  license?: string;
  tags?: string[];
  security?: {
    permissions: string[];
    max_cost_estimate?: number;
    network_domains?: string[];
    filesystem_scope?: string[];
    requires_approval?: boolean;
  };
  runtime?: {
    min_tokens?: number;
    max_tokens?: number;
    timeout_seconds?: number;
    recommended_model?: string;
  };
  audit?: {
    hash?: string;
    last_scanned?: string;
    scan_rating?: string;
    scan_score?: number;
  };
}

/** Registry skill entry */
export interface RegistrySkill {
  skill_id: string;
  name: string;
  version: string;
  author: string;
  description: string;
  rating: string;
  score: number;
  source: string;
  tags: string[];
  status: "verified" | "needs_review" | "rejected";
  category: string;
  added_at: string;
  license?: string;
}

// ============================================================================
// Memory Types
// ============================================================================

/** Memory namespace definition */
export interface MemoryNamespace {
  id: "shared" | "personal" | "board" | "audit";
  access: "team" | "owner" | "board" | "governance";
  retention_days: number | null;
  desc: string;
  entry_count?: number;
}

/** Memory entry */
export interface MemoryEntry {
  timestamp: string;
  author: string;
  body: string;
  entry_id?: string;
  namespace?: string;
  audit_hash?: string;
}

// ============================================================================
// Connector Types
// ============================================================================

/** Supported platforms */
export type Platform = "feishu" | "slack" | "discord";

/** Outgoing message */
export interface OutgoingMessage {
  platform: Platform;
  channel: string;
  text: string;
  markdown?: boolean;
  thread_id?: string;
}

/** Incoming message (from webhook) */
export interface IncomingMessage {
  platform: Platform;
  channel: string;
  text: string;
  user: string;
  timestamp: string;
  thread_id?: string;
}

// ============================================================================
// Export
// ============================================================================
export default {
  Plugin,
  registry,
  createManifest,
  validateManifest,
};
