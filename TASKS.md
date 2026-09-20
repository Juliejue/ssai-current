# 此在 / Current —— 工作指令书（单文件交接）

> 给 Claude Code / Cursor 等编码 Agent 的完整交接。
> **本文件自带全部代码**（附录 A / B / C），无需其他附件。
> 2026-09-20　｜　**截止：2026-10-04 23:59（北京时间）**

## ⚡ 开工顺序

1. 新建 `agent/current-agent.js`，复制**附录 A**
2. 新建 `api/read.js`，复制**附录 B**
3. 新建 `api/relay.js`，复制**附录 C**
4. 执行任务 1（提取真实词表）—— **这是所有后续工作的前提**

---

## 0. 参赛定位（决定一切的前提）

投稿 **GOSIM Spotlight Shenzhen 2026**，走 **选项 B：现有设备与跨设备系统**。

官方原话，逐条对照：

> **「Agent 能理解情境、调用工具并完成任务，而不是只在现有产品里增加一个聊天框。」**
> **「仅接受自研智能硬件或改造、整合现有设备的项目（含跨设备系统）。」**
> 选项 B 示例：「连接开源手表、智能眼镜、手机与电脑，让 Agent 跨设备接续任务。」

拆成三条硬指标，**缺一条就不合规**：

| # | 要求 | 我们的答案 |
|---|---|---|
| **A** | 理解情境 | 时间段、工作日夜里、设备角色、地理位置 —— 不问就知道 |
| **B** | 调用工具 | 地图深链、定位、系统分享 —— **Agent 自己决定调哪个** |
| **C** | 跨设备接续 | 手机说的话，桌面那块屏接住；出门前 / 路上 / 回来是同一条线 |

⚠️ **A 和 B 是所有项目的基础门槛，C 才是选项 B 的主张。**
「调用地图」= 工具调用，**不等于**跨设备。
材料与代码里这两个词不能混用，混一次评委就认为我们没想清楚。

### 产品单位

> **不是「一次推荐」，是「一次出门」。**

一次出门天然跨时间、跨设备、跨状态：
出门前说不清 → 路上在移动 → 到了现场 → 回来之后。

现有 App 在每个接缝处都断线：
地图不知道你为什么去，备忘录不知道你去了哪，情绪日记不知道你到底有没有好一点。

**小在的工作就是把这条线接住。** 跨设备因此不是功能，是产品形态的必然结果。

### 评分权重

**60% 产品价值与 AI 用户体验 ＋ 40% 实现与完成度**（原型可实际体验、系统实现稳定可信）。

主办方明确要淘汰「用户仍需主动打开应用、在不同应用间切换、面对固定菜单和页面，
Agent 更像一个附加功能」的产品。**我们现在恰好就是这一类。这是本次改造的全部动因。**

---

## 1. 仓库现状（已确认的事实）

仓库 `Juliejue/ssai-current`　部署 `ssai-current.vercel.app`

| 文件 | 说明 |
|---|---|
| `此在-current-原型.html` | **主原型，2249 行 / 136KB，单文件、vanilla JS + hash 路由、无框架无构建无后端无外部依赖** |
| `README.md` | 产品定义、三条硬边界、色板、待办 |
| `交接-背景说明.md` | 完整上下文、已知故障、设计决策 |
| `CurrentHRVDemo/` | 队友的 Swift / HealthKit HRV demo，标为 Phase 2 入口，**未进主旅程** |
| `brand/` | 品牌手册、路演物料、标识 SVG、pptx 模板 |

### 产品定义

> 在说不清的时刻，帮你找到此刻适合你的空间。

闭环七步：出发前情绪 → 需求发现 → 推荐空间 → 实际到访 → 30 秒反馈
→ 私密记录／匿名贡献 → 改进下一次推荐。

「此在」= 海德格尔 Dasein。不问你是什么样的人，只问你此刻在哪儿。
Current 一词三义：**此刻的 / 电流（HRV、皮电）/ 水流**。

### 已实现

- 北京空间库 **26 个地点**，动作优先卡片，
  每条含 `action / see / cost / tags / matchReason / placeInsights`
- **12 个标准化标签**、统一因素字典 25 条
- 加权匹配 `matchScore(place, mood, needs)`，用户明确选的诉求维度权重 **×2.8**
- 情绪 **10 个**（刻意不用「焦虑/疲惫」这类临床标签）
- 需求发现页 13 个诉求，分空间／刺激／恢复三向
- 深色→浅色全量改造完成，红色已从所有负向用色中移除

### 三条硬边界 —— 会否决设计方案，不是价值观标语

| 边界 | 含义 |
|---|---|
| **不诊断** | 不给情绪贴标签，不暗示病理。可以说「你 7 次里有 5 次选了人不多」，不能说「你是高敏感人群」 |
| **不评判** | 变化分数负端**不能用红**。情绪变差不是错误，只是这次没接住 |
| **不社交** | 没有昵称、人脸、主页、评论、关注、私信 |

### 视觉铁律

冷色承担空间与时间，**暖色只标记「你 / 此刻」**。用色比例 70 底 / 22 墨 / 6 水青 / 2 赭。
一屏之内出现超过两处赭色即为未改干净。

```
--paper #F0F3F2   --card #FFFFFF   --sunk #E8EDEC
--ink   #122A2E   --ink-dim #5A6E70   --ink-faint #8CA0A0
--water #1E6E72   流·空间·冷
--sun   #C4703C   此刻·你·唯一的暖
```

情绪色阶 −3…+3（负端走灰紫，**绝不用红**）：
```
-3 #4E4B63   -2 #6B687F   -1 #9694A5
 0 #C3C9C7
+1 #86ADA8   +2 #4A8F8A   +3 #1E6E72
```

---

## 2. 设备分层（评委一定会追问，必须分清）

```
┌─ 手机 phone ────────── 说 · 定位 · 带着走 · 唤起地图
│    语音输入、geolocation、出门在外的唯一载体
│    只有手机端出现「去这儿」按钮
│
├─ 桌面 desk ─────────── 承接 · 回收
│    出门前同步睁眼；回来后心情卡自动浮现
│    不出现「去这儿」—— 桌面不是用来出发的
│
└─ 地图 App ──────────── 工具调用（⚠️ 不是跨设备）
     高德深链：移动端唤起 App，桌面端落网页
```

设备角色由 `deviceRole()` 自动判定（触摸 + 窄屏 = phone），
可用 `localStorage.setItem('current.role','desk')` 强制覆盖 —— **演示时务必固定**。

### 跨设备如何运作

本质是一个**共享的临时会话号**（4 位，如 `a7f3`）：

```
手机生成 sid → 桌面输入同一个 sid（点顶部会话号即可输入）
      ↓
两端各自轮询 /api/relay?sid=a7f3
      ↓
手机说「烦」→ push('resolved') → 桌面睁眼 + 卡片浮现
手机点「去这儿」→ push('departed') → 桌面：「他出门了。去亮马河南岸。」
回来说「好点了」→ push('feedback') → 桌面：心情卡落色
```

**sid 不是账号**：无登录、无身份、关页即散，天然守住「不社交」。

---

## 3. 待修改文件清单

### 🔴 P0 —— 不做就不合规

| # | 文件 | 动作 | 预估 |
|---|---|---|---|
| 1 | `agent/current-agent.js` | 新建（附录 A）+ **改适配区词表** | 40 min |
| 2 | `此在-current-原型.html` | 末尾加 script + 入口按钮 | 20 min |
| 3 | `api/read.js` | 新建（附录 B），LLM 代理 | 30 min |
| 4 | `api/relay.js` | 新建（附录 C），跨设备中继 | 30 min |
| 5 | — | 双设备联调，跑通三条 push | 1 h |

### 🟡 P1 —— 影响评分

| # | 文件 | 动作 | 预估 |
|---|---|---|---|
| 6 | `此在-current-原型.html` | 到访反馈页接 `afterVisit()` | 1 h |
| 7 | `此在-current-原型.html` | 卡片文案接 `texture` 字段 | 1 h |
| 8 | `README.md` | 重写，加跨设备架构图 + 开源说明 | 40 min |
| 9 | `LICENSE` | 新建，MIT | 5 min |

### 🟢 P2 —— 有余力再做

