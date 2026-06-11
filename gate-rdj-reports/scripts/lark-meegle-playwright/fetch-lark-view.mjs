#!/usr/bin/env node
/**
 * 用 Chromium（Playwright）打开 Lark Meegle 多项目视图页，拦截 JSON 接口并导出 CSV。
 *
 * 说明：该页面为 SPA，未登录只能抓到营销站静态壳；首次请在已登录环境下保存会话。
 *
 * 用法：
 *   npm install && npx playwright install chromium
 *
 *   # 有登录态文件时（推荐）
 *   node fetch-lark-view.mjs --storage ~/.lark-meegle-auth.json \
 *     "https://project.larksuite.com/iocb9y/multiProjectView/4lGPhsI09?scope=workspaces&node=398418"
 *
 *   # 首次：弹出浏览器，手动登录 Lark 后按回车保存会话
 *   node fetch-lark-view.mjs --headed --save-storage ./data/lark_auth.json "<url>"
 *
 * 输出：
 *   ../../data/meegle_page_capture.json   原始拦截的 JSON（摘要）
 *   ../../data/meegle_page_export.csv     合并分页后的工作项 CSV
 *
 * 分页不足时加大：--scroll-rounds 50 --wait-ms 120000
 */

import crypto from 'crypto';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';
import { chromium } from 'playwright';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, '..', '..');
const DEFAULT_JSON = path.join(REPO_ROOT, 'data', 'meegle_page_capture.json');
const DEFAULT_CSV = path.join(REPO_ROOT, 'data', 'meegle_page_export.csv');

function parseArgs(argv) {
  const o = {
    url: '',
    headed: false,
    storage: process.env.LARK_STORAGE_STATE || '',
    saveStorage: '',
    waitMs: 25000,
    scrollRounds: 25,
    scrollPauseMs: 700,
    outJson: DEFAULT_JSON,
    outCsv: DEFAULT_CSV,
  };
  const rest = [];
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--headed') o.headed = true;
    else if (a === '--wait-ms' && argv[i + 1]) o.waitMs = parseInt(argv[++i], 10);
    else if (a === '--scroll-rounds' && argv[i + 1]) o.scrollRounds = parseInt(argv[++i], 10);
    else if (a === '--scroll-pause-ms' && argv[i + 1]) o.scrollPauseMs = parseInt(argv[++i], 10);
    else if (a === '--storage' && argv[i + 1]) o.storage = path.resolve(argv[++i]);
    else if (a === '--save-storage' && argv[i + 1]) o.saveStorage = path.resolve(argv[++i]);
    else if (a === '--out-json' && argv[i + 1]) o.outJson = path.resolve(argv[++i]);
    else if (a === '--out-csv' && argv[i + 1]) o.outCsv = path.resolve(argv[++i]);
    else if (a.startsWith('--')) {
      console.error('未知参数:', a);
      process.exit(2);
    } else rest.push(a);
  }
  o.url = rest[0] || '';
  return o;
}

function shouldCaptureUrl(url) {
  try {
    const u = new URL(url);
    if (!/larksuite\.com|feishu\.cn|feishu\.com/i.test(u.hostname)) return false;
    return true;
  } catch {
    return false;
  }
}

function flattenObj(obj, prefix = '') {
  const out = {};
  if (obj === null || obj === undefined) {
    out[prefix || 'value'] = '';
    return out;
  }
  if (typeof obj !== 'object') {
    out[prefix || 'value'] = obj;
    return out;
  }
  if (Array.isArray(obj)) {
    out[prefix || 'items'] = JSON.stringify(obj);
    return out;
  }
  for (const [k, v] of Object.entries(obj)) {
    const key = prefix ? `${prefix}.${k}` : k;
    if (v !== null && typeof v === 'object' && !Array.isArray(v)) {
      Object.assign(out, flattenObj(v, key));
    } else if (Array.isArray(v)) {
      out[key] = JSON.stringify(v);
    } else {
      out[key] = v;
    }
  }
  return out;
}

function isPlainRecord(x) {
  return x !== null && typeof x === 'object' && !Array.isArray(x);
}

/** 收集 JSON 内所有「对象数组」候选（长度≥2） */
function collectObjectArrays(root, maxDepth = 12, out = []) {
  function walk(node, depth) {
    if (depth > maxDepth || node === null || typeof node !== 'object') return;
    if (Array.isArray(node)) {
      const objects = node.filter(isPlainRecord);
      if (objects.length >= 2) out.push(objects);
      for (const el of node) walk(el, depth + 1);
      return;
    }
    for (const v of Object.values(node)) walk(v, depth + 1);
  }
  walk(root, 0);
  return out;
}

