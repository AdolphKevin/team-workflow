// 接管已打开的 Chrome 执行场景验收。复制到业务仓库的验收目录后按需调整。
//
// 环境变量：
//   PW_TAB               必填。目标标签页 URL 的子串，只操作匹配的那一个标签页。
//   PW_CDP_ENDPOINT      可选。CDP 地址（ws://… 或 http://127.0.0.1:9222）；缺省读 Chrome 的 DevToolsActivePort。
//   PW_CHROME_USER_DATA  可选。Chrome 用户数据目录；缺省按操作系统取默认目录。
//   PW_CASES             可选。scripts/case_tags.py 生成的 cases.json，用于给测试加上游用例 tag。
//   PW_OUT               可选。输出目录（仓库外），由 playwright.config.mjs 读取。
//
// 依赖：@playwright/test >= 1.64（page.screencast）；录屏需先执行 npx playwright install ffmpeg
//（ffmpeg 装在 PLAYWRIGHT_BROWSERS_PATH 或默认缓存目录，换机器、换该变量都要重装；global-setup.mjs 会在开跑前检查）。
import { test as base, chromium } from '@playwright/test';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const BLOCKED_PREFIX = '受阻：';

function chromeUserData() {
  if (process.env.PW_CHROME_USER_DATA) return process.env.PW_CHROME_USER_DATA;
  const home = os.homedir();
  if (process.platform === 'darwin') return path.join(home, 'Library/Application Support/Google/Chrome');
  if (process.platform === 'win32') return path.join(process.env.LOCALAPPDATA || path.join(home, 'AppData/Local'), 'Google/Chrome/User Data');
  return path.join(home, '.config/google-chrome');
}

export function cdpEndpoint() {
  if (process.env.PW_CDP_ENDPOINT) return process.env.PW_CDP_ENDPOINT;
  const file = path.join(chromeUserData(), 'DevToolsActivePort');
  if (!fs.existsSync(file)) {
    throw new Error(`没有找到 ${file}。请在 Chrome 打开 chrome://inspect/#remote-debugging 并启用远程调试，或设置 PW_CDP_ENDPOINT。`);
  }
  const [port, wsPath] = fs.readFileSync(file, 'utf8').trim().split('\n');
  return `ws://127.0.0.1:${port}${wsPath}`;
}

// 受阻：前置条件不满足、人机验证、登录过期、未知遮挡。to_scenarios.py 据此输出 blocked。
export function blocked(reason) {
  return new Error(BLOCKED_PREFIX + reason);
}

// 读取 cases.json，为场景生成 tag：['@SOP-02-P01', '@CASE-037', …]。tag 只能来自配对文件。
let casesCache;
export function tags(scenarioId) {
  if (casesCache === undefined) {
    const file = process.env.PW_CASES;
    casesCache = file && fs.existsSync(file) ? JSON.parse(fs.readFileSync(file, 'utf8')).scenarios || {} : {};
  }
  return ['@' + scenarioId, ...(casesCache[scenarioId] || []).map((id) => '@' + id)];
}

export const test = base.extend({
  page: async ({}, use, testInfo) => {
    const marker = process.env.PW_TAB;
    if (!marker) throw new Error('请设置 PW_TAB 为目标标签页 URL 的子串');
    const browser = await chromium.connectOverCDP(cdpEndpoint(), { timeout: 60000 });
    const context = browser.contexts()[0];
    const matches = context.pages().filter((p) => p.url().includes(marker));
    if (matches.length !== 1) {
      await browser.close();
      throw new Error(`URL 含 "${marker}" 的标签页有 ${matches.length} 个，需要正好一个：\n` + matches.map((p) => p.url()).join('\n'));
    }
    const page = matches[0];

    const video = testInfo.outputPath('video.webm');
    const size = await page.evaluate(() => ({ width: window.innerWidth, height: window.innerHeight }));
    await page.screencast.start({ path: video, size });
    await page.screencast.showActions({ position: 'top', duration: 800 });

    // 新开的标签页各录一段；录屏帧宽约 800 像素，按页面比例设画布避免灰边。
    const popups = [];
    const onPage = (popup) => {
      const file = testInfo.outputPath(`video-tab-${popups.length + 1}.webm`);
      const started = popup.waitForLoadState('domcontentloaded')
        .then(() => popup.evaluate(() => window.innerHeight / window.innerWidth))
        .then((ratio) => popup.screencast.start({ path: file, size: { width: 800, height: Math.round(800 * ratio) } }))
        .then(() => true)
        .catch(() => false);
      popups.push({ popup, file, started });
    };
    context.on('page', onPage);
    await context.tracing.start({ screenshots: true, snapshots: true, title: testInfo.title });
    try {
      await use(page);
    } finally {
      context.off('page', onPage);
      const trace = testInfo.outputPath('trace.zip');
      await context.tracing.stop({ path: trace });
      await page.screencast.hideActions().catch(() => {});
      await page.screencast.stop().catch(() => {});
      if (fs.existsSync(video)) await testInfo.attach('video', { path: video, contentType: 'video/webm' });
      for (const [index, { popup, file, started }] of popups.entries()) {
        if (!(await started)) continue;
        await popup.screencast.stop().catch(() => {});
        if (fs.existsSync(file)) await testInfo.attach(`video-新标签页-${index + 1}`, { path: file, contentType: 'video/webm' });
      }
      await testInfo.attach('trace', { path: trace, contentType: 'application/zip' });
      await browser.close();
    }
  },
});

// 一条场景步骤对应一个 step：录屏中显示章节标题，report 中显示同名步骤。
export async function step(page, title, body) {
  return test.step(title, async () => {
    await page.screencast.showChapter(title, { duration: 1200 }).catch(() => {});
    return body();
  });
}

// 截图并附到 report；target 可以是 page 或新标签页。
export async function shot(testInfo, target, name) {
  await testInfo.attach(name, { body: await target.screenshot(), contentType: 'image/png' });
}

export { expect } from '@playwright/test';