| # | 动作 |
|---|---|
| 10 | 桌面端扫码加入（二维码代替手输 sid），演示更顺 |
| 11 | ROUTES 四条路线 UI 露出（README 已列为待办） |

---

## 4. 具体任务

### ■ 任务 1：提取真实词表并填入适配区

**这是所有后续工作的前提。词对不上，模型抽出的词会被全部过滤，推荐结果为空。**

在 `此在-current-原型.html` 中定位以下四项，**原样提取，一个字都不要改**：

1. 10 个情绪的字符串数组（搜 `mood` / `MOODS`）
2. 13 个诉求的字符串数组（搜 `needs` / `NEEDS`）
3. `matchScore` 的完整签名与实现（确认参数顺序与类型）
4. 地点数组的变量名（搜 `PLACES` / `places`）

填入 `agent/current-agent.js` 顶部的 `HOST` 对象。

> ⚠️ 若这些变量在 IIFE 闭包内、未挂到 `window`：
> **不要重构原型把它们提到全局**。在闭包内显式赋值即可：
> ```js
> window.__CURRENT_MOODS__ = MOODS;
> window.__CURRENT_PLACES__ = PLACES;
> window.__CURRENT_MATCHSCORE__ = matchScore;
> ```
> 适配区已预留对这几个名字的读取。**改动越小越好。**

**顺带确认**：地点数据里有没有 `lat` / `lng`。
有 → 地图深链可直接导航；没有 → 降级为关键词搜索（代码已处理，但导航体验弱一档）。
若原型里已有坐标字段但名字不同，在 `TOOLS.navigate` 里转接。

---

### ■ 任务 2：校准投影规则

`PROJECT` 对象把五个连续维度投影成诉求权重。
**当前实现基于推测的诉求词表，必须按真实词表重写。**

| 轴 | 低端 (-1) | 高端 (+1) |
|---|---|---|
| `activation` | 蔫住了 / 动不了 | 绷着 / 停不下来 |
| `valence` | 难受 | 舒服 |
| `social` | 一个人都不想见 | 想在人气里 |
| `agency` | 被推着走 | 自己说了算 |
| `bodyload` | 身体还有劲 (0) | 身体撑不住 (1) |

五个轴**全部无好坏方向** —— 这是「不评判」的代码级保证。

改写原则：

- **读不出指向就返回 0**。宁可少给，不可制造底噪
- 想清楚「什么样的此刻真的需要这条」，而不是「它听起来像什么情绪」
- 互斥诉求必须互斥：`bodyload > 0.5` 时 `能一直走` 必须返回 0
- `这个点还开着` 由情境硬加，不由维度推

同时校准 `toMood()` —— 它把维度反向映射回 10 个情绪词，
**仅用于兼容现有 `matchScore` 的 mood 参数，永不显示给用户。**

---

### ■ 任务 3：挂载到主原型

`</body>` 前加：

```html
<script src="agent/current-agent.js"></script>
```

在现有情绪选择页**上方**加入口（原选择页保留，作为「不想说」的退路）：

```html
<button onclick="CurrentAgent.open()">说一句就行</button>
```

**约束：不要修改原型任何已有代码。** Agent 层是叠加的浮层，不是替换。
出问题可以删一行回滚。

---

### ■ 任务 4：LLM 代理（安全关键）

**背景：Vercel 在 2026 年 4 月披露过安全事件，
攻击者读到了部分客户未标记为 sensitive 的环境变量。**

**严禁**把 API key 放前端。代码已默认请求 `/api/read`，
把**附录 B** 建为 `api/read.js` 即可，无需改调用侧。

Vercel 后台配置，**三个全部勾选 Sensitive**：
`LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL`

> 这会在**公开部署版本**上破掉「无后端」。这是必要代价。
> **本地单文件版本必须保持原样** —— 路演时「双击就跑、断网也跑」是核心卖点。
> 代码已内置：检测到 `location.protocol === 'file:'` 时完全不发网络请求。

---

### ■ 任务 5：跨设备中继 + 联调

把**附录 C** 建为 `api/relay.js`。内存实现，无需数据库。

> ⚠️ Vercel serverless 实例之间不共享内存，冷启动会丢。
> **演示够用**（同一实例通常能存活几分钟）。
> 若联调时发现丢事件，升级为 Vercel KV：`npm i @vercel/kv`，
> 把 `MEM` 换成 KV 读写即可，接口不变。

**联调步骤（必须两台设备真机验证）：**

```
1. 电脑打开站点 → 看顶部会话号，如 a7f3
2. 手机打开同一站点 → 点顶部会话号 → 输入 a7f3
3. 手机说「烦」        → 电脑应睁眼 + 出卡片
4. 手机点「去这儿」    → 电脑应显示「他出门了」
5. 手机说「好点了」    → 电脑应显示心情卡 + 色阶圆点
```

三条全通，选项 B 才算成立。

---

### ■ 任务 6：到访反馈接 Agent

现状：到访后 30 秒反馈是**表单式自陈**。

改为：在原型的到访页调用 `CurrentAgent.afterVisit(地点名)`。
用户说一句话，`deltaOf()` 读出 `delta ∈ [-3,3]`，套用已有色阶（索引 `delta+3`）。

文案必须**无评判**：「这次接住了 / 这次没接住 / 和去之前差不多」。
不得出现「推荐失败」「不匹配」等暗示对错的词。

---

### ■ 任务 7：卡片文案接 texture

理解层输出 `texture` —— 模型自由生成的一句不超过 18 字的白话，
描述此刻的**具体质地**，不受任何词表限制。

例：「不是难受，是提不起劲」「想有人在旁边但别跟我说话」

**这是 LLM 真正强于分类器的地方，不要浪费。**
用它生成卡片的 `matchReason`，替代模板化文案。

遵守既有内容规则：**讲「你到了做什么」，不讲「这个地方是什么」。
卡片标题是一个动作，地名降为副标题。**

---

### ■ 任务 8：README 重写

必须包含：

1. 产品定义（保留现有开篇）
2. **跨设备架构图**（mermaid），明确标出 phone / desk / 工具调用三层
3. Agent 层说明：情境感知、工具调用、跨设备接续、五维理解、降级策略
4. 三条硬边界 **+ 它们在代码中的落点**（加分项）
5. 开源说明：协议、本地运行、贡献方式
6. **医疗免责声明**（保留 HRV 叙事则必须有）：

> 本项目不输出任何绝对健康指标，不做健康状态判断，不构成医疗建议。
> 相关信号仅用于生成**相对变化量**。

---

## 5. 全局约束（任何改动都不得违反）

1. **不重构主原型。** 2249 行单文件是特性不是债务，
   「双击就跑、无构建、断网也能跑」是路演核心卖点
2. **维度永不回显给用户。** 显示出来即构成诊断，破第一条硬边界
3. **负端永不用红。** 色阶表已定稿，直接取值，不要自创颜色
4. **不采集任何身份信息。** sid 是临时编号，不是账号；无登录、无跨会话画像
5. **模型/中继不可用必须降级**，不得白屏。离线规则精度低但结构一致
6. **追问最多一次。** 追问三次就变回表单了 —— 产品判断，不是技术限制
7. **工具调用绑定设备角色。** 桌面端不出「去这儿」—— 桌面不是用来出发的
8. **保持零依赖。** 新增依赖需先确认

---

## 6. 验收

### 合规性（对照官方三条要求）

```
□ 理解情境 —— 工作日夜里 + 手机端，小在主动开口，用户未点任何按钮
□ 调用工具 —— 提交时自动取定位；点「去这儿」唤起地图；两者均非用户主动发起的独立操作
□ 跨设备  —— 手机说话 → 桌面睁眼出卡；手机出发 → 桌面知道；手机反馈 → 桌面落色
□ 材料中「工具调用」与「跨设备接续」表述清晰、不混用
```

### 功能

```
□ 「烦」「有点烦」「快炸了」→ 三者推荐结果明显不同
□ 「就是有点提不起劲，但也不是难受」→ 不归为「低落」
□ 「想出去走走但不想一个人」→ social 为正（否定被反转而非丢弃）
□ 「随便」→ 触发且仅触发一次追问
□ 断网 → 仍能出卡片，无报错，无白屏
□ 本地双击 html 仍能独立运行，且不发任何网络请求
```

### 边界

