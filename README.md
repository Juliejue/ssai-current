# 此在 / Current

在说不清的时刻，帮你找到此刻适合你的空间。

基于 AI 与真实到访反馈的**情绪—空间匹配平台**。SSAI 黑客松项目。

> **此在** = 海德格尔 Dasein，"在此处存在"。不问你是什么样的人，只问你此刻在哪儿。
> **Current** 一词三义：此刻的 / 电流（HRV、皮电）/ 水流。

---

## 怎么跑

原视觉原型仍可直接双击打开；AI 自然语言、语音和闭环事件需要同时运行后端。

```
双击 此在-current-原型.html
```

### AI 后端开发

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt pytest
.venv/bin/uvicorn backend_app.main:app --port 8001
python3 -m http.server 8000
```

然后打开 `http://127.0.0.1:8000/此在-current-原型.html`。

环境变量参照 `.env.example`：

- 未配置大模型时，使用可测试的本地规则解析，不影响开发。
- 配置 OpenAI-compatible 模型后，模型只负责把自然语言转换为受约束的需求结构。
- 配置腾讯云 ASR 后，音频由浏览器直传腾讯；Current 后端只生成两分钟有效的签名。
- 配置高德 Web 服务 Key 后，且地点完成过人工核对时，用户主动授权位置后会使用真实步行距离和时间；否则自动回退到原型估算。
- 配置 PostgreSQL 后，推荐决策、行为事件和到访结果进入闭环数据库；不配置时只写隐私安全的运行日志。
- 原始语音和用户倾诉原文均不写入数据库或分析事件。

运行检查：

```bash
.venv/bin/pytest -q
node --check current-client.js
node scripts/extract_place_data.mjs
```

### 地图地点核对（不自动认领）

原型里的地点名称不能直接当作可靠地图身份。先把 `AMAP_WEB_SERVICE_KEY` 放进本地 `.env`（不要提交），再生成候选：

```bash
AMAP_WEB_SERVICE_KEY=你的服务端Key .venv/bin/python -m scripts.resolve_amap_places
```

候选写入被 Git 忽略的 `backend_app/data/amap_candidates.json`。人工核对名称、地址和坐标后，只把确定的一项写入 `backend_app/data/place_overrides.json`：

```json
{
  "places": {
    "wansheng": {
      "amap": {
        "provider_place_id": "高德POI ID",
        "longitude": 116.0,
        "latitude": 39.0,
        "verified_name": "地图中的正式名称",
        "address": "人工核对后的地址",
        "verification_status": "verified",
        "verified_at": "2026-09-05T00:00:00Z"
      }
    }
  }
}
```

代码不会自动采用搜索第一名；只有 `verification_status=verified` 才会用于路线和导航。

### 闭环数据库

Vercel 上建议从 Marketplace 连接 Neon，并给 `DATABASE_URL` 使用 pooled connection string。环境变量只配置在服务端，按 Development / Preview / Production 分开管理。首次连接后运行：

```bash
.venv/bin/python scripts/migrate.py
.venv/bin/python -m scripts.seed_places
```

数据库保存：结构化需求、推荐排名与得分、接受/拒绝/导航/到访状态、反馈分数和因素。数据库不保存：倾诉原文、原始语音、用户经纬度；私密反馈正文也不上传。

断网也能跑。手机上看用这个链接（私有，问 Julie 要）：
<https://claude.ai/code/artifact/d78298ab-65f6-4a87-9656-4e1be7a0516b>

完整闭环：情绪 → 需求发现 → 推荐（卡片／瀑布流）→ 地点详情 → 到访 → 30 秒反馈 → 情绪空间轨迹。

---

## 目录

```
此在-current-原型.html      主原型（~140KB，vanilla JS + hash 路由）
交接-背景说明.md            ⭐ 接手先读这个：完整上下文、已知故障、待办
brand/
  品牌手册.html             色板、标识规范、符号系统、语气规则、小在
  路演物料.html             主视觉、六种演示页型、海报、一页纸、社媒
  标识-A稿收敛.html         最终标识的四档对比与几何论证
  标识-四稿对比.html         最初的四个方向
  此在-路演模板.pptx        六种页型，Keynote / PowerPoint 可直接编辑
  svg/                     标识与小在的矢量（含四种表情、反白、icon）
  成品图/                   路演用的 7 张导出图
CurrentHRVDemo/            Swift / HealthKit HRV demo（Phase 2 入口）
```

---

## 三条硬边界

**会否决设计方案，不是价值观标语。**

1. **不诊断** —— 不给情绪贴标签，不暗示病理。可以说"你 7 次里有 5 次选了人不多"，不能说"你是高敏感人群"。
2. **不评判** —— 变化分数**负端不能用红**。情绪变差不是错误，只是这次没接住。
3. **不社交** —— 没有昵称、人脸、主页、评论、关注、私信。只有用户主动匿名贡献的记录会露出。

## 一条视觉规则

**冷色承担空间与时间，暖色只标记"你 / 此刻"。**
用色比例 70 底 / 22 墨 / 6 水青 / **2 赭**。一屏之内出现超过两处赭色，就是没改干净。

```
--paper #F0F3F2   --card #FFFFFF   --sunk #E8EDEC
--ink   #122A2E   --ink-dim #5A6E70   --ink-faint #8CA0A0
--water #1E6E72   流 · 空间 · 冷
--sun   #C4703C   此刻 · 你 · 唯一的暖
情绪色阶 −3…+3：#4E4B63 #6B687F #9694A5 #C3C9C7 #86ADA8 #4A8F8A #1E6E72
```

## 一条内容规则

**讲"你到了做什么"，不讲"这个地方是什么"。**
卡片标题是一个动作，地名降为副标题。没有评分、没有必去、没有氛围感，代价照实写。
`会看到什么` 这一行专门用来**替代照片** —— 小众场所没有合规图源，硬配图会错配。

---

## 待办

1. `ROUTES` 四条路线数据完整但 UI 没露出（小西天 citywalk / 鼓楼 / 三里屯 / 亮马河黄昏）。
2. 地点的距离与交通是估算值，需核对。
3. 福声唱片、火鬼 paro 在卡片模式进不了 top3（价值是"顺路""周二特价"这类上下文，标签体系表达不了）。瀑布流里能看到。
4. 密度原则待应用到：瀑布流卡片、反馈页（10 个影响因素 → 先显示 6 个 + 展开）、需求页（每组前 4 个 + 更多）。

细节和待办见 `交接-背景说明.md`。

---

## 注意

- 内含 **7 条真人原话**（群聊摘录，见各地点的 `quote` 字段）。已无人名与私人场景，但仍是他人原话——
  若当事人希望撤下，改成转述即可（搜索 `quote:` 定位）。
- 路演数字 `+2.4 / 1,205 份` 是**原型示例值**，上台必须说明是模拟数据。
- 物料里的二维码是占位图形，扫不出东西。