function scoreUrl(url) {
  const u = url.toLowerCase();
  if (
    u.includes('/settings/fg') ||
    u.includes('slardar') ||
    u.includes('monitor_web') ||
    u.includes('browser-settings') ||
    u.includes('/monitor/')
  ) {
    return -10000;
  }
  let s = 0;
  if (u.includes('multi_project') || u.includes('multiproject') || u.includes('multi-project'))
    s += 800;
  if (u.includes('work_item') || u.includes('workitem') || u.includes('story') || u.includes('issue'))
    s += 600;
  if (u.includes('structure_and_detail') || u.includes('work_item_list') || u.includes('batch_query'))
    s += 400;
  if (u.includes('project_view') || u.includes('panorama') || u.includes('workspace')) s += 400;
  if (u.includes('/goapi/') || u.includes('/m-api/')) s += 50;
  return s;
}

function scoreRowShape(sample) {
  if (!isPlainRecord(sample)) return -500;
  const keys = Object.keys(sample).map((k) => k.toLowerCase());
  let s = 0;
  const hints = [
    'title',
    'name',
    'summary',
    'story',
    'issue',
    'owner',
    'assignee',
    'status',
    'priority',
    'project',
    'iteration',
    'node',
    'work_item',
    'workitem_id',
    'id',
  ];
  for (const h of hints) {
    if (keys.some((x) => x === h || x.includes(h))) s += 80;
  }
  // 典型功能开关 / 埋点配置行，降权
  if (
    keys.includes('key') &&
    (keys.includes('is_hit') || keys.includes('exist')) &&
    keys.length <= 5
  ) {
    s -= 900;
  }
  return s;
}

function pickBestRowsFromCapture(body, url) {
  const urlScore = scoreUrl(url);
  if (urlScore <= -9000) {
    return { rows: [], score: -Infinity, urlScore };
  }

  const candidates = collectObjectArrays(body);
  let best = [];
  let bestScore = -Infinity;
  for (const rows of candidates) {
    const shape = scoreRowShape(rows[0]);
    const lenBonus = Math.min(rows.length, 20000) * 0.02;
    const total = urlScore + shape + lenBonus;
    if (total > bestScore) {
      bestScore = total;
      best = rows;
    }
  }
  return { rows: best, score: bestScore, urlScore };
}

