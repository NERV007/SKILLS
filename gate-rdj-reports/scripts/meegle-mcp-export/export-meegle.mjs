#!/usr/bin/env node
/**
 * 通过 Meegle MCP（Streamable HTTP）拉取 Lark/Meegle 页面数据并写入 CSV。
 *
 * 用法:
 *   node export-meegle.mjs --mcp-url "https://..." --list
 *   node export-meegle.mjs --mcp-url "https://..." "https://project.larksuite.com/..."
 *   node export-meegle.mjs --mcp-url "https://..." --tool get_xxx --args-json '{"k":"v"}'
 *
 * 环境变量（可选）:
 *   MEEGLE_MCP_URL     MCP 端点，等价于 --mcp-url
 *   MEEGLE_MCP_HEADERS JSON 字符串，额外 HTTP 头（如鉴权）
 */

import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StreamableHTTPClientTransport } from '@modelcontextprotocol/sdk/client/streamableHttp.js';
import { ListToolsResultSchema, CallToolResultSchema } from '@modelcontextprotocol/sdk/types.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

function parseArgs(argv) {
  const out = {
    mcpUrl: process.env.MEEGLE_MCP_URL || '',
    projectUrl: '',
    listOnly: false,
    toolName: '',
    argsJson: '',
    outCsv: path.join(__dirname, '..', '..', 'data', 'meegle_export.csv'),
    extraHeaders: {},
  };
  const rest = [];
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--mcp-url' && argv[i + 1]) {
      out.mcpUrl = argv[++i];
    } else if (a === '--list') {
      out.listOnly = true;
    } else if (a === '--tool' && argv[i + 1]) {
      out.toolName = argv[++i];
    } else if (a === '--args-json' && argv[i + 1]) {
      out.argsJson = argv[++i];
    } else if (a === '--out' && argv[i + 1]) {
      out.outCsv = path.resolve(argv[++i]);
    } else if (a.startsWith('--')) {
      console.error('未知参数:', a);
      process.exit(2);
    } else {
      rest.push(a);
    }
  }
  if (process.env.MEEGLE_MCP_HEADERS) {
    try {
      Object.assign(out.extraHeaders, JSON.parse(process.env.MEEGLE_MCP_HEADERS));
    } catch (e) {
      console.error('MEEGLE_MCP_HEADERS 必须是合法 JSON 对象');
      process.exit(2);
    }
  }
  out.projectUrl = rest[0] || '';
  return out;
}

function parseProjectUrl(urlStr) {
  const u = new URL(urlStr);
  const parts = u.pathname.split('/').filter(Boolean);
  // .../iocb9y/multiProjectView/4lGPhsI09
  let workspace_key = '';
  let multi_project_view_id = '';
  const mpi = parts.indexOf('multiProjectView');
  if (mpi >= 1) {
    workspace_key = parts[mpi - 1];
    multi_project_view_id = parts[mpi + 1] || '';
  }
  const node_id = u.searchParams.get('node') || '';
  const scope = u.searchParams.get('scope') || '';
  return {
    url: urlStr,
    workspace_key,
    multi_project_view_id,
    node_id,
    scope,
  };
}