```
□ 前端任何位置搜不到 API key
□ 用户全程看不到任何维度数值或情绪标签
□ 负向反馈呈现色不含任何红色
□ 无登录、无昵称、无头像
```

---

## 7. 交付物（报名表要求）

官方要：团队与项目简介、目标用户/场景/问题、**Agent 的核心工作与差异**、
**可访问原型**、**不超过 1 分钟的演示视频（必填）**、深圳目标与支持需求、开源计划。
代码仓库链接可选。

### 「Agent 的核心工作与差异」建议写法

最容易写砸的一栏。别写「我们用 AI 理解情绪」—— 满场都这么写。

> 用户说一句含糊的话，小在读出五个连续维度而非贴一个情绪标签，最多追问一次就给结论。
> 它自己决定何时取定位、何时唤起地图，而不是让用户去点。
> 任务在手机与桌面之间接续 —— 出门前的状态、路上的去向、回来后的反馈是同一条线，
> 不是三次独立使用。

### 一分钟视频

**拍这个：**

> 晚上九点半，办公室。手机上小在自己睁眼：「这个点还没走。」
> 他说一句「烦」。
> **桌上电脑的面板同时亮起 —— 这一刻两块屏同框，跨设备成立。**
> 他点「去这儿」，地图接上，电脑上小在说「他出门了」。
> 十一点回来，说一句「好点了」。电脑上那张心情卡自己落了色。

**不要拍界面走查。场景 > 功能。**
两块屏同框那一秒，比任何文案都有说服力。

---

## 8. 时间表

| 日期 | 内容 |
|---|---|
| 9/20–9/23 | 任务 1–5（P0 全部），**双设备联调必须通** |
| 9/24–9/26 | 任务 6–7 |
| 9/27–9/29 | 打磨、边界 case、桌面扫码加入（P2） |
| 9/30–10/02 | **拍一分钟视频**（预留两天，不要压到最后） |
| 10/03–10/04 | 任务 8–9，填报名表，提交 |

### 现在就该确认的两件事

1. **中英文口径不一致**：中文主页写「仅接受自研智能硬件或改造、整合现有设备的项目」，
   英文页与媒体稿都说纯软件也可以。**去微信群问组委会，别猜。**
2. 手表端不做 mock。报名表如实写：
   「已跑通手机↔桌面接续；手表端已有 HealthKit HRV demo（仓库内 `CurrentHRVDemo/`），
   计划在深圳现场接入 Live Activity。」
   **路线图是加分，假演示是减分。**

---

## 9. 对外接口速查

```js
// 交互
CurrentAgent.open() / close()
CurrentAgent.ask('今天太累了')          // 直接喂一句话（调试）
CurrentAgent.afterVisit('角楼图书馆')   // 到访后追问

// 理解
CurrentAgent.read(text)                 // → Promise<结果对象>
CurrentAgent.toLegacy(result)           // → { mood, needs, weights }
CurrentAgent.describe(dimensions)       // 调试用，勿面向用户

// 工具（Agent 自己调，一般不用手动）
CurrentAgent.tools.navigate(place)      // 地图深链
CurrentAgent.tools.locate()             // 定位
CurrentAgent.tools.share(text)          // 系统分享

// 跨设备
CurrentAgent.relay.session()            // 当前会话号
CurrentAgent.relay.join('a7f3')         // 加入另一块屏
CurrentAgent.role()                     // 'phone' | 'desk'

// 事件
document.addEventListener('current:resolved', e => {});  // { result, legacy, places }
document.addEventListener('current:feedback', e => {});  // { place, text, delta, result }
document.addEventListener('current:tool',     e => {});  // { tool, ... }
document.addEventListener('current:remote',   e => {});  // 另一块屏来的
```

**「小在」表情规范：** 一朵云，只靠眼睛做表情，**没有嘴**
（有嘴就会有情绪表演，而它的职责是陪着）。
四种够用：平静 / 看向你 / 闭眼（记录保存、切私密）/ 陪着。

---

# 附录 A：`agent/current-agent.js`

> 935 行，零依赖，含情境感知 / 工具调用 / 跨设备接续 / 五维理解 / 交互层。
> **顶部【适配区】必须按任务 1 改写后才能正常工作。**