function rowsToCsv(rows) {
  if (!rows.length) return '';
  const flat = rows.map((r) => flattenObj(r));
  const keys = [...new Set(flat.flatMap((r) => Object.keys(r)))];
  const esc = (s) => {
    const t = s === null || s === undefined ? '' : String(s);
    if (/[",\n\r]/.test(t)) return `"${t.replace(/"/g, '""')}"`;
    return t;
  };
  const header = keys.map(esc).join(',');
  const lines = flat.map((row) => keys.map((k) => esc(row[k])).join(','));
  return [header, ...lines].join('\n') + '\n';
}

function rowDedupeKey(row) {
  if (!isPlainRecord(row)) return JSON.stringify(row).slice(0, 120);
  const id =
    row.work_item_id ??
    row.workItemID ??
    row.work_item_id_str ??
    row.storyID ??
    row.story_id ??
    row.id ??
    row.work_item_key;
  if (id !== undefined && id !== null && String(id).length) return `id:${String(id)}`;
  const name =
    row.uiDataMap?.['1l5clgkicafc2']?.uiValue?.nameWithComment?.value ??
    row.name ??
    row.title;
  return `hash:${String(name || '').slice(0, 80)}`;
}

/** Meegle 列表页真实需求行：仅存在于接口 data.work_item_detail_v2 */
function extractWorkItemDetailV2Rows(body) {
  const data = body?.data;
  if (!data || typeof data !== 'object' || Array.isArray(data)) return [];
  const v2 = data.work_item_detail_v2;
  if (!v2 || typeof v2 !== 'object') return [];
  const out = [];
  for (const arr of Object.values(v2)) {
    if (!Array.isArray(arr)) continue;
    for (const row of arr) {
      if (row && typeof row === 'object' && !Array.isArray(row)) out.push(row);
    }
  }
  return out;
}

/** 旧逻辑：从任意 JSON 里猜对象数组（易混入工作项类型配置等杂数据） */
function fallbackMergeRowsFromCaptures(captures) {
  const map = new Map();
  let bestSingle = [];
  let bestScore = -Infinity;
  let bestSource = '';

  for (const cap of captures) {
    const { rows, score } = pickBestRowsFromCapture(cap.body, cap.url);
    if (rows.length >= 2 && score > bestScore) {
      bestScore = score;
      bestSingle = rows;
      bestSource = cap.url;
    }
    const u = cap.url.toLowerCase();
    const looksLikeWorkItems =
      u.includes('work_item') ||
      u.includes('structure_and_detail') ||
      u.includes('workitem') ||
      (u.includes('/goapi/') && u.includes('search'));
    if (!looksLikeWorkItems || rows.length < 1) continue;
    for (const row of rows) {
      if (!isPlainRecord(row)) continue;
      const k = rowDedupeKey(row);
      if (!map.has(k)) map.set(k, row);
    }
  }

  const merged = [...map.values()];
  if (merged.length >= bestSingle.length) {
    return {
      rows: merged,
      source: `merged:${merged.length}_from_${captures.length}_responses`,
      mergedCount: merged.length,
      singleBestCount: bestSingle.length,
      singleBestSource: bestSource,
    };
  }
  return {
    rows: bestSingle,
    source: bestSource,
    mergedCount: merged.length,
    singleBestCount: bestSingle.length,
    singleBestSource: bestSource,
  };
}

/** 优先合并 work_item_detail_v2（唯一可信的需求实例数据源） */
function mergeRowsFromCaptures(captures) {
  const map = new Map();
  let detailCaptureCount = 0;

  for (const cap of captures) {
    const rows = extractWorkItemDetailV2Rows(cap.body);
    if (!rows.length) continue;
    detailCaptureCount += 1;
    for (const row of rows) {
      const wid = row.work_item_id ?? row.storyID;
      if (wid === undefined || wid === null || wid === '') continue;
      const k = `id:${String(wid)}`;
      const prev = map.get(k);
      const ua = row.updatedAt;
      const pa = prev?.updatedAt;
      if (!prev) {
        map.set(k, row);
        continue;
      }
      if (typeof ua === 'number' && typeof pa === 'number' && ua >= pa) map.set(k, row);
      else if (typeof ua === 'number' && typeof pa !== 'number') map.set(k, row);
    }
  }

  const merged = [...map.values()];
  if (merged.length > 0) {
    return {
      rows: merged,
      source: `work_item_detail_v2:${detailCaptureCount}_captures_${merged.length}_rows`,
      mergedCount: merged.length,
      singleBestCount: merged.length,
      singleBestSource: 'data.work_item_detail_v2',
      detailCaptureCount,
    };
  }

  return { ...fallbackMergeRowsFromCaptures(captures), detailCaptureCount: 0 };
}

async function scrollLoadMore(page, rounds, pauseMs) {
  for (let i = 0; i < rounds; i++) {
    if (i % 5 === 4) {
      await page.keyboard.press('End').catch(() => {});
    }
    await page.evaluate(() => {
      const cand = document.querySelector(
        '[class*="scroll"], main, [role="main"], .semi-table-body, [data-scroll]',
      );
      const el = cand || document.documentElement;
      el.scrollTop = (el.scrollTop || 0) + Math.min(900, window.innerHeight);
      window.scrollBy(0, window.innerHeight * 0.9);
    });
    await new Promise((r) => setTimeout(r, pauseMs));
  }
}

async function extractTablesFromDom(page) {
  return page.evaluate(() => {
    const tables = Array.from(document.querySelectorAll('table'));
    const out = [];
    for (const t of tables) {
      const rows = Array.from(t.querySelectorAll('tr')).map((tr) =>
        Array.from(tr.querySelectorAll('th,td')).map((c) => (c.innerText || '').trim()),
      );
      if (rows.length) out.push(rows);
    }
    return out;
  });
}

async function main() {
  const opts = parseArgs(process.argv.slice(2));
  if (!opts.url) {
    console.error('请传入页面 URL');
    process.exit(2);
  }

  const captures = [];
  /** 同一 URL 可能有多段分页响应，不能按 URL 去重；仅按正文 hash 去重 */
  const seenBody = new Set();

  const browser = await chromium.launch({
    headless: !opts.headed,
    channel: process.env.PLAYWRIGHT_CHROME_CHANNEL || undefined,
  });

  const storageExists = opts.storage && fs.existsSync(opts.storage);
  const context = await browser.newContext(
    storageExists
      ? { storageState: opts.storage }
      : {
          locale: 'zh-CN',
          userAgent:
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        },
  );

  const page = await context.newPage();

  page.on('response', async (response) => {
    const url = response.url();
    if (!shouldCaptureUrl(url)) return;
    const ct = (response.headers()['content-type'] || '').toLowerCase();
    if (!ct.includes('json')) return;
    try {
      const buf = await response.body();
      const text = buf.toString('utf8');
      if (!text || (text[0] !== '{' && text[0] !== '[')) return;
      const sig = crypto.createHash('sha256').update(text).digest('hex');
      if (seenBody.has(sig)) return;
      seenBody.add(sig);
      const body = JSON.parse(text);
      captures.push({ url, approxSize: text.length, body });
    } catch {
      /* 非 JSON 或过大跳过 */
    }
  });

  console.error('打开:', opts.url);
  await page.goto(opts.url, { waitUntil: 'domcontentloaded', timeout: 120000 });
  await new Promise((r) => setTimeout(r, Math.min(8000, opts.waitMs)));
  console.error(
    `滚动加载: ${opts.scrollRounds} 轮, 间隔 ${opts.scrollPauseMs}ms（触发分页/虚拟列表）`,
  );
  await scrollLoadMore(page, opts.scrollRounds, opts.scrollPauseMs);
  await new Promise((r) =>
    setTimeout(r, Math.max(0, Math.min(opts.waitMs, 120000) - Math.min(8000, opts.waitMs))),
  );

  if (opts.saveStorage) {
    console.error('若未登录请在浏览器中完成登录，然后在终端按回车以保存会话…');
    if (opts.headed) {
      await new Promise((r) => process.stdin.once('data', r));
    }
    fs.mkdirSync(path.dirname(opts.saveStorage), { recursive: true });
    await context.storageState({ path: opts.saveStorage });
    console.error('已保存会话:', opts.saveStorage);
  }

  const domTables = await extractTablesFromDom(page).catch(() => []);

  const merged = mergeRowsFromCaptures(captures);
  let bestRows = merged.rows;
  let bestSource = merged.source;

  if (!bestRows.length && domTables.length) {
    const largest = domTables.reduce((a, b) => (a.length >= b.length ? a : b), []);
    if (largest.length > 1) {
      const header = largest[0];
      bestRows = largest.slice(1).map((cells) => {
        const o = {};
        cells.forEach((c, i) => {
          o[header[i] || `col_${i}`] = c;
        });
        return o;
      });
      bestSource = 'dom:table';
    }
  }

  fs.mkdirSync(path.dirname(opts.outJson), { recursive: true });

  const summary = {
    fetchedAt: new Date().toISOString(),
    pageUrl: opts.url,
    captureCount: captures.length,
    capturesMeta: captures.map((c) => ({ url: c.url, approxSize: c.approxSize })),
    bestRowsSource: bestSource || null,
    bestRowCount: bestRows.length,
    mergedRowCount: merged.mergedCount,
    singleBestRowCount: merged.singleBestCount,
    singleBestSource: merged.singleBestSource,
    detailV2CaptureCount: merged.detailCaptureCount ?? 0,
    scrollRounds: opts.scrollRounds,
    domTableCount: domTables.length,
    loginHint:
      captures.length === 0
        ? '未拦截到 Lark JSON：多为未登录或接口域名不匹配。请使用 --headed --save-storage 登录一次，或传入已有 storageState。'
        : undefined,
  };

  fs.writeFileSync(opts.outJson, JSON.stringify({ summary, captures }, null, 2), 'utf8');
  console.error('JSON:', opts.outJson);

  const csv = rowsToCsv(bestRows);
  fs.writeFileSync(opts.outCsv, csv || 'warning,no_data\ntrue,see_json_and_console\n', 'utf8');
  console.error('CSV:', opts.outCsv, bestRows.length ? `(${bestRows.length} 行)` : '(占位，请查看 JSON / 登录重试)');

  await browser.close();

  if (!bestRows.length) {
    console.error(summary.loginHint || '未能解析出表格行，请查看 capture JSON 手工筛选接口。');
    process.exit(1);
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