function escapeCsvCell(val) {
  const s = val === null || val === undefined ? '' : String(val);
  if (/[",\n\r]/.test(s)) return `"${s.replace(/"/g, '""')}"`;
  return s;
}

function arrayOfObjectsToCsv(rows) {
  if (!rows.length) return '';
  const keys = [...new Set(rows.flatMap((r) => Object.keys(r)))];
  const header = keys.map(escapeCsvCell).join(',');
  const lines = rows.map((row) =>
    keys.map((k) => escapeCsvCell(row[k])).join(','),
  );
  return [header, ...lines].join('\n') + '\n';
}

function tryExtractRowsFromToolResult(result) {
  if (result.structuredContent && typeof result.structuredContent === 'object') {
    const sc = result.structuredContent;
    const arr =
      Array.isArray(sc) ? sc : sc.rows || sc.items || sc.data || null;
    if (arr && arr.length && typeof arr[0] === 'object') {
      return {
        kind: 'structured',
        csv: arrayOfObjectsToCsv(arr),
        raw: JSON.stringify(sc),
      };
    }
  }

  const texts = [];
  for (const block of result.content || []) {
    if (block.type === 'text' && block.text) texts.push(block.text);
  }
  const joined = texts.join('\n').trim();
  if (!joined) return { kind: 'empty', csv: '', raw: '' };

  // 已是 CSV
  if (joined.includes(',') && joined.split('\n').length > 1 && !joined.startsWith('{')) {
    return { kind: 'csv', csv: joined.endsWith('\n') ? joined : joined + '\n', raw: joined };
  }

  try {
    const data = JSON.parse(joined);
    if (Array.isArray(data) && data.length && typeof data[0] === 'object') {
      return { kind: 'json-rows', csv: arrayOfObjectsToCsv(data), raw: joined };
    }
    if (data && Array.isArray(data.rows)) {
      return { kind: 'json-rows', csv: arrayOfObjectsToCsv(data.rows), raw: joined };
    }
    if (data && Array.isArray(data.items)) {
      return { kind: 'json-rows', csv: arrayOfObjectsToCsv(data.items), raw: joined };
    }
    if (data && Array.isArray(data.data)) {
      return { kind: 'json-rows', csv: arrayOfObjectsToCsv(data.data), raw: joined };
    }
    // 单对象展开为一行
    if (typeof data === 'object' && !Array.isArray(data)) {
      return { kind: 'json-rows', csv: arrayOfObjectsToCsv([data]), raw: joined };
    }
  } catch {
    /* 非 JSON，按纯文本单行 CSV 兜底 */
  }
  return {
    kind: 'text',
    csv: arrayOfObjectsToCsv([{ content: joined }]),
    raw: joined,
  };
}

function guessTool(tools) {
  const keywords = [
    'multiproject',
    'multi_project',
    'workspace',
    'export',
    'list',
    'view',
    'work_item',
    'story',
    'requirement',
  ];
  const scored = tools.map((t) => {
    const n = (t.name || '').toLowerCase();
    let score = 0;
    for (const kw of keywords) {
      if (n.includes(kw)) score += 2;
    }
    return { tool: t, score };
  });
  scored.sort((a, b) => b.score - a.score);
  if (!scored.length || scored[0].score === 0) return '';
  return scored[0].tool.name;
}

async function main() {
  const opts = parseArgs(process.argv.slice(2));
  if (!opts.mcpUrl) {
    console.error('请设置 --mcp-url 或环境变量 MEEGLE_MCP_URL（与 .cursor/mcp.json 中 meegle.url 一致）。');
    process.exit(2);
  }

  const baseUrl = new URL(opts.mcpUrl);
  const defaultHeaders = {
    Accept: 'application/json, text/event-stream',
    ...opts.extraHeaders,
  };

  const transport = new StreamableHTTPClientTransport(baseUrl, {
    requestInit: { headers: defaultHeaders },
  });

  const client = new Client({ name: 'meegle-export', version: '1.0.0' });
  await client.connect(transport);

  try {
    const toolsResult = await client.request({ method: 'tools/list', params: {} }, ListToolsResultSchema);
    const tools = toolsResult.tools || [];

    if (opts.listOnly) {
      console.log(JSON.stringify(tools, null, 2));
      return;
    }

    if (!opts.projectUrl) {
      console.error('请传入 Meegle/Lark 项目 URL，或先用 --list 查看工具名与参数 schema。');
      process.exit(2);
    }

    const parsed = parseProjectUrl(opts.projectUrl);
    let toolName = opts.toolName || guessTool(tools);

    if (!toolName) {
      console.error('未能猜测工具名。请使用 --list 查看后指定 --tool <name>。');
      process.exit(1);
    }

    let args =
      opts.argsJson ? JSON.parse(opts.argsJson) : { ...parsed };

    const toolMeta = tools.find((t) => t.name === toolName);
    if (toolMeta?.inputSchema?.properties) {
      const props = Object.keys(toolMeta.inputSchema.properties);
      // 若 schema 要求单一 url 字段，收敛参数
      if (props.length === 1 && props[0] === 'url') {
        args = { url: opts.projectUrl };
      }
    }

    console.error(`调用工具: ${toolName}`);
    console.error('参数:', JSON.stringify(args, null, 2));

    const callResult = await client.request(
      {
        method: 'tools/call',
        params: { name: toolName, arguments: args },
      },
      CallToolResultSchema,
    );

    if (callResult.isError) {
      console.error('工具返回 isError=true，未写入 CSV。原始内容:');
      console.error(JSON.stringify(callResult.content, null, 2));
      process.exit(1);
    }

    const { csv } = tryExtractRowsFromToolResult(callResult);
    fs.mkdirSync(path.dirname(opts.outCsv), { recursive: true });
    fs.writeFileSync(opts.outCsv, csv, 'utf8');
    console.error(`已写入: ${opts.outCsv}`);
    console.log(csv.trimEnd());
  } finally {
    await transport.close();
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