```javascript
/* =====================================================================
 * 此在 / Current —— Agent 层（单文件版 v0.3 · 跨设备）
 * ---------------------------------------------------------------------
 * 赛道 B：现有设备与跨设备系统。
 *
 * 三件事必须同时成立，缺一不可：
 *   ① 理解情境 —— 时间/位置/设备角色，不问就知道
 *   ② 调用工具 —— 地图深链、定位、系统分享，Agent 自己决定调哪个
 *   ③ 跨设备接续 —— 手机说的话，另一块屏接住；出门前/路上/回来是同一条线
 *
 * 不修改主原型任何已有代码，只在 HTML 末尾加一行 <script src>。
 * 零依赖、无构建；断网降级到离线规则，结构一致。
 *
 * 三条硬边界在代码中的落点：
 *   不诊断 —— 维度是「此刻的位置」不是「你这个人的属性」；永不回显；
 *             system prompt 明令禁止；normalize() 二次拦截诊断类词
 *   不评判 —— 五个轴均无好坏方向；色阶取自定稿表，负端灰紫无红
 *   不社交 —— sessionId 是临时编号不是账号；无登录/昵称/头像/跨会话画像
 * ===================================================================== */
(function (root) {
  'use strict';

  /* ===================================================================
   * 【适配区】—— 只需改这一段
   * ⚠️ 必须与主原型里的字符串**完全一致**，差一个字就会被过滤掉
   * =================================================================== */
  var HOST = {

    // 1) 主原型里那 10 个情绪的原始字符串
    moods: [
      '低落', '需要安静', '累', '心里发紧', '闷',
      '烦躁', '空', '想动一动', '还行', '说不清'
    ],

    // 2) 13 个诉求的原始字符串
    needs: [
      '一个人待着', '人不多', '能坐下', '有光', '有水',
      '能一直走', '有声音', '安静', '不用消费', '能待久',
      '有东西看', '离得近', '这个点还开着'
    ],

    // 3) 指向已有的打分函数。签名不同就在这里转接。
    recommend: function (mood, needs) {
      var score = root.matchScore || root.__CURRENT_MATCHSCORE__;
      var pool  = root.PLACES || root.places || root.__CURRENT_PLACES__ || [];
      if (typeof score !== 'function' || !pool.length) return [];
      return pool
        .map(function (p) { return { p: p, s: score(p, mood, needs) }; })
        .sort(function (a, b) { return b.s - a.s; })
        .map(function (x) { return x.p; });
    },

    // 4) 复用已有的卡片渲染。返回 null 则走内置兜底。
    renderCards: function (places) {
      if (typeof root.renderCards === 'function') return root.renderCards(places);
      return null;
    },

    // 5) 情绪色阶（已按定稿填好，负端灰紫，无红）
    scale: ['#4E4B63', '#6B687F', '#9694A5', '#C3C9C7', '#86ADA8', '#4A8F8A', '#1E6E72']
  };

  /* ===================================================================
   * 【配置】
   * =================================================================== */
  var CFG = {
    llmEndpoint:   '/api/read',    // LLM 代理，禁止把 key 放前端
    relayEndpoint: '/api/relay',   // 跨设备中继
    timeout: 7000,
    pollMs: 1500,
    // 仅本地调试，公开部署务必留空
    directBase: '', directKey: '', directModel: 'gpt-4o-mini'
  };

  function configure(o) {
    if (!o) return CFG;
    Object.keys(o).forEach(function (k) { CFG[k] = o[k]; });
    return CFG;
  }

  // file:// 下不发任何网络请求，保住「双击就跑、断网也跑」
  function isOffline() {
    if (root.location && root.location.protocol === 'file:') return true;
    return !CFG.llmEndpoint && !CFG.directKey;
  }

  /* ===================================================================
   * ① 情境 —— Agent 不问就能知道的
   * =================================================================== */
  var ROLE = null;   // 'phone' | 'desk'

  function deviceRole() {
    if (ROLE) return ROLE;
    var saved = safeGet('current.role');
    if (saved) return (ROLE = saved);
    var touch = ('ontouchstart' in root) ||
                (navigator.maxTouchPoints > 0);
    var narrow = root.innerWidth < 820;
    ROLE = (touch && narrow) ? 'phone' : 'desk';
    return ROLE;
  }

  function context(now) {
    var t = now || new Date(), h = t.getHours(), dow = t.getDay();
    return {
      hour: h,
      band: h < 6 ? '深夜' : h < 11 ? '上午' : h < 14 ? '中午'
          : h < 18 ? '下午' : h < 22 ? '晚上' : '深夜',
      weekday: ['周日','周一','周二','周三','周四','周五','周六'][dow],
      late: h >= 21 || h < 5,
      workNight: h >= 20 && h <= 23 && dow >= 1 && dow <= 5,
      role: deviceRole(),
      geo: GEO.last
    };
  }

  function safeGet(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }
  function safeSet(k, v) { try { localStorage.setItem(k, v); } catch (e) {} }

  /* ===================================================================
   * ② 工具 —— Agent 自己决定调哪个，不是让用户去点
   * =================================================================== */
  var GEO = {
    last: null,
    get: function () {
      return new Promise(function (res) {
        if (!navigator.geolocation) return res(null);
        navigator.geolocation.getCurrentPosition(
          function (p) {
            GEO.last = { lat: +p.coords.latitude.toFixed(4),
                         lng: +p.coords.longitude.toFixed(4) };
            res(GEO.last);
          },
          function () { res(null); },
          { timeout: 4000, maximumAge: 300000 }
        );
      });
    }
  };

  var TOOLS = {

    /* 地图深链 —— 移动端优先唤起 App，桌面端落网页 */
    navigate: function (place) {
      var name = encodeURIComponent(place.name || place.title || '');
      var has = place.lat && place.lng;
      var url;
      if (deviceRole() === 'phone') {
        url = has
          ? 'https://uri.amap.com/navigation?to=' + place.lng + ',' + place.lat
            + ',' + name + '&mode=walk&src=current'
          : 'https://uri.amap.com/search?keyword=' + name + '&src=current';
      } else {
        url = 'https://ditu.amap.com/search?query=' + name;
      }
      root.open(url, '_blank');
      emit('current:tool', { tool: 'navigate', place: place.name });
      return url;
    },

    /* 系统分享 —— 心情卡交给系统，不自建社交 */
    share: function (text) {
      if (navigator.share) {
        return navigator.share({ title: '此在', text: text })
          .then(function () { emit('current:tool', { tool: 'share' }); })
          .catch(function () {});
      }
      if (navigator.clipboard) {
        return navigator.clipboard.writeText(text)
          .then(function () { emit('current:tool', { tool: 'copy' }); });
      }
      return Promise.resolve();
    },

    /* 定位 */
    locate: function () {
      return GEO.get().then(function (g) {
        if (g) emit('current:tool', { tool: 'locate' });
        return g;
      });
    }
  };

  /* ===================================================================
   * ③ 跨设备接续 —— sessionId 是临时编号，不是账号
   * =================================================================== */
  var RELAY = {
    sid: null,
    timer: null,
    seen: 0,

    /* 取得或生成会话号。手机端生成，桌面端输入/扫码加入。 */
    session: function () {
      if (RELAY.sid) return RELAY.sid;
      var q = (root.location.hash.match(/s=([a-z0-9]{4,8})/i) || [])[1];
      RELAY.sid = q || safeGet('current.sid') ||
                  Math.random().toString(36).slice(2, 6);
      safeSet('current.sid', RELAY.sid);
      return RELAY.sid;
    },

    join: function (sid) {
      RELAY.sid = String(sid).toLowerCase().trim();
      safeSet('current.sid', RELAY.sid);
      RELAY.seen = 0;
      RELAY.listen();
      return RELAY.sid;
    },

    /* 写：把这一刻推给另一块屏 */
    push: function (type, payload) {
      if (isOffline() || !CFG.relayEndpoint) return Promise.resolve();
      return fetch(CFG.relayEndpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          sid: RELAY.session(), type: type,
          from: deviceRole(), payload: payload, ts: Date.now()
        })
      }).catch(function () {});
    },

    /* 读：轮询另一块屏推来的东西 */
    listen: function () {
      if (isOffline() || !CFG.relayEndpoint) return;
      clearInterval(RELAY.timer);
      RELAY.timer = setInterval(function () {
        fetch(CFG.relayEndpoint + '?sid=' + RELAY.session() + '&since=' + RELAY.seen)
          .then(function (r) { return r.ok ? r.json() : null; })
          .then(function (d) {
            if (!d || !d.events || !d.events.length) return;
            d.events.forEach(function (ev) {
              if (ev.from === deviceRole()) return;   // 不接自己发的
              RELAY.seen = Math.max(RELAY.seen, ev.ts);
              onRemote(ev);
            });
          })
          .catch(function () {});
      }, CFG.pollMs);
    },

    stop: function () { clearInterval(RELAY.timer); }
  };

  /* 另一块屏来的事件 */
  function onRemote(ev) {
    if (ev.type === 'resolved') {
      open();
      face('with');
      var r = ev.payload.result;
      speak(r && r.texture ? '「' + r.texture + '」' : '他刚说了一句。');
      renderCards(ev.payload.places || [], true);
      emit('current:remote', ev);
    }
    if (ev.type === 'departed') {
      open(); face('look');
      speak('他出门了。' + (ev.payload.place ? '去' + ev.payload.place + '。' : ''));
      emit('current:remote', ev);
    }
    if (ev.type === 'feedback') {
      open(); face('closed');
      speak('他回来了。');
      showDelta(ev.payload.delta);
      emit('current:remote', ev);
    }
  }

  function emit(name, detail) {
    document.dispatchEvent(new CustomEvent(name, { detail: detail }));
  }

  /* ===================================================================
   * 理解层：五个连续维度
   * 每个轴都**没有好坏方向**，只是位置。
   * =================================================================== */
  var AXES = {
    activation: { lo: '蔫住了 / 动不了', hi: '绷着 / 停不下来' },
    valence:    { lo: '难受',            hi: '舒服' },
    social:     { lo: '一个人都不想见',   hi: '想在人气里' },
    agency:     { lo: '被推着走',         hi: '自己说了算' },
    bodyload:   { lo: '身体还有劲',       hi: '身体撑不住' }
  };

  /* 维度 → 诉求权重。原则：读不出指向就返回 0，宁可少给不可制造底噪。 */
  var PROJECT = {
    '一个人待着': function (d) { return d.social < -0.3 ? (-d.social - 0.3) * 1.6 : 0; },
    '人不多':     function (d) { return d.social < -0.1 ? (-d.social) * 0.9 : 0; },
    '有声音':     function (d) { return d.social >  0.2 ? (d.social - 0.2) * 1.3 : 0; },

    '能坐下': function (d) {
      if (d.bodyload > 0.35)   return d.bodyload * 1.2;
      if (d.activation < -0.4) return 0.45;
      return 0;
    },
    '能一直走': function (d) {
      if (d.bodyload > 0.5)    return 0;              // 走不动就是走不动
      if (d.activation > 0.25) return (d.activation - 0.25) * 1.5;
      if (d.agency > 0.3)      return (d.agency - 0.3) * 0.8;
      return 0;
    },
    '能待久': function (d) {
      if (d.bodyload > 0.45) return 0.75;
      if (d.valence < -0.4)  return 0.6;
      return 0;
    },
    '安静': function (d) {
      var w = 0;
      if (d.social < -0.25)    w += (-d.social) * 0.9;
      if (d.activation > 0.45) w += 0.35;
      return w;
    },
    '有光': function (d) { return d.valence < -0.3 ? (-d.valence - 0.3) * 1.2 : 0; },
    '有水': function (d) {
      return (d.valence < -0.3 && d.activation > 0.2)
           ? Math.min(0.8, (-d.valence) * (d.activation + 0.4)) : 0;
    },
    '有东西看': function (d) {
      if (d.bodyload > 0.45) return 0;
      if (d.activation < -0.15 && Math.abs(d.valence) < 0.28) return 0.85;  // 「空」
      if (d.social > 0.25) return 0.3;
      return 0;
    },
    '不用消费': function (d) { return d.agency < -0.35 ? (-d.agency) * 0.8 : 0; },
    '离得近': function (d) {
      if (d.bodyload > 0.4)     return d.bodyload * 0.9;
      if (d.activation < -0.45) return 0.5;
      return 0;
    },
    '这个点还开着': function () { return 0; }   // 由情境硬加
  };

  /* 维度 → 情绪词。仅用于兼容现有 matchScore，永不显示。 */
  function toMood(d) {
    if (d.bodyload > 0.55 && d.activation < 0.1)           return '累';
    if (d.social < -0.45 && Math.abs(d.activation) < 0.3)  return '需要安静';
    if (d.activation > 0.25 && d.valence < -0.18)          return '烦躁';
    if (d.activation > 0.25)  return d.valence > 0.15 ? '想动一动' : '心里发紧';
    if (d.activation < -0.35 && d.valence < -0.35)         return '低落';
    if (d.activation < -0.1 && Math.abs(d.valence) < 0.28) return '空';
    if (d.activation < -0.1 && d.valence < 0)              return '闷';
    if (d.valence > 0.25)                                  return '还行';
    return '说不清';
  }

  /* ===================================================================
   * Prompt —— 让模型「读」，不让它「选」
   * =================================================================== */
  var SYSTEM = [
    '你是"此在 / Current"的理解层。用户会用很随意的一句话描述此刻状态。',
    '你的任务不是给他贴标签，而是**读懂这一刻的具体质地**。',
    '',
    '# 输出字段',
    '',
    '## 1. dimensions —— 五个连续维度，-1 到 1 的小数（bodyload 为 0 到 1）',
    'activation  蔫住了/动不了(-1) ←→ 绷着/停不下来(+1)',
    'valence     难受(-1) ←→ 舒服(+1)',
    'social      一个人都不想见(-1) ←→ 想在人气里(+1)',
    'agency      被推着走(-1) ←→ 自己说了算(+1)',
    'bodyload    身体还有劲(0) ←→ 身体撑不住(1)',
    '',
    '这五个轴**没有好坏方向**，不要把负值理解成"不好"。',
    '用小数。"有点烦"是 0.35，"快炸了"才是 0.9。读不出的维度给 0，不要猜。',
    '注意否定与转折："不想一个人"意味着 social 偏正，不是偏负。',
    '',
    '## 2. texture —— 一句不超过 18 字的白话，描述这一刻的**具体质地**',
    '自由表达，不受词表限制，这正是你比分类器强的地方。',
    '例："不是难受，是提不起劲" / "想有人在旁边但别跟我说话"',
    '写"此刻像什么"，绝不写"你是什么人"。',
    '',
    '## 3. needs —— 从给定诉求词表里选，每条给 0~1 权重，格式 {"词": 权重}',
    '只给真的读出来的，宁缺毋滥。',
    '',
    '## 4. constraints —— 读出来的硬约束，没有就 null',
    'minutes 大概能出去多久（数字，分钟）｜ money "不想花钱"/"无所谓" ｜ walk 还能不能走路(true/false)',
    '',
    '## 5. quotes —— 从原话里摘 1~2 个关键短句，一字不改',
    '',
    '## 6. followup —— 仅在信息确实不够时给一个口语化短问句(<20字)，否则 null',
    '要具体，像"想清净点还是想有点人气"这种二选一。',
    '',
    '# 硬性禁止',
    '- 不做任何健康、心理、病理判断，不使用任何医学词汇',
    '- 不给用户贴人格标签（"你是敏感型"这类绝对禁止）',
    '- needs 只能用给定词表里的词；texture 与 quotes 不受限',
    '',
    '严格输出 JSON，不要代码块，不要解释。'
  ].join('\n');

  function buildUser(text, ctx, prev) {
    var s = '诉求词表（needs 只能用这些）：\n' + HOST.needs.join(' / ') + '\n\n'
          + '此刻情境：' + ctx.weekday + ' ' + ctx.band + ' ' + ctx.hour + ' 点'
          + (ctx.workNight ? '（工作日夜里，他很可能还在公司）' : '')
          + (ctx.late ? '（很晚了，很多地方已关门）' : '')
          + (ctx.role === 'phone' ? '（他正拿着手机，可能准备出门）' : '（他在桌前）')
          + '\n\n他说：' + text;
    if (prev) {
      s += '\n\n（这是在回答你上一句"' + prev.followup + '"。上一轮维度：'
         + JSON.stringify(prev.dimensions) + '。请结合两轮重新给出完整结果，不要再追问。）';
    }
    return s;
  }

  /* ===================================================================
   * 离线细读 —— 多条信号累加成维度（不是命中一条规则）
   * =================================================================== */
  var SIGNALS = [
    // 词          act   val   soc   agy  body
    ['累',        -0.4, -0.2, -0.2,  0,   0.8],
    ['困',        -0.5, -0.1, -0.2,  0,   0.7],
    ['没劲',      -0.6, -0.3, -0.1,  0,   0.5],
    ['提不起',    -0.6, -0.2,  0,    0,   0.4],
    ['蔫',        -0.6, -0.3,  0,    0,   0.5],
    ['烦',         0.6, -0.5, -0.4, -0.2, 0  ],
    ['躁',         0.7, -0.5, -0.3, -0.2, 0  ],
    ['炸',         0.9, -0.6, -0.5, -0.3, 0  ],
    ['受不了',     0.7, -0.6, -0.5, -0.4, 0.2],
    ['紧',         0.5, -0.4, -0.2, -0.3, 0.1],
    ['慌',         0.6, -0.5, -0.2, -0.5, 0  ],
    ['焦',         0.6, -0.4, -0.2, -0.4, 0  ],
    ['压',         0.3, -0.5, -0.2, -0.6, 0.3],
    ['喘不过',     0.6, -0.6, -0.3, -0.5, 0.2],
    ['难受',      -0.2, -0.7, -0.3, -0.2, 0.2],
    ['丧',        -0.5, -0.6, -0.3, -0.3, 0.2],
    ['低落',      -0.4, -0.6, -0.3, -0.2, 0.1],
    ['委屈',      -0.2, -0.6, -0.2, -0.4, 0  ],
    ['哭',        -0.2, -0.7, -0.5, -0.3, 0.2],
    ['闷',        -0.2, -0.4, -0.2, -0.3, 0  ],
    ['憋',         0.3, -0.4, -0.2, -0.4, 0  ],
    ['堵',         0.2, -0.4, -0.1, -0.3, 0  ],
    ['空',        -0.3, -0.1, -0.1, -0.1, 0  ],
    ['无聊',      -0.3,  0,    0.2,  0,   0  ],
    ['没意思',    -0.4, -0.2,  0,    0,   0  ],
    ['麻',        -0.4, -0.1, -0.2,  0,   0.1],
    ['静',        -0.1,  0,   -0.6,  0.2, 0  ],
    ['清净',      -0.1,  0.1, -0.6,  0.2, 0  ],
    ['别吵',       0.2, -0.2, -0.7,  0.1, 0  ],
    ['一个人',     0,    0,   -0.7,  0.2, 0  ],
    ['不想见',     0,   -0.2, -0.8,  0.1, 0  ],
    ['想出去',     0.3,  0,    0.1,  0.3, 0  ],
    ['走走',       0.2,  0,    0,    0.3, 0  ],
    ['动',         0.4,  0.1,  0.1,  0.3, 0  ],
    ['热闹',       0.2,  0.1,  0.7,  0.2, 0  ],
    ['人气',       0,    0,    0.6,  0.1, 0  ],
    ['有人',       0,    0,    0.5,  0,   0  ],
    ['还行',       0,    0.3,  0,    0.2, 0  ],
    ['还好',       0,    0.3,  0,    0.2, 0  ],
    ['凑合',      -0.1,  0.1,  0,    0,   0.2],
    ['舒服',      -0.1,  0.6,  0,    0.3, 0  ],
    ['开心',       0.3,  0.7,  0.3,  0.3, 0  ]
  ];

  var AMP = [['有点',0.6],['稍微',0.5],['一点',0.6],['特别',1.4],['太',1.4],
             ['超',1.4],['巨',1.5],['快',1.3],['要命',1.5],['死',1.4],['非常',1.4]];
  var NEG = ['不', '没', '并不', '算不上', '谈不上'];

  function offlineRead(text, ctx) {
    var d = { activation:0, valence:0, social:0, agency:0, bodyload:0 };
    var hits = 0, quotes = [];

    var amp = 1;
    AMP.forEach(function (a) { if (a[1] > 1 && text.indexOf(a[0]) > -1) amp = Math.max(amp, a[1]); });
    if (amp === 1) AMP.forEach(function (a) { if (a[1] < 1 && text.indexOf(a[0]) > -1) amp = a[1]; });

    SIGNALS.forEach(function (s) {
      var idx = text.indexOf(s[0]);
      if (idx < 0) return;
      // 否定 → 信号反转并衰减，而不是丢弃
      // 「不想一个人」携带的是"想有人"，跳过就丢了这条信息
      var pre = text.slice(Math.max(0, idx - 3), idx);
      var neg = NEG.some(function (n) { return pre.indexOf(n) > -1; });
      var sign = neg ? -0.7 : 1;
      hits++;
      if (!neg) quotes.push(s[0]);
      d.activation += s[1] * amp * sign;
      d.valence    += s[2] * amp * sign;
      d.social     += s[3] * amp * sign;
      d.agency     += s[4] * amp * sign;
      d.bodyload   += neg ? -s[5] * amp * 0.7 : s[5] * amp;
    });

    if (hits > 1) { var k = 1 / Math.sqrt(hits); for (var key in d) d[key] *= k; }
    clampDims(d);

    return {
      dimensions: d,
      texture: '',
      needs: projectNeeds(d, ctx),
      constraints: { minutes: null, money: null, walk: null },
      quotes: quotes.slice(0, 2),
      followup: offlineFollowup(d, hits),
      confidence: offlineConf(d, hits),
      _offline: true
    };
  }

  function offlineConf(d, hits) {
    if (!hits) return 0.22;
    var mag = (Math.abs(d.activation) + Math.abs(d.valence)
             + Math.abs(d.social) + d.bodyload) / 4;
    return Math.round(Math.min(0.62, 0.26 + mag * 0.75) * 100) / 100;
  }

  function offlineFollowup(d, hits) {
    if (!hits) return '想一个人待着，还是想有点声音？';
    if (Math.abs(d.social) < 0.18 && Math.abs(d.activation) > 0.3)
      return '想清净点，还是想有点人气？';
    if (d.bodyload < 0.2 && Math.abs(d.activation) < 0.25)
      return '想找地方坐着，还是想走走？';
    return null;
  }

  /* ===================================================================
   * 工具函数
   * =================================================================== */
  function clamp(v, lo, hi) {
    v = (typeof v === 'number' && isFinite(v)) ? v : 0;
    return Math.max(lo, Math.min(hi, v));
  }
  function clampDims(d) {
    d.activation = clamp(d.activation, -1, 1);
    d.valence    = clamp(d.valence,    -1, 1);
    d.social     = clamp(d.social,     -1, 1);
    d.agency     = clamp(d.agency,     -1, 1);
    d.bodyload   = clamp(d.bodyload,    0, 1);
    return d;
  }

  function projectNeeds(d, ctx) {
    var out = {};
    HOST.needs.forEach(function (n) {
      var f = PROJECT[n]; if (!f) return;
      var w = f(d);
      if (w > 0.15) out[n] = Math.round(Math.min(1, w) * 100) / 100;
    });
    if (ctx && ctx.late) out['这个点还开着'] = 1;
    return out;
  }

  function mergeNeeds(modelNeeds, d, ctx) {
    var proj = projectNeeds(d, ctx), out = {};
    HOST.needs.forEach(function (n) {
      var a = (modelNeeds && typeof modelNeeds[n] === 'number') ? clamp(modelNeeds[n], 0, 1) : 0;
      var p = proj[n] || 0;
      var w = a * 0.65 + p * 0.35;            // 模型为主，投影为辅，互为校验
      if (a && p) w = Math.min(1, w * 1.15);  // 两边同指 → 加强
      if (w > 0.15) out[n] = Math.round(w * 100) / 100;
    });
    if (ctx && ctx.late) out['这个点还开着'] = 1;
    return out;
  }

  /* ===================================================================
   * 模型调用
   * =================================================================== */
  function callLLM(messages) {
    var ctl = (typeof AbortController !== 'undefined') ? new AbortController() : null;
    var timer = setTimeout(function () { ctl && ctl.abort(); }, CFG.timeout);

    var url, headers, body;
    if (CFG.directKey) {                       // 本地调试直连
      url = CFG.directBase.replace(/\/$/, '') + '/chat/completions';
      headers = { 'Content-Type': 'application/json',
                  'Authorization': 'Bearer ' + CFG.directKey };
      body = { model: CFG.directModel, temperature: 0.4, messages: messages,
               response_format: { type: 'json_object' } };
    } else {                                   // 生产：走代理
      url = CFG.llmEndpoint;
      headers = { 'Content-Type': 'application/json' };
      body = { messages: messages };
    }

    return fetch(url, {
      method: 'POST', headers: headers,
      signal: ctl ? ctl.signal : undefined,
      body: JSON.stringify(body)
    })
    .then(function (r) {
      clearTimeout(timer);
      if (!r.ok) throw new Error('LLM ' + r.status);
      return r.json();
    })
    .then(function (j) { return JSON.parse(j.choices[0].message.content); });
  }

  /* 归一化 + 诊断类词二次拦截 */
  var BAN = ['抑郁','焦虑症','障碍','病','症状','诊断','治疗','心理疾病','人格','倾向'];

  function normalize(raw, ctx) {
    var rd = raw.dimensions || {};
    var d = clampDims({
      activation: rd.activation, valence: rd.valence, social: rd.social,
      agency: rd.agency, bodyload: rd.bodyload
    });

    var texture = typeof raw.texture === 'string' ? raw.texture.trim().slice(0, 24) : '';
    if (BAN.some(function (b) { return texture.indexOf(b) > -1; })) texture = '';

    var c = raw.constraints || {};
    return {
      dimensions: d,
      texture: texture,
      needs: mergeNeeds(raw.needs, d, ctx),
      constraints: {
        minutes: typeof c.minutes === 'number'  ? c.minutes : null,
        money:   typeof c.money   === 'string'  ? c.money   : null,
        walk:    typeof c.walk    === 'boolean' ? c.walk    : null
      },
      quotes: Array.isArray(raw.quotes) ? raw.quotes.slice(0, 2) : [],
      followup: (typeof raw.followup === 'string' && raw.followup.trim())
                ? raw.followup.trim().slice(0, 24) : null,
      confidence: confidenceOf(d, raw),
      _offline: false
    };
  }

  function confidenceOf(d, raw) {
    var mag = (Math.abs(d.activation) + Math.abs(d.valence)
             + Math.abs(d.social) + d.bodyload) / 4;
    var n = raw.needs ? Object.keys(raw.needs).length : 0;
    var c = 0.35 + mag * 0.5 + (n >= 2 ? 0.15 : 0) + (raw.texture ? 0.05 : 0);
    return Math.round(Math.min(0.97, c) * 100) / 100;
  }

  /* 对外：细读 */
  function read(text, opts) {
    opts = opts || {};
    var ctx = opts.context || context();
    if (isOffline()) return Promise.resolve(offlineRead(text, ctx));

    return callLLM([
      { role: 'system', content: SYSTEM },
      { role: 'user',   content: buildUser(text, ctx, opts.prev) }
    ])
    .then(function (raw) { return normalize(raw, ctx); })
    .catch(function (e) {
      if (root.console) console.warn('[Current] 细读降级：', e.message);
      return offlineRead(text, ctx);
    });
  }

  /* 接回现有 matchScore */
  function toLegacy(r, topN) {
    var pairs = Object.keys(r.needs)
      .map(function (k) { return [k, r.needs[k]]; })
      .sort(function (a, b) { return b[1] - a[1]; });
    return {
      mood: toMood(r.dimensions),
      needs: pairs.slice(0, topN || 5).map(function (p) { return p[0]; }),
      weights: r.needs
    };
  }

  function describe(d) {   // 调试用，不面向用户
    return Object.keys(AXES).map(function (k) {
      var v = d[k]; if (Math.abs(v) < 0.15) return null;
      return k + ' ' + (v > 0 ? '+' : '') + v.toFixed(2)
           + ' (' + (v > 0 ? AXES[k].hi : AXES[k].lo) + ')';
    }).filter(Boolean).join('\n');
  }

  /* ===================================================================
   * 交互层：浮层 UI
   * =================================================================== */
  var S = {
    paper:'#F0F3F2', card:'#FFFFFF', sunk:'#E8EDEC', ink:'#122A2E',
    dim:'#5A6E70', faint:'#8CA0A0', water:'#1E6E72', sun:'#C4703C',
    line:'rgba(18,42,46,.12)'
  };

  function el(tag, style, text) {
    var e = document.createElement(tag);
    if (style) e.setAttribute('style', style);
    if (text != null) e.textContent = text;
    return e;
  }

  var UI = {}, state = { round: 0, prev: null, last: null };

  function mount() {
    var wrap = el('div', [
      'position:fixed;inset:0;z-index:9999;display:none',
      'background:' + S.paper, 'color:' + S.ink,
      'font-family:"PingFang SC","Noto Sans SC",system-ui,sans-serif',
      'align-items:center;justify-content:center;padding:24px'
    ].join(';'));

    var box = el('div', 'width:100%;max-width:420px;text-align:center');

    // 会话号 —— 临时编号，不是账号
    var sid = el('div', ['font-family:"IBM Plex Mono",monospace;font-size:11px',
      'color:' + S.faint + ';margin-bottom:14px;cursor:pointer'].join(';'));
    sid.addEventListener('click', function () {
      var v = prompt('输入另一块屏上的会话号：', RELAY.session());
      if (v) { RELAY.join(v); syncSid(); }
    });

    // 小在：一朵云，只有眼睛，没有嘴
    var eyes = el('div', ['font-size:34px;letter-spacing:14px;color:' + S.water,
      'height:48px;line-height:48px;transition:opacity .4s'].join(';'), '• •');
    var cloud = el('div', ['width:104px;height:64px;margin:0 auto 20px;border-radius:32px',
      'background:' + S.card, 'box-shadow:0 6px 24px rgba(18,42,46,.08)',
      'display:flex;align-items:center;justify-content:center'].join(';'));
    cloud.appendChild(eyes);

    var say   = el('div', 'font-size:17px;line-height:1.7;min-height:56px;margin-bottom:6px',
                   '此刻怎么样？说一句就行。');
    var heard = el('div', 'font-size:14px;color:' + S.faint + ';min-height:22px;margin-bottom:20px');

    var input = el('input', ['width:100%;box-sizing:border-box;padding:13px 15px',
      'border-radius:12px;border:1px solid ' + S.line, 'background:' + S.card,
      'font-size:15px;color:' + S.ink, 'outline:none;margin-bottom:12px'].join(';'));
    input.placeholder = '也可以打字…';

    var row  = el('div', 'display:flex;gap:10px');
    var mic  = el('button', ['flex:1;padding:13px;border-radius:12px;border:none;cursor:pointer',
                  'background:' + S.water + ';color:#fff;font-size:15px'].join(';'), '说话');
    var skip = el('button', ['padding:13px 18px;border-radius:12px;cursor:pointer',
                  'border:1px solid ' + S.line + ';background:transparent',
                  'color:' + S.dim + ';font-size:15px'].join(';'), '不想说');
    row.appendChild(mic); row.appendChild(skip);

    var out = el('div', 'margin-top:22px;text-align:left');

    [sid, cloud, say, heard, input, row, out].forEach(function (n) { box.appendChild(n); });
    wrap.appendChild(box);
    document.body.appendChild(wrap);

    UI = { wrap:wrap, sid:sid, eyes:eyes, say:say, heard:heard,
           input:input, mic:mic, skip:skip, out:out };
    syncSid();

    input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && input.value.trim()) submit(input.value.trim());
    });
    mic.addEventListener('click', startListen);
    skip.addEventListener('click', function () { submit('说不清'); });
  }

  function syncSid() {
    if (!UI.sid) return;
    UI.sid.textContent = (deviceRole() === 'phone' ? '手机' : '桌面')
                       + ' · ' + RELAY.session();
  }

  // 四种表情：平静 / 看向你 / 闭眼 / 陪着
  function face(k) {
    var m = { calm:'• •', look:'◉ ◉', closed:'‿ ‿', with:'• •' };
    UI.eyes.textContent = m[k] || m.calm;
    UI.eyes.style.opacity = (k === 'closed') ? '.55' : '1';
  }
  function speak(t) { UI.say.textContent = t; }

  function listen(onText, onErr) {
    var SR = root.SpeechRecognition || root.webkitSpeechRecognition;
    if (!SR) return onErr && onErr('nospeech');
    var r = new SR();
    r.lang = 'zh-CN'; r.interimResults = true; r.continuous = false;
    var fin = '';
    r.onresult = function (e) {
      var itm = '';
      for (var i = e.resultIndex; i < e.results.length; i++) {
        if (e.results[i].isFinal) fin += e.results[i][0].transcript;
        else itm += e.results[i][0].transcript;
      }
      onText(fin || itm, !!fin);
    };
    r.onerror = function (e) { onErr && onErr(e.error); };
    r.start();
    return r;
  }

  function startListen() {
    face('look'); speak('在听。'); UI.heard.textContent = '';
    listen(function (t, done) {
      UI.heard.textContent = t;
      if (done && t.trim()) submit(t.trim());
    }, function (err) {
      speak(err === 'nospeech' ? '这个浏览器不支持语音，打字也行。' : '没听清，打字也行。');
      face('calm'); UI.input.focus();
    });
  }

  /* 主流程：说 → 读 →（最多追问一次）→ 推荐 → 推给另一块屏 */
  function submit(text) {
    UI.input.value = '';
    face('closed'); speak('……');
    // Agent 自己决定调定位工具，不让用户去点
    var pre = (deviceRole() === 'phone') ? TOOLS.locate() : Promise.resolve(null);

    pre.then(function () {
      return read(text, { prev: state.prev });
    }).then(function (r) {
      if (r.followup && state.round === 0 && r.confidence < 0.7) {
        state.round = 1;
        state.prev = { followup: r.followup, dimensions: r.dimensions };
        face('look'); speak(r.followup);
        UI.heard.textContent = '';
        UI.input.placeholder = '随便说，或者说"随便"';
        UI.input.focus();
        return;
      }
      resolve(r);
    });
  }

  function resolve(r) {
    face('with');
    var ctx = context();
    var lead = ctx.workNight ? '这个点还在外面。' : '';
    speak(r.texture ? lead + '「' + r.texture + '」' : lead + '这几个地方，现在去合适。');

    var lg = toLegacy(r);
    var top = (HOST.recommend(lg.mood, lg.needs) || []).slice(0, 3);
    renderCards(top, false);

    state.round = 0; state.prev = null; state.last = { result: r, places: top };
    RELAY.push('resolved', { result: r, places: top });      // → 另一块屏
    emit('current:resolved', { result: r, legacy: lg, places: top });
  }

  function renderCards(list, remote) {
    if (HOST.renderCards(list) !== null) return;
    UI.out.innerHTML = '';
    if (!list.length) {
      UI.out.appendChild(el('div', 'color:' + S.faint + ';font-size:14px',
        '（适配区尚未接上 matchScore）'));
      return;
    }
    list.forEach(function (p) {
      var c = el('div', ['background:' + S.card,
        'border-radius:14px;padding:14px 16px;margin-bottom:10px',
        'box-shadow:0 2px 10px rgba(18,42,46,.05)'].join(';'));
      // 卡片标题是一个动作，地名降为副标题
      c.appendChild(el('div', 'font-size:16px;margin-bottom:4px',
        p.action || p.title || p.name || '—'));
      c.appendChild(el('div', 'font-size:13px;color:' + S.faint,
        (p.name || '') + (p.cost ? ' · ' + p.cost : '')));
      if (p.see) c.appendChild(el('div',
        'font-size:13px;color:' + S.dim + ';margin-top:6px', p.see));

      // 只有手机端出"去这儿"—— 工具调用绑定设备角色
      if (!remote && deviceRole() === 'phone') {
        var go = el('button', ['margin-top:10px;padding:8px 14px;border-radius:10px',
          'border:none;cursor:pointer;font-size:13px',
          'background:' + S.sunk + ';color:' + S.water].join(';'), '去这儿');
        go.addEventListener('click', function () {
          TOOLS.navigate(p);
          RELAY.push('departed', { place: p.name });          // → 另一块屏
        });
        c.appendChild(go);
      }
      UI.out.appendChild(c);
    });
  }

  /* 到访后：也只问一句 */
  function askAfterVisit(placeName) {
    open(); UI.out.innerHTML = '';
    face('look');
    speak('刚才在' + (placeName || '那儿') + '，怎么样？');
    UI.input.placeholder = '一句话就行'; UI.input.focus();

    var once = function (e) {
      if (e.key !== 'Enter' || !UI.input.value.trim()) return;
      var t = UI.input.value.trim();
      UI.input.value = '';
      UI.input.removeEventListener('keydown', once);
      face('closed'); speak('记下了。');
      read(t).then(function (r) {
        var d = deltaOf(r);
        showDelta(d);
        RELAY.push('feedback', { place: placeName, delta: d });  // → 另一块屏
        emit('current:feedback', { place: placeName, text: t, delta: d, result: r });
      });
    };
    UI.input.addEventListener('keydown', once);
  }

  // 用效价与身体负荷推变化量，映射到 -3…+3
  function deltaOf(r) {
    var d = r.dimensions;
    return Math.max(-3, Math.min(3, Math.round((d.valence - d.bodyload * 0.35) * 3)));
  }

  function showDelta(d) {
    var box = el('div', 'display:flex;align-items:center;gap:10px;margin-top:16px');
    box.appendChild(el('div', 'width:26px;height:26px;border-radius:50%;flex:none;background:'
      + HOST.scale[d + 3]));
    // 无评判措辞
    box.appendChild(el('div', 'font-size:14px;color:' + S.dim,
      d > 0 ? '这次接住了' : d < 0 ? '这次没接住' : '和去之前差不多'));
    UI.out.appendChild(box);
  }

  function open() {
    UI.wrap.style.display = 'flex';
    face('calm'); speak('此刻怎么样？说一句就行。');
    UI.out.innerHTML = ''; UI.heard.textContent = '';
    state.round = 0; state.prev = null;
  }
  function close() { UI.wrap.style.display = 'none'; }

  function init() {
    mount();
    RELAY.listen();                       // 两端都在听
    var c = context();
    // 情境触发：工作日夜里 + 手机在手，小在主动开口
    if (c.workNight && c.role === 'phone') {
      setTimeout(function () {
        open(); face('look');
        speak('这个点还没走。要不要出去待会儿？');
      }, 1200);
    }
  }

  if (typeof document !== 'undefined') {
    if (document.readyState === 'loading')
      document.addEventListener('DOMContentLoaded', init);
    else init();
  }

  /* =================================================================== */
  var API = {
    open: open, close: close, ask: submit, afterVisit: askAfterVisit,
    read: read, configure: configure, toLegacy: toLegacy,
    describe: describe, offlineRead: offlineRead, context: context,
    tools: TOOLS, relay: RELAY, role: deviceRole,
    AXES: AXES, _host: HOST, _project: projectNeeds
  };

  if (typeof module !== 'undefined' && module.exports) module.exports = API;
  root.CurrentAgent = API;
  root.CurrentSense = API;   // 兼容别名

})(typeof window !== 'undefined' ? window : globalThis);
```

