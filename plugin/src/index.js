/**
 * Context Nexus — OpenClaw Plugin
 *
 * Provides: before_prompt_build, after_tool_call, session_end hooks
 * Exposes tools: nexus_memory, nexus_logs, nexus_secrets, nexus_replay, nexus_admin
 */
const { spawn } = require('child_process');
const path = require('path');
const os = require('os');

let dbPath = null;
let eventCount = 0;

function pythonCall(method, params = {}) {
  return new Promise((resolve, reject) => {
    const pluginDir = __dirname;
    const script = path.join(pluginDir, 'nexus_service.py');
    const args = [script, method, JSON.stringify(params)];
    const proc = spawn('python3', args, {
      stdio: ['pipe', 'pipe', 'pipe'],
      env: { ...process.env, CONTEXT_NEXUS_DB_PATH: dbPath || '' },
    });
    let stdout = '';
    let stderr = '';
    proc.stdout.on('data', (d) => (stdout += d.toString()));
    proc.stderr.on('data', (d) => (stderr += d.toString()));
    proc.on('close', (code) => {
      if (code !== 0) reject(new Error(stderr || `python exited ${code}`));
      else {
        try {
          resolve(JSON.parse(stdout.trim()));
        } catch {
          resolve({ raw: stdout.trim() });
        }
      }
    });
  });
}

function registerHooks({ registerHook, log }) {
  // ── before_prompt_build ─────────────────────────────────────────────────
  registerHook('before_prompt_build', async ({ session, messages, env }) => {
    try {
      const threadId = env?.currentThread || session?.id || 'default';
      const recent = await pythonCall('memory_recent', { limit: 5, scope: 'durable' });
      if (!recent || recent.length === 0) return {};

      const memoryLines = recent
        .map((m) => `[memory:${m.key}] ${typeof m.value === 'string' ? m.value : JSON.stringify(m.value)}`)
        .join('\n');

      return {
        prependContext: `[Prior context from recent memory]\n${memoryLines}\n[/prior context]`,
      };
    } catch (err) {
      log.warn('context-nexus: before_prompt_build failed', { error: err.message });
      return {};
    }
  });

  // ── after_tool_call ────────────────────────────────────────────────────
  registerHook('after_tool_call', async ({ tool, params, result, session, env }) => {
    try {
      eventCount++;
      const threadId = env?.currentThread || session?.id || 'default';
      await pythonCall('log_event', {
        event_type: 'tool_call',
        session_id: session?.id || 'unknown',
        thread_id: threadId,
        input_summary: `${tool}(${Object.keys(params || {}).join(', ')})`,
        output_summary: result && typeof result === 'object' ? JSON.stringify(result).slice(0, 200) : String(result),
        status: 'success',
        correlation_id: env?.correlationId,
      });

      // Auto-distill on significant tools
      const significantTools = ['write', 'edit', 'exec', 'commit', 'deploy', 'browser', 'git'];
      if (significantTools.includes(tool)) {
        await pythonCall('distill_run', {
          session_id: session?.id || 'unknown',
          thread_id: threadId,
          goal: `${tool} called with params`,
          action_summary: `${tool} tool used`,
          result_summary: typeof result === 'object' ? JSON.stringify(result).slice(0, 300) : String(result),
          success: true,
          tools_used: [tool],
        });
      }

      // Periodic compaction
      const compactInterval = 100;
      if (eventCount % compactInterval === 0) {
        pythonCall('compact', {}).catch(() => {});
      }
    } catch (err) {
      log.warn('context-nexus: after_tool_call failed', { error: err.message });
    }
  });

  // ── session_end ────────────────────────────────────────────────────────
  registerHook('session_end', async ({ session, messages, env }) => {
    try {
      const threadId = env?.currentThread || session?.id || 'default';
      const goal = messages?.[0]?.content?.slice(0, 200) || 'session';
      const lastMsg = messages?.[messages.length - 1];
      const resultSummary = lastMsg?.content?.slice(0, 300) || '';

      await pythonCall('distill_run', {
        session_id: session?.id || 'unknown',
        thread_id: threadId,
        goal,
        action_summary: 'Session completed',
        result_summary: resultSummary,
        success: true,
      });
    } catch (err) {
      log.warn('context-nexus: session_end failed', { error: err.message });
    }
  });

  // ── on_error ──────────────────────────────────────────────────────────
  registerHook('on_error', async ({ error, session, env }) => {
    try {
      const threadId = env?.currentThread || session?.id || 'unknown';
      const errorCode = error?.code || 'UNKNOWN';
      const errorMessage = error?.message || String(error);
      await pythonCall('log_event', {
        event_type: 'error',
        session_id: session?.id || 'unknown',
        thread_id: threadId,
        status: 'error',
        error_code: errorCode,
        error_message: errorMessage.slice(0, 300),
      });
      await pythonCall('distill_run', {
        session_id: session?.id || 'unknown',
        thread_id: threadId,
        goal: 'session',
        action_summary: 'Session error',
        result_summary: `${errorCode}: ${errorMessage}`.slice(0, 300),
        success: false,
      });
    } catch (err) {
      log.warn('context-nexus: on_error failed', { error: err.message });
    }
  });
}

// ── Tool definitions ──────────────────────────────────────────────────────────

