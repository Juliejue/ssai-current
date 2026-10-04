import fs from 'node:fs';
import path from 'node:path';

const root = path.resolve(import.meta.dirname, '..');
const out = path.join(root, 'docs', 'readme-assets');
fs.mkdirSync(out, { recursive: true });

const C = {
  paper: '#F3F6F4',
  white: '#FFFFFF',
  ink: '#102F33',
  teal: '#1E6E72',
  teal2: '#8FC3C0',
  teal3: '#DDECE9',
  orange: '#C4703C',
  orange2: '#F4D8C5',
  muted: '#60777A',
  line: '#CEDAD8',
  green: '#447B60',
  soft: '#E9EFED',
};

const font = "-apple-system,BlinkMacSystemFont,'PingFang SC','Noto Sans CJK SC','Microsoft YaHei',sans-serif";

function esc(s) {
  return String(s).replace(/[&<>\"]/g, (m) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[m]);
}

function dataUri(file, mime) {
  return `data:${mime};base64,${fs.readFileSync(path.join(out, file)).toString('base64')}`;
}

function svgStart(w, h, title, desc) {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" role="img" aria-labelledby="title desc">
  <title id="title">${esc(title)}</title>
  <desc id="desc">${esc(desc)}</desc>
  <defs>
    <filter id="shadow" x="-20%" y="-20%" width="140%" height="160%"><feDropShadow dx="0" dy="18" stdDeviation="22" flood-color="#102F33" flood-opacity=".10"/></filter>
    <filter id="softShadow" x="-20%" y="-20%" width="140%" height="160%"><feDropShadow dx="0" dy="8" stdDeviation="12" flood-color="#102F33" flood-opacity=".08"/></filter>
    <linearGradient id="paperGlow" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#FAFCFB"/><stop offset=".55" stop-color="#F3F6F4"/><stop offset="1" stop-color="#E6F0ED"/></linearGradient>
    <linearGradient id="tealGlow" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#174F53"/><stop offset="1" stop-color="#1E777A"/></linearGradient>
    <style>
      text { font-family: ${font}; }
      .title, .subtitle, .body, .small, .tiny, .label, .cardTitle { fill: ${C.ink}; }
      .muted { fill: ${C.muted}; }
      .eyebrow { font-size: 22px; font-weight: 700; letter-spacing: 3px; fill: ${C.teal}; }
      .title { font-size: 66px; font-weight: 800; letter-spacing: -2px; }
      .subtitle { font-size: 30px; font-weight: 600; }
      .body { font-size: 24px; }
      .small { font-size: 18px; }
      .tiny { font-size: 15px; }
      .label { font-size: 18px; font-weight: 700; }
      .cardTitle { font-size: 27px; font-weight: 800; }
    </style>
  </defs>`;
}

function finish() { return '</svg>\n'; }

function rect(x, y, w, h, r = 28, fill = C.white, stroke = 'none', extra = '') {
  return `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${r}" fill="${fill}" stroke="${stroke}" ${extra}/>`;
}

function text(x, y, value, cls = 'body', anchor = 'start', extra = '') {
  return `<text x="${x}" y="${y}" class="${cls}" text-anchor="${anchor}" ${extra}>${esc(value)}</text>`;
}

function multiline(x, y, lines, cls = 'body', gap = 34, anchor = 'start', extra = '') {
  return `<text x="${x}" y="${y}" class="${cls}" text-anchor="${anchor}" ${extra}>${lines.map((line, i) => `<tspan x="${x}" dy="${i === 0 ? 0 : gap}">${esc(line)}</tspan>`).join('')}</text>`;
}

function pill(x, y, w, label, fill = C.teal3, color = C.teal) {
  return `${rect(x, y, w, 48, 24, fill)}<text x="${x + w / 2}" y="${y + 31}" font-family="${font}" font-size="18" font-weight="700" text-anchor="middle" fill="${color}">${esc(label)}</text>`;
}

function numberDot(cx, cy, n) {
  return `<circle cx="${cx}" cy="${cy}" r="28" fill="${C.ink}"/><text x="${cx}" y="${cy + 8}" font-family="${font}" font-size="24" font-weight="800" fill="#fff" text-anchor="middle">${n}</text>`;
}

function arrow(x1, y1, x2, y2, color = C.teal2) {
  return `<path d="M${x1} ${y1} H${x2 - 18}" fill="none" stroke="${color}" stroke-width="5" stroke-linecap="round"/><path d="M${x2 - 28} ${y2 - 10} L${x2 - 16} ${y2} L${x2 - 28} ${y2 + 10}" fill="none" stroke="${color}" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>`;
}

function save(name, content) {
  const target = path.join(out, name);
  fs.writeFileSync(target, content);
  console.log(target);
}

const mascot = dataUri('xiaozai-mascot.png', 'image/png');

// 01 · README hero
{
  const w = 1600, h = 900;
  let s = svgStart(w, h, '此在 Current 产品主视觉', '从情绪表达、空间推荐到真实行动与反馈闭环。');
  s += rect(0, 0, w, h, 0, 'url(#paperGlow)');
  s += `<circle cx="1420" cy="80" r="240" fill="${C.orange2}" opacity=".46"/><circle cx="1300" cy="740" r="330" fill="${C.teal3}" opacity=".62"/>`;
  s += text(92, 82, '此在 · CURRENT', 'eyebrow');
  s += multiline(92, 200, ['从情绪', '到行动'], 'title', 86);
  s += text(96, 405, '一个持续陪伴的情绪空间 Agent', 'subtitle');
  s += multiline(96, 468, ['当你不知道该去哪里时，小在先理解你此刻的状态，', '再把感受变成一个真实、可到达、可反馈的空间行动。'], 'body', 38);
  s += pill(96, 570, 130, '听懂你');
  s += pill(242, 570, 150, '推荐空间');
  s += pill(408, 570, 150, '陪你行动');
  s += pill(574, 570, 150, '越用越懂');
  s += rect(96, 658, 550, 88, 26, C.ink, 'none', 'filter="url(#softShadow)"');
  s += `<text x="132" y="710" font-family="${font}" font-size="23" font-weight="700" fill="#fff">在线体验</text>`;
  s += `<text x="286" y="710" font-family="${font}" font-size="22" fill="#DDECE9">ssai-current.vercel.app</text>`;
  s += `<path d="M1000 580 C1140 500 1240 400 1360 240" fill="none" stroke="${C.teal2}" stroke-width="7" stroke-linecap="round" stroke-dasharray="10 20"/><circle cx="1000" cy="580" r="15" fill="${C.orange}"/><path d="M1360 214 c-34 0-60 25-60 58 0 46 60 101 60 101s60-55 60-101c0-33-26-58-60-58z" fill="${C.teal}"/><circle cx="1360" cy="272" r="19" fill="#fff"/>`;
  s += `<image href="${mascot}" x="855" y="75" width="600" height="600" preserveAspectRatio="xMidYMid meet"/>`;
  s += rect(938, 672, 540, 126, 30, 'rgba(255,255,255,.82)', C.line, 'filter="url(#softShadow)"');
  s += text(982, 720, '真实地图候选 · 可解释推荐', 'label');
  s += text(982, 760, '到访反馈 · 私密足迹 · 空间画像', 'body');
  s += text(92, 846, '不是替你做决定，而是陪你走进真实世界。', 'body');
  s += text(1508, 846, 'README HERO · 01', 'small', 'end');
  s += finish();
  save('01-product-hero.svg', s);
}

// 03 · Five-step journey
{
  const w = 1800, h = 760;
  const steps = [
    ['表达此刻状态', '自然语言或快速选择', '用户'],
    ['理解与安全判断', 'NeedState + 风险分流', 'Agent'],
    ['推荐真实空间', '地图候选 + 可解释排序', '地图 × 规则'],
    ['到达、体验、反馈', '把建议变成真实行动', '用户'],
    ['形成空间画像', '在证据门槛后保守更新', '数据库'],
  ];
  let s = svgStart(w, h, '五步用户旅程', '从表达此刻状态到形成更可信的空间画像。');
  s += rect(0, 0, w, h, 0, 'url(#paperGlow)');
  s += text(70, 72, '03 · USER JOURNEY', 'eyebrow');
  s += text(70, 148, '从一句感受，到一次真实行动', 'title');
  s += text(72, 198, '闭环不是“给建议”，而是让每一次到访都成为下一次推荐的证据。', 'body');
  steps.forEach((st, i) => {
    const x = 54 + i * 348;
    const y = 268;
    s += rect(x, y, 310, 365, 34, C.white, C.line, 'filter="url(#softShadow)"');
    s += numberDot(x + 48, y + 48, i + 1);
    s += pill(x + 142, y + 28, 142, st[2], i === 1 ? C.orange2 : C.teal3, i === 1 ? C.orange : C.teal);
    const icons = ['“…”', '◇', '⌖', '✓', '◎'];
    s += `<text x="${x + 155}" y="${y + 170}" font-family="${font}" font-size="74" font-weight="800" text-anchor="middle" fill="${i === 1 ? C.orange : C.teal}">${icons[i]}</text>`;
    s += text(x + 155, y + 238, st[0], 'cardTitle', 'middle');
    s += text(x + 155, y + 286, st[1], 'small', 'middle');
    if (i < steps.length - 1) s += arrow(x + 312, y + 184, x + 348, y + 184);
  });
  s += pill(70, 672, 214, '模型负责理解', C.orange2, C.orange);
  s += pill(298, 672, 214, '规则负责边界');
  s += pill(526, 672, 214, '地图负责现实');
  s += pill(754, 672, 214, '用户保留选择');
  s += pill(982, 672, 272, '数据库只记结构化证据');
  s += text(1730, 706, 'CURRENT · 2026', 'small', 'end');
  s += finish();
  save('03-five-step-journey.svg', s);
}

// 04 · Three real screenshots
{
  const w = 1800, h = 980;
  const shots = [
    { file: '04-input-raw.jpg', title: '1 · 表达', sub: '用自然语言说出此刻的状态', accent: C.teal },
    { file: '04-recommendation-raw.jpg', title: '2 · 推荐', sub: '获得真实可达且可解释的空间', accent: C.orange },
    { file: '04-feedback-raw.jpg', title: '3 · 反馈', sub: '记录变化，形成下一次推荐证据', accent: C.green },
  ];
  let s = svgStart(w, h, '真实产品流程', '线上产品的输入、推荐与到访反馈三个真实页面。');
  s += rect(0, 0, w, h, 0, 'url(#paperGlow)');
  s += text(70, 72, '04 · REAL PRODUCT FLOW', 'eyebrow');
  s += text(70, 144, '不是概念图：这是可以实际走通的产品闭环', 'title');
  s += text(72, 194, '线上版本实测 · 北京亮马桥公开地点 · 不使用私人定位', 'body');
  shots.forEach((shot, i) => {
    const x = 132 + i * 548;
    const y = 254;
    const clipId = `phoneClip${i}`;
    s += `<defs><clipPath id="${clipId}"><rect x="${x + 24}" y="${y + 46}" width="356" height="632" rx="34"/></clipPath></defs>`;
    s += rect(x, y, 404, 718, 58, '#0B1719', '#233C40', 'filter="url(#shadow)"');
    s += rect(x + 14, y + 16, 376, 686, 46, '#F4F6F5');
    // IAB screenshots are captured at half scale with the useful page in the left half.
    s += `<g clip-path="url(#${clipId})"><image href="${dataUri(shot.file, 'image/jpeg')}" x="${x + 24}" y="${y + 46}" width="712" height="1544" preserveAspectRatio="none"/></g>`;
    s += `<rect x="${x + 147}" y="${y + 25}" width="110" height="24" rx="12" fill="#0B1719"/>`;
    s += text(x + 202, y + 760, shot.title, 'cardTitle', 'middle');
    s += text(x + 202, y + 802, shot.sub, 'small', 'middle');
    if (i < 2) s += `<path d="M${x + 438} ${y + 360} H${x + 498}" stroke="${C.teal2}" stroke-width="6" stroke-linecap="round"/><path d="M${x + 482} ${y + 344} l18 16 -18 16" fill="none" stroke="${C.teal2}" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"/>`;
  });
  s += finish();
  save('04-real-product-flow.svg', s);
}

// 05 · Agent workflow
{
  const w = 1800, h = 980;
  const stages = [
    ['表达', '用户', '原话 / 快速选择'], ['安全判断', '规则', '危机信号先分流'], ['结构化理解', '模型', 'NeedState'],
    ['地图候选', '地图', 'POI / 路线 / 营业'], ['过滤与排序', '规则', '硬条件 + 确定性评分'],
    ['解释推荐', '模型', '为什么适合此刻'], ['用户纠错', '用户', '安静一点 / 近一点'],
    ['地图行动', '地图', '路线与出发'], ['到访反馈', '用户', '状态变化与因素'], ['空间画像', '数据库', '达标后保守更新'],
  ];
  let s = svgStart(w, h, 'Agent 工作流', '模型、规则、地图、用户与数据库在推荐闭环中的责任边界。');
  s += rect(0, 0, w, h, 0, 'url(#paperGlow)');
  s += text(70, 72, '05 · AGENT WORKFLOW', 'eyebrow');
  s += text(70, 145, '小在如何把“我不知道去哪”变成一次行动', 'title');
  s += text(72, 196, '模型负责理解与表达；规则守住边界；地图提供现实；用户始终拥有决定权。', 'body');
  stages.forEach((st, i) => {
    const row = i < 5 ? 0 : 1;
    const col = i % 5;
    const x = 70 + col * 344;
    const y = 270 + row * 286;
    const ownerColor = { '用户': C.green, '规则': C.orange, '模型': C.teal, '地图': '#376B9A', '数据库': '#725F9A' }[st[1]];
    s += rect(x, y, 292, 204, 30, C.white, C.line, 'filter="url(#softShadow)"');
    s += `<circle cx="${x + 38}" cy="${y + 38}" r="20" fill="${ownerColor}"/><text x="${x + 38}" y="${y + 45}" font-family="${font}" font-size="18" font-weight="800" fill="#fff" text-anchor="middle">${i + 1}</text>`;
    s += `<text x="${x + 266}" y="${y + 45}" font-family="${font}" font-size="16" font-weight="800" fill="${ownerColor}" text-anchor="end">${esc(st[1])}</text>`;
    s += text(x + 26, y + 104, st[0], 'cardTitle');
    s += text(x + 26, y + 151, st[2], 'small');
    if (col < 4) s += arrow(x + 294, y + 102, x + 342, y + 102);
  });
  s += `<path d="M1638 474 C1690 474 1690 555 1638 555" fill="none" stroke="${C.teal2}" stroke-width="5" stroke-linecap="round"/>`;
  s += rect(70, 858, 1660, 72, 24, C.ink);
  s += `<text x="110" y="904" font-family="${font}" font-size="22" font-weight="700" fill="#fff">底线：</text><text x="210" y="904" font-family="${font}" font-size="21" fill="#DDECE9">高风险表达不进入地点推荐；模型不能虚构地点；地图与用户反馈可以否决模型。</text>`;
  s += finish();
  save('05-agent-workflow.svg', s);
}

// 06 · Architecture
{
  const w = 1800, h = 1080;
  let s = svgStart(w, h, '系统架构图', '客户端、FastAPI、模型、地图、语音、数据与跨设备服务的真实架构。');
  s += rect(0, 0, w, h, 0, 'url(#paperGlow)');
  s += text(70, 72, '06 · SYSTEM ARCHITECTURE', 'eyebrow');
  s += text(70, 145, '当前可运行系统，以及清楚的降级边界', 'title');
  s += text(72, 195, 'PWA 前端 + FastAPI 后端 + 可替换服务提供方；任何单点失败都应回到可操作状态。', 'body');

  const layer = (y, hgt, label, color) => {
    s += rect(50, y, 1700, hgt, 34, '#FFFFFFCC', C.line, 'filter="url(#softShadow)"');
    s += `<rect x="50" y="${y}" width="190" height="${hgt}" rx="34" fill="${color}"/><text x="145" y="${y + hgt / 2 + 8}" font-family="${font}" font-size="25" font-weight="800" fill="#fff" text-anchor="middle">${label}</text>`;
  };
  layer(250, 150, '体验层', C.teal);
  layer(430, 210, '服务层', C.ink);
  layer(670, 160, '能力层', C.orange);
  layer(860, 150, '数据层', C.green);

  const box = (x, y, w0, h0, title, sub, fill = C.paper) => {
    s += rect(x, y, w0, h0, 22, fill, C.line);
    s += text(x + 20, y + 42, title, 'label');
    s += text(x + 20, y + 76, sub, 'tiny');
  };
  box(270, 278, 250, 94, '手机 Web / PWA', '输入、推荐、反馈、足迹');
  box(545, 278, 250, 94, '桌面 / 伴侣网页', '6 位码接续、受限控制');
  box(820, 278, 250, 94, 'Swift HRV 实验', '本地心率变异性探索');
  box(1095, 278, 250, 94, 'Service Worker', '离线外壳与弱网兜底');
  box(1370, 278, 340, 94, 'current-client.js', '状态机、隐私与 UI 协调');

  box(270, 462, 300, 146, 'FastAPI', '接口编排 · 限流 · CORS');
  box(595, 462, 300, 146, 'Interpretation', '结构化理解与安全分流');
  box(920, 462, 300, 146, 'Recommender', '硬过滤 + 确定性排序');
  box(1245, 462, 220, 146, 'Relay', '跨设备结构化接续');
  box(1490, 462, 220, 146, 'Community', '共创审核与公共信号');

  box(270, 700, 300, 100, 'OpenAI-compatible LLM', '解释与结构化生成', C.orange2);
  box(595, 700, 300, 100, '高德地图', 'POI · 路线 · 地理编码', C.orange2);
  box(920, 700, 300, 100, '浏览器 / 腾讯 ASR', '语音转文字，可降级打字', C.orange2);
  box(1245, 700, 220, 100, '规则引擎', '安全与事实边界', C.orange2);
  box(1490, 700, 220, 100, '缓存与重试', '提供方抖动降级', C.orange2);

  box(270, 890, 360, 90, 'PostgreSQL / Neon', '结构化会话、空间与反馈', '#E3EFE8');
  box(660, 890, 330, 90, 'Space Profiles', '满足样本门槛再更新', '#E3EFE8');
  box(1020, 890, 330, 90, '本地私密记录', '倾诉原文、笔记、媒体', '#E3EFE8');
  box(1380, 890, 330, 90, '审计与健康检查', '可观测性与上线验收', '#E3EFE8');

  s += `<path d="M390 400 V430 M720 400 V430 M1045 400 V430 M1405 400 V430 M420 640 V670 M745 640 V670 M1070 640 V670 M1355 640 V670 M1600 640 V670 M420 830 V860 M825 830 V860 M1185 830 V860 M1600 830 V860" stroke="${C.teal2}" stroke-width="4" stroke-dasharray="8 9"/>`;
  s += text(1705, 1040, '实线能力：当前代码可运行 · 虚线：提供方与降级边界', 'small', 'end');
  s += finish();
  save('06-system-architecture.svg', s);
}

// 07 · Recommendation and geospatial flow
{
  const w = 1800, h = 980;
  let s = svgStart(w, h, '推荐与地理数据流', '从用户原话到地图候选、确定性评分、到访证据和空间画像。');
  s += rect(0, 0, w, h, 0, 'url(#paperGlow)');
  s += text(70, 72, '07 · RECOMMENDATION & GEO DATA', 'eyebrow');
  s += text(70, 145, '推荐不是一句模型答案，而是一条可审计的数据链', 'title');
  s += text(72, 195, '先把不可去的地方排除，再在真实候选里解释为什么适合“此刻”。', 'body');

  const nodes = [
    [70, 280, 230, '用户原话', '自然语言'], [330, 280, 230, 'NeedState', '需求与能量'], [590, 280, 230, '地图候选', 'POI / 路线'],
    [850, 280, 230, '硬条件过滤', '距离 / 营业 / 可达'], [1110, 280, 230, '确定性评分', '五项基础权重'], [1370, 280, 360, '1 主推 + 2 备选', '理由与行动成本'],
  ];
  nodes.forEach((n, i) => {
    s += rect(n[0], n[1], n[2], 160, 28, C.white, C.line, 'filter="url(#softShadow)"');
    s += numberDot(n[0] + 40, n[1] + 42, i + 1);
    s += text(n[0] + 24, n[1] + 104, n[3], 'cardTitle');
    s += text(n[0] + 24, n[1] + 138, n[4], 'small');
    if (i < nodes.length - 1) s += arrow(n[0] + n[2], n[1] + 80, nodes[i + 1][0], n[1] + 80);
  });

  s += rect(70, 500, 1010, 250, 34, C.ink);
  s += `<text x="110" y="550" font-family="${font}" font-size="26" font-weight="800" fill="#fff">基础评分权重</text>`;
  const weights = [['需求匹配',45,C.teal2],['精力适配',20,'#B7D8CE'],['出行成本',15,C.orange2],['社交强度',10,'#D8CFE9'],['预算',10,'#E7DFBF']];
  let wx = 110;
  weights.forEach(([label, val, color]) => {
    const bw = val * 8.8;
    s += `<rect x="${wx}" y="590" width="${bw}" height="62" rx="16" fill="${color}"/><text x="${wx + bw / 2}" y="629" font-family="${font}" font-size="18" font-weight="800" fill="${C.ink}" text-anchor="middle">${val}%</text><text x="${wx + bw / 2}" y="678" font-family="${font}" font-size="15" font-weight="700" fill="#DDECE9" text-anchor="middle">${label}</text>`;
    wx += bw + 8;
  });
  s += `<text x="110" y="724" font-family="${font}" font-size="20" fill="#DDECE9">若用户明确指定活动：活动匹配 65% + 基础评分 35%</text>`;

  s += rect(1110, 500, 620, 250, 34, C.white, C.line, 'filter="url(#softShadow)"');
  s += text(1150, 550, '反馈如何改变推荐？', 'cardTitle');
  s += multiline(1150, 600, ['到访证据 → 满足最小样本量 5', '→ 质量与新鲜度检查', '→ 空间画像最多修正 45%'], 'body', 42);
  s += pill(1150, 690, 240, '证据只降不升', C.orange2, C.orange);
  s += pill(1410, 690, 270, '避免少量反馈带偏');

  s += `<path d="M1548 750 C1548 850 850 855 850 754" fill="none" stroke="${C.teal}" stroke-width="5" stroke-dasharray="10 12"/><path d="M835 778 l15 -24 15 24" fill="none" stroke="${C.teal}" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>`;
  s += text(900, 842, '新的可信证据回到下一次排序，但不会覆盖硬条件', 'label', 'middle');
  s += finish();
  save('07-recommendation-geo-flow.svg', s);
}

// 08 · Privacy boundary
{
  const w = 1600, h = 980;
  let s = svgStart(w, h, '隐私数据边界', '设备内数据、结构化上传数据与达到门槛后可公开数据的边界。');
  s += rect(0, 0, w, h, 0, 'url(#paperGlow)');
  s += text(70, 72, '08 · PRIVACY BOUNDARY', 'eyebrow');
  s += text(70, 145, '让系统更懂你，不等于让所有数据离开设备', 'title');
  s += text(72, 195, '只传递完成推荐闭环所需的最少结构化信息。', 'body');

  s += rect(110, 270, 1380, 610, 50, '#FFFFFFCC', C.line, 'filter="url(#shadow)"');
  s += rect(170, 330, 1260, 490, 44, C.teal3, C.teal2);
  s += rect(250, 410, 1100, 330, 40, C.ink);
  s += text(150, 314, '达到门槛后可公开', 'cardTitle');
  s += text(210, 374, '可以结构化上传', 'cardTitle');
  s += `<text x="290" y="458" font-family="${font}" font-size="28" font-weight="800" fill="#fff">只在设备上</text>`;

  const inner = ['原始语音', '倾诉原文', '实时坐标', '私密笔记', '照片与媒体'];
  inner.forEach((v, i) => s += pill(290 + (i % 3) * 310, 502 + Math.floor(i / 3) * 76, 270, v, '#27484C', '#fff'));
  s += `<text x="290" y="696" font-family="${font}" font-size="19" fill="#DDECE9">默认不上传，不用于公开训练，不跨设备同步。</text>`;

  const middle = ['需求状态', '推荐选择', '围栏结论', '停留分钟', '反馈因素'];
  middle.forEach((v, i) => s += pill(270 + i * 218, 760, 190, v, C.white, C.teal));
  s += text(246, 855, '经审核共创 · 匿名空间画像 · 最小样本量后的公共信号', 'body');

  s += rect(1060, 250, 430, 118, 30, C.orange2, 'none', 'filter="url(#softShadow)"');
  s += text(1092, 295, '三条执行原则', 'label');
  s += multiline(1092, 330, ['围栏在浏览器计算 · 服务端证据只降不升 · 私密记录可删除'], 'small');
  s += finish();
  save('08-privacy-boundary.svg', s);
}

// 09 · Phone and glasses companion prototype
{
  const w = 1600, h = 900;
  const companion = dataUri('09-glasses-companion-raw.jpg', 'image/jpeg');
  let s = svgStart(w, h, '手机与智能眼镜伴侣原型', '当前跨设备网页伴侣原型以及下一阶段的硬件接入边界。');
  s += rect(0, 0, w, h, 0, 'url(#paperGlow)');
  s += text(70, 72, '09 · CROSS-DEVICE COMPANION', 'eyebrow');
  s += text(70, 145, '手机完成核心流程，伴侣界面轻量接续', 'title');
  s += text(72, 195, '当前是可运行的跨设备网页原型；真实眼镜 SDK、AR 导航与视觉识别属于下一阶段。', 'body');

  // phone
  s += rect(105, 255, 380, 570, 54, '#0B1719', '#233C40', 'filter="url(#shadow)"');
  s += rect(119, 270, 352, 540, 42, '#F6F8F7');
  s += `<rect x="220" y="280" width="148" height="26" rx="13" fill="#0B1719"/>`;
  s += text(152, 350, '手机端', 'cardTitle');
  s += multiline(152, 405, ['表达与理解', '查看推荐', '确认出发', '记录反馈与足迹'], 'body', 52);
  s += rect(150, 640, 290, 92, 24, C.ink);
  s += `<text x="295" y="696" font-family="${font}" font-size="22" font-weight="800" fill="#fff" text-anchor="middle">核心体验独立可用</text>`;

  s += `<path d="M520 518 H695" stroke="${C.teal2}" stroke-width="7" stroke-dasharray="10 12"/><path d="M675 500 l22 18 -22 18" fill="none" stroke="${C.teal2}" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/>`;
  s += pill(535, 450, 145, '6 位临时码');

  // companion screen crop
  s += rect(725, 255, 430, 570, 44, '#243235', '#243235', 'filter="url(#shadow)"');
  s += rect(741, 272, 398, 536, 32, '#F6F8F7');
  s += `<defs><clipPath id="companionClip"><rect x="741" y="272" width="398" height="536" rx="32"/></clipPath></defs>`;
  s += `<g clip-path="url(#companionClip)"><image href="${companion}" x="741" y="272" width="796" height="1724" preserveAspectRatio="none"/></g>`;

  s += rect(1200, 255, 330, 250, 34, '#E3EFE8', C.line);
  s += text(1236, 305, '当前已实现', 'cardTitle');
  s += multiline(1236, 355, ['结构化进度同步', '场景模式切换', '受限推荐操作', '12 小时临时会话'], 'body', 43);
  s += rect(1200, 535, 330, 290, 34, C.orange2, 'none');
  s += text(1236, 585, '下一阶段', 'cardTitle');
  s += multiline(1236, 635, ['真实眼镜 SDK', '抬头导航', '视觉识别', '语音与环境感知'], 'body', 45);
  s += text(1236, 790, '明确标注：尚未完成', 'label');
  s += finish();
  save('09-cross-device-companion.svg', s);
}

// 10 · Roadmap
{
  const w = 1800, h = 1000;
  const phases = [
    ['现在', '可运行闭环', ['推荐与反馈闭环', '北京 / 深圳地图候选', '跨设备网页伴侣', '安全与隐私边界']],
    ['深圳提交', '验证与打磨', ['真实移动端验收', '补齐深圳场所证据', 'README / 路演材料', '用户测试与缺陷收口']],
    ['下一阶段', '提高可信度', ['单次模型调用提速', '更精确城市反查', '共创审核工作台', '眼镜 SDK 技术验证']],
    ['长期', '形成网络效应', ['多城市空间画像', '匿名共创社区', '空间伙伴与场所合作', '情绪地理技术团队']],
  ];
  let s = svgStart(w, h, '工程产品市场路线图', '当前、深圳提交、下一阶段和长期的工程、产品与验证目标。');
  s += rect(0, 0, w, h, 0, 'url(#paperGlow)');
  s += text(70, 72, '10 · ROADMAP', 'eyebrow');
  s += text(70, 145, '工程 × 产品 × 验证：知道什么已经完成，也知道下一步为何重要', 'title');
  s += text(72, 195, '路线图中的未来能力不会被写成当前能力。', 'body');
  phases.forEach((p, i) => {
    const x = 56 + i * 432;
    const accent = [C.teal, C.orange, '#557E96', '#725F9A'][i];
    s += rect(x, 260, 400, 640, 38, C.white, C.line, 'filter="url(#softShadow)"');
    s += `<rect x="${x}" y="260" width="400" height="112" rx="38" fill="${accent}"/><rect x="${x}" y="330" width="400" height="42" fill="${accent}"/>`;
    s += `<text x="${x + 34}" y="310" font-family="${font}" font-size="24" font-weight="800" fill="#fff">${esc(p[0])}</text>`;
    s += `<text x="${x + 34}" y="350" font-family="${font}" font-size="18" fill="#fff" opacity=".84">${esc(p[1])}</text>`;
    p[2].forEach((item, j) => {
      const yy = 430 + j * 108;
      s += `<circle cx="${x + 48}" cy="${yy - 4}" r="16" fill="${accent}" opacity="${1 - j * .12}"/>`;
      s += `<path d="M${x + 41} ${yy - 4} l5 6 10 -13" fill="none" stroke="#fff" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>`;
      s += text(x + 84, yy + 4, item, 'body');
    });
    if (i < 3) s += arrow(x + 400, 580, x + 432, 580, accent);
  });
  s += text(70, 956, '原则：先验证真实行动，再扩大城市与硬件；先建立证据，再建立社区。', 'label');
  s += finish();
  save('10-roadmap.svg', s);
}

// 11 · Test evidence
{
  const w = 1600, h = 900;
  let s = svgStart(w, h, '测试证据卡', '后端、前端与总测试数量，以及自动化测试的覆盖边界。');
  s += rect(0, 0, w, h, 0, 'url(#paperGlow)');
  s += text(70, 72, '11 · VERIFICATION EVIDENCE', 'eyebrow');
  s += text(70, 145, '提交前，不靠“应该可以”', 'title');
  s += text(72, 195, '以自动化测试保护推荐、安全、语音降级、地图与跨设备逻辑。', 'body');

  const stats = [['208', '后端测试通过'], ['67', '前端策略测试通过'], ['275', '总计通过']];
  stats.forEach((st, i) => {
    const x = 70 + i * 470;
    const fill = i === 2 ? C.ink : C.white;
    s += rect(x, 275, 420, 250, 38, fill, i === 2 ? 'none' : C.line, 'filter="url(#shadow)"');
    s += `<text x="${x + 210}" y="410" font-family="${font}" font-size="102" font-weight="850" text-anchor="middle" fill="${i === 2 ? '#fff' : C.teal}">${st[0]}</text>`;
    s += `<text x="${x + 210}" y="470" font-family="${font}" font-size="24" font-weight="700" text-anchor="middle" fill="${i === 2 ? '#DDECE9' : C.ink}">${st[1]}</text>`;
  });

  s += rect(70, 585, 880, 230, 34, C.white, C.line);
  s += text(108, 635, '覆盖范围', 'cardTitle');
  const domains = ['安全分流', '确定性排序', '地图与地理编码', '反馈画像', '语音降级', '跨设备接续', '共创审核', '缓存与重试'];
  domains.forEach((d, i) => s += pill(108 + (i % 4) * 196, 674 + Math.floor(i / 4) * 62, 178, d));

  s += rect(990, 585, 540, 230, 34, C.orange2, 'none');
  s += text(1030, 635, '最后验证', 'cardTitle');
  s += text(1030, 683, '2026-10-04 · commit 0202863', 'body');
  s += multiline(1030, 730, ['自动化不替代真机语音、定位与', '国内移动网络访问验证。'], 'small', 32);
  s += finish();
  save('11-test-evidence.svg', s);
}

// 12 · Branded QR wrapper. The QR PNG is generated separately by CoreImage.
if (fs.existsSync(path.join(out, '12-experience-qr.png'))) {
  const qr = dataUri('12-experience-qr.png', 'image/png');
  const w = 1200, h = 1200;
  let s = svgStart(w, h, '在线体验二维码', '扫描二维码打开此在 Current 线上体验。');
  s += rect(0, 0, w, h, 0, 'url(#paperGlow)');
  s += text(80, 92, '12 · TRY CURRENT', 'eyebrow');
  s += text(80, 180, '现在，去一个', 'title');
  s += text(80, 254, '更适合此刻的地方', 'title');
  s += rect(160, 338, 880, 690, 60, C.white, C.line, 'filter="url(#shadow)"');
  s += `<image href="${qr}" x="285" y="385" width="630" height="630" image-rendering="pixelated"/>`;
  s += pill(376, 1052, 448, 'ssai-current.vercel.app', C.ink, '#fff');
  s += `<image href="${mascot}" x="900" y="36" width="240" height="240"/>`;
  s += finish();
  save('12-experience-qr-card.svg', s);
}

// README refresh · the public README intentionally uses only these three
// quieter visuals. The fuller submission graphics above remain available for
// decks and judging materials, but no longer crowd the main project page.

// A · Real product screens, with no editorial headline or explanatory copy.
{
  const w = 1500, h = 820;
  const shots = [
    { file: '04-input-raw.jpg', label: '表达' },
    { file: '04-recommendation-raw.jpg', label: '推荐' },
    { file: '04-feedback-raw.jpg', label: '反馈' },
  ];
  let s = svgStart(w, h, '真实产品界面', '当前线上版本的表达、推荐和反馈页面。');
  s += rect(0, 0, w, h, 0, C.paper);
  shots.forEach((shot, i) => {
    const x = 132 + i * 456;
    const y = 42;
    const clipId = `simplePhoneClip${i}`;
    s += `<defs><clipPath id="${clipId}"><rect x="${x + 20}" y="${y + 42}" width="290" height="626" rx="30"/></clipPath></defs>`;
    s += rect(x, y, 330, 704, 48, '#0B1719', '#233C40', 'filter="url(#softShadow)"');
    s += rect(x + 12, y + 14, 306, 674, 38, '#F4F6F5');
    s += `<g clip-path="url(#${clipId})"><image href="${dataUri(shot.file, 'image/jpeg')}" x="${x + 20}" y="${y + 42}" width="580" height="1256" preserveAspectRatio="none"/></g>`;
    s += `<rect x="${x + 122}" y="${y + 22}" width="86" height="19" rx="10" fill="#0B1719"/>`;
    s += text(x + 165, 790, shot.label, 'label', 'middle');
  });
  s += finish();
  save('product-flow-simple.svg', s);
}

// B · Recommendation pipeline. Labels only; the explanation lives in prose.
{
  const w = 1500, h = 360;
  const stages = [
    ['此刻的表达', '用户'],
    ['NeedState', '模型'],
    ['真实 POI', '地图'],
    ['过滤与排序', '规则'],
    ['1 + 2 个选择', '用户'],
  ];
  let s = svgStart(w, h, '推荐流程', '表达经过结构化理解、地图候选和规则排序，最后回到用户选择。');
  s += rect(0, 0, w, h, 0, C.paper);
  stages.forEach((stage, i) => {
    const x = 54 + i * 292;
    const fill = i === 4 ? C.ink : C.white;
    s += rect(x, 82, 238, 156, 28, fill, i === 4 ? 'none' : C.line, 'filter="url(#softShadow)"');
    s += `<circle cx="${x + 34}" cy="116" r="8" fill="${i === 1 ? C.orange : C.teal}"/>`;
    s += `<text x="${x + 119}" y="158" font-family="${font}" font-size="25" font-weight="760" text-anchor="middle" fill="${i === 4 ? '#fff' : C.ink}">${esc(stage[0])}</text>`;
    s += `<text x="${x + 119}" y="199" font-family="${font}" font-size="16" text-anchor="middle" fill="${i === 4 ? C.teal3 : C.muted}">${esc(stage[1])}</text>`;
    if (i < stages.length - 1) s += arrow(x + 240, 160, x + 290, 160);
  });
  s += text(750, 302, '地点由地图提供，最终选择属于用户', 'small', 'middle');
  s += finish();
  save('recommendation-simple.svg', s);
}

// C · Current architecture, stripped to the dependencies a reader needs.
{
  const w = 1500, h = 610;
  let s = svgStart(w, h, 'Current 系统结构', 'Web 客户端、Current API、外部能力与数据存储。');
  s += rect(0, 0, w, h, 0, C.paper);

  s += rect(70, 205, 270, 170, 30, C.white, C.line, 'filter="url(#softShadow)"');
  s += text(205, 276, 'Web / PWA', 'cardTitle', 'middle');
  s += text(205, 322, '输入 · 推荐 · 反馈', 'small', 'middle');

  s += rect(485, 170, 330, 240, 34, C.ink, 'none', 'filter="url(#shadow)"');
  s += `<text x="650" y="258" font-family="${font}" font-size="30" font-weight="800" text-anchor="middle" fill="#fff">Current API</text>`;
  s += `<text x="650" y="308" font-family="${font}" font-size="18" text-anchor="middle" fill="${C.teal3}">理解 · 安全 · 排序 · 中继</text>`;

  const services = [
    ['语言模型', '结构化理解'],
    ['高德地图', 'POI 与路线'],
    ['语音服务', 'ASR'],
  ];
  services.forEach((service, i) => {
    const y = 70 + i * 150;
    s += rect(960, y, 250, 108, 24, C.white, C.line);
    s += text(1085, y + 47, service[0], 'label', 'middle');
    s += text(1085, y + 79, service[1], 'tiny', 'middle');
    s += `<path d="M815 290 C880 290 880 ${y + 54} 960 ${y + 54}" fill="none" stroke="${C.teal2}" stroke-width="4"/>`;
  });

  s += rect(960, 510, 250, 70, 22, '#E3EFE8', C.line);
  s += text(1085, 553, 'PostgreSQL / Neon', 'label', 'middle');
  s += `<path d="M650 410 V545 H960" fill="none" stroke="${C.teal2}" stroke-width="4"/>`;
  s += arrow(342, 290, 482, 290);

  s += rect(1280, 175, 150, 240, 26, C.orange2, 'none');
  s += multiline(1355, 242, ['缺少外部服务时', '明确降级', '不伪装成功'], 'small', 40, 'middle');
  s += finish();
  save('architecture-simple.svg', s);
}