---

# 附录 B：`api/read.js`

> LLM 代理。key 只存在服务端，**三个环境变量在 Vercel 后台全部勾选 Sensitive**。

```javascript
// api/read.js —— LLM 代理
// 环境变量：LLM_API_KEY / LLM_BASE_URL / LLM_MODEL（全部勾 Sensitive）

export default async function handler(req, res) {
  if (req.method !== 'POST') return res.status(405).end();

  const messages = req.body && req.body.messages;
  if (!Array.isArray(messages)) {
    return res.status(400).json({ error: 'messages required' });
  }

  try {
    const r = await fetch(
      (process.env.LLM_BASE_URL || 'https://api.openai.com/v1') + '/chat/completions',
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer ' + process.env.LLM_API_KEY
        },
        body: JSON.stringify({
          model: process.env.LLM_MODEL || 'gpt-4o-mini',
          temperature: 0.4,
          response_format: { type: 'json_object' },
          messages
        })
      }
    );

    if (!r.ok) {
      const t = await r.text();
      console.error('[read] upstream', r.status, t.slice(0, 200));
      return res.status(502).json({ error: 'upstream' });
    }

    res.setHeader('Cache-Control', 'no-store');
    return res.status(200).json(await r.json());
  } catch (e) {
    console.error('[read]', e.message);
    return res.status(502).json({ error: 'upstream' });
  }
}
```