const memoryTool = {
  name: 'nexus_memory',
  description: 'Persistent cross-session memory for Context Nexus. Set, get, search, pin, forget, or compact memories.',
  inputSchema: {
    type: 'object',
    properties: {
      action: { type: 'string', enum: ['set', 'get', 'search', 'recent', 'pin', 'forget', 'compact'] },
      key: { type: 'string', description: 'Memory key' },
      value: { type: 'string', description: 'Value (for set)' },
      scope: { type: 'string', enum: ['ephemeral', 'durable', 'pinned'], default: 'durable' },
      importance: { type: 'integer', minimum: 1, maximum: 10, default: 5 },
      query: { type: 'string', description: 'Search query (for search action)' },
      limit: { type: 'integer', default: 10 },
      pinned: { type: 'boolean', default: true },
    },
    required: ['action'],
  },
};

const logsTool = {
  name: 'nexus_logs',
  description: 'Query structured event logs and session summaries from Context Nexus.',
  inputSchema: {
    type: 'object',
    properties: {
      action: { type: 'string', enum: ['list_events', 'get_event', 'query_failures', 'summarize_session'] },
      event_id: { type: 'string' },
      session_id: { type: 'string' },
      limit: { type: 'integer', default: 20 },
    },
    required: ['action'],
  },
};

const secretsTool = {
  name: 'nexus_secrets',
  description: 'Securely store, retrieve, and manage encrypted secrets in Context Nexus.',
  inputSchema: {
    type: 'object',
    properties: {
      action: { type: 'string', enum: ['store', 'get', 'list', 'delete'] },
      name: { type: 'string' },
      value: { type: 'string' },
      metadata: { type: 'object' },
    },
    required: ['action', 'name'],
  },
};

const replayTool = {
  name: 'nexus_replay',
  description: 'Replay and inspect prior agent sessions and their context.',
  inputSchema: {
    type: 'object',
    properties: {
      action: { type: 'string', enum: ['session_timeline', 'explain_failure', 'compare_runs', 'show_loaded_context'] },
      session_id: { type: 'string' },
      limit: { type: 'integer', default: 10 },
    },
    required: ['action'],
  },
};

const adminTool = {
  name: 'nexus_admin',
  description: 'Context Nexus system administration: health check, storage status, compaction, and snapshots.',
  inputSchema: {
    type: 'object',
    properties: {
      action: { type: 'string', enum: ['healthcheck', 'storage_status', 'run_compaction', 'export_snapshot'] },
    },
    required: ['action'],
  },
};

function registerTools({ registerTool }) {
  registerTool(memoryTool, async ({ action, key, value, scope, importance, query, limit, pinned }) => {
    switch (action) {
      case 'set':
        return pythonCall('memory_set', { key, value, scope: scope || 'durable', importance: importance || 5 });
      case 'get':
        return pythonCall('memory_get', { key, scope });
      case 'search':
        return pythonCall('memory_search', { query: query || '', limit: limit || 10 });
      case 'recent':
        return pythonCall('memory_recent', { limit: limit || 10, scope });
      case 'pin':
        return pythonCall('memory_pin', { key, pin: pinned !== false });
      case 'forget':
        return pythonCall('memory_forget', { key, scope });
      case 'compact':
        return pythonCall('compact', {});
      default:
        return { error: `Unknown action: ${action}` };
    }
  });

  registerTool(logsTool, async ({ action, event_id, session_id, limit }) => {
    switch (action) {
      case 'list_events':
        return pythonCall('list_events', { limit: limit || 20, session_id });
      case 'get_event':
        return pythonCall('get_event', { event_id });
      case 'query_failures':
        return pythonCall('query_failures', { limit: limit || 20 });
      case 'summarize_session':
        return pythonCall('summarize_session', { session_id });
      default:
        return { error: `Unknown action: ${action}` };
    }
  });

  registerTool(secretsTool, async ({ action, name, value, metadata }) => {
    switch (action) {
      case 'store':
        if (!value) return { error: 'value required for store' };
        return pythonCall('secret_store', { name, value, metadata: metadata || {} });
      case 'get':
        return pythonCall('secret_get', { name });
      case 'list':
        return pythonCall('secret_list', {});
      case 'delete':
        return pythonCall('secret_delete', { name });
      default:
        return { error: `Unknown action: ${action}` };
    }
  });

  registerTool(replayTool, async ({ action, session_id, limit }) => {
    switch (action) {
      case 'session_timeline':
        return pythonCall('session_timeline', { session_id, limit: limit || 20 });
      case 'explain_failure':
        return pythonCall('explain_failure', { session_id });
      case 'compare_runs':
        return pythonCall('compare_runs', { limit: limit || 10 });
      case 'show_loaded_context':
        return pythonCall('show_loaded_context', { session_id });
      default:
        return { error: `Unknown action: ${action}` };
    }
  });

  registerTool(adminTool, async ({ action }) => {
    switch (action) {
      case 'healthcheck':
        return pythonCall('healthcheck', {});
      case 'storage_status':
        return pythonCall('storage_status', {});
      case 'run_compaction':
        return pythonCall('compact', {});
      case 'export_snapshot':
        return pythonCall('export_snapshot', {});
      default:
        return { error: `Unknown action: ${action}` };
    }
  });
}

module.exports = { register: registerHooks, registerTools };
