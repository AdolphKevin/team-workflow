// 开跑前的环境检查：任何一项不满足就整轮不跑，避免把环境问题记成场景失败。
// 由 playwright.config.mjs 的 globalSetup 引用。
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import { cdpEndpoint } from './scenarios/fixtures.mjs';

function ffmpegInstalled() {
  const npx = process.platform === 'win32' ? 'npx.cmd' : 'npx';
  const text = execFileSync(npx, ['playwright', 'install', '--dry-run', 'ffmpeg'], { encoding: 'utf8' });
  const match = text.match(/Install location:\s*(.+)/);
  const location = match && match[1].trim();
  return Boolean(location && fs.existsSync(location) && fs.readdirSync(location).length > 0);
}

export default async function globalSetup() {
  const problems = [];
  if (!process.env.PW_TAB) problems.push('未设置 PW_TAB（目标标签页 URL 的子串）。');
  try {
    cdpEndpoint();
  } catch (error) {
    problems.push(error.message);
  }
  if (!ffmpegInstalled()) {
    problems.push('录屏需要 ffmpeg，当前环境没有安装。请先执行：npx playwright install ffmpeg'
      + (process.env.PLAYWRIGHT_BROWSERS_PATH ? `（注意 PLAYWRIGHT_BROWSERS_PATH=${process.env.PLAYWRIGHT_BROWSERS_PATH}）` : ''));
  }
  if (problems.length) {
    throw new Error('环境检查未通过，本轮未执行任何场景：\n- ' + problems.join('\n- '));
  }
}