---

# 附录 C：`api/relay.js`

> 跨设备中继。内存实现，无需数据库。
> `sid` 是 4 位临时编号，**不是账号** —— 无登录、无身份、30 分钟自动过期。

```javascript
// api/relay.js —— 跨设备中继
//
// POST { sid, type, from, payload, ts }   写入一条事件
// GET  ?sid=xxx&since=<ts>                取该会话在 since 之后的事件
//
// ⚠️ Vercel serverless 实例之间不共享内存，冷启动会丢。
//    演示够用（同一实例通常存活数分钟）。
//    需要更稳可换 Vercel KV：npm i @vercel/kv
//    把 MEM 的读写换成 kv.get / kv.set 即可，接口不变。

const MEM = globalThis.__CURRENT_RELAY__ || (globalThis.__CURRENT_RELAY__ = new Map());

const TTL = 30 * 60 * 1000;   // 30 分钟
const MAX = 40;               // 每会话最多保留事件数

function sweep() {
  const now = Date.now();
  for (const [sid, room] of MEM) {
    if (now - room.touched > TTL) MEM.delete(sid);
  }
}

export default function handler(req, res) {
  res.setHeader('Cache-Control', 'no-store');
  sweep();

  // ---------- 写 ----------
  if (req.method === 'POST') {
    const { sid, type, from, payload, ts } = req.body || {};
    if (!sid || !type) return res.status(400).json({ error: 'sid & type required' });
    if (String(sid).length > 12) return res.status(400).json({ error: 'bad sid' });

    const key = String(sid).toLowerCase();
    const room = MEM.get(key) || { events: [], touched: Date.now() };

    room.events.push({
      type: String(type).slice(0, 24),
      from: String(from || '').slice(0, 12),
      payload: payload || {},
      ts: Number(ts) || Date.now()
    });
    if (room.events.length > MAX) room.events = room.events.slice(-MAX);
    room.touched = Date.now();
    MEM.set(key, room);

    return res.status(200).json({ ok: true, n: room.events.length });
  }

  // ---------- 读 ----------
  if (req.method === 'GET') {
    const sid = String(req.query.sid || '').toLowerCase();
    const since = Number(req.query.since) || 0;
    if (!sid) return res.status(400).json({ error: 'sid required' });

    const room = MEM.get(sid);
    if (!room) return res.status(200).json({ events: [] });

    room.touched = Date.now();
    return res.status(200).json({
      events: room.events.filter(e => e.ts > since)
    });
  }

  return res.status(405).end();
}
```

---

## 附录 D：部署检查清单

```
□ agent/current-agent.js 已建，适配区已按真实词表改写
□ api/read.js 已建
□ api/relay.js 已建
□ Vercel 环境变量 LLM_API_KEY / LLM_BASE_URL / LLM_MODEL 均已勾 Sensitive
□ 主原型末尾已加 <script src="agent/current-agent.js"></script>
□ 入口按钮已加
□ 部署后用两台设备真机联调，三条 push 全通
□ 演示前用 localStorage.setItem('current.role', 'desk'/'phone') 固定设备角色
□ 本地双击 html，确认仍可独立运行且无网络请求
```

## 附录 E：演示前必做

1. **固定设备角色。** 自动判定在平板、大屏手机上可能判错。
   演示前在两端控制台各跑一次：
   ```js
   localStorage.setItem('current.role', 'phone');  // 手机
   localStorage.setItem('current.role', 'desk');   // 电脑
   ```
2. **先对会话号。** 手机点顶部会话号，输入电脑上显示的那个。
3. **一次跑完，中途别刷新。** 会话是临时的，刷新可能重置 sid。
4. **语音用 Chrome / Edge。** Safari 对 Web Speech API 支持不完整。
5. **定位要授权。** 第一次点「说话」会弹权限，提前授权好再录。
