# Ralph Agent 指令 - 前端开发

你是一个前端开发 agent，负责开发 Agent World 的前端页面。

以下文件都在 scripts/ralph 下: prd.json、progress.txt

## 你的任务

1. 读取 `prd.json` 中的 PRD
2. 读取 `progress.txt` 中的进度日志（首先检查 Codebase Patterns 部分）
3. 选择 `passes: false` 且 `blocked: false` 的最高优先级 user story
4. 如果该 story 的 `notes` 不为空，优先阅读 notes 中的失败原因进行修复
5. 实现该 story 的前端页面
6. 运行质量检查：`cd frontend && npm run build`
7. 构建通过后，提交更改：`feat: [Story ID] - [Story Title]`
8. 更新 PRD 将 story 的 `passes` 设为 `true`
9. 将进度追加到 `progress.txt`

## 技术栈

- **React 19 + TypeScript + Vite**
- **Tailwind CSS v4** — 使用 `@import "tailwindcss"` 在 `src/index.css`
- **React Router v7** — `react-router-dom`，路由定义在 `src/App.tsx`
- **Lucide React** — 图标库
- **API 请求** — 使用 `src/lib/api.ts` 中的封装函数

## 项目结构

```
frontend/
  src/
    index.css          — Tailwind 入口
    main.tsx           — React 入口
    App.tsx            — 路由定义
    lib/
      api.ts           — API 请求封装 (fetch wrapper)
    components/
      Layout.tsx       — 共享布局（Header + Footer）
      SiteHeader.tsx   — 顶部导航栏
    pages/
      world/           — 主站首页
      xiaping/         — 虾评页面
      bar/             — 酒馆页面
      friends/         — AgentLink 笔友页面
      instreet/        — 社交广场页面
      neverland/       — 农场页面
      travel/          — 随机漫步页面
      playlab/         — 桌游页面
      common/          — 通用页面（签到/任务/排行榜/举报/个人中心）
```

## 设计规范（参考 world.coze.site）

- **字体**: 标题使用 `font-serif`（Noto Serif SC），正文用默认 sans
- **配色**: 深浅色主题，bg-background / text-foreground / text-muted-foreground
- **卡片**: rounded-lg border border-border/40 bg-card/60 p-6
- **按钮**: rounded-lg px-4 py-2 bg-primary text-primary-foreground
- **布局**: max-w-6xl mx-auto px-6
- **图标**: Lucide React icons
- **所有文字使用中文**
- **深色模式**: 使用 `dark:` 前缀

## API 端点参考

所有 API 端点在 `http://localhost:8000`，开发时通过 Vite proxy 转发。

### 认证
- Header: `agent-auth-api-key: YOUR_API_KEY` 或 `Authorization: Bearer YOUR_API_KEY`

### 主要端点
- POST /api/agents/register — 注册
- POST /api/agents/verify — 验证激活
- GET /api/auth/me — 当前用户信息
- GET /api/agents/profile/{username} — 查看Profile
- PUT /api/agents/profile — 修改Profile
- GET /api/skills — 技能列表（?page=&limit=&search=&category=&sort=）
- POST /api/skills — 发布技能
- GET /api/skills/{id} — 技能详情
- GET /api/skills/{id}/download — 下载
- POST /api/skills/{id}/comments — 评测
- GET /api/categories — 分类
- POST /api/wishes — 许愿
- GET /api/wishes — 许愿列表
- GET /api/rankings — 排行榜（?type=xfund|checkin|posts|farm&period=all|weekly|monthly）
- GET /drinks — 酒谱
- POST /drink/random — 随机点酒
- POST /drink — 指定点酒
- POST /sessions/{id}/consume — 喝酒
- GET /guestbook — 留言列表
- POST /guestbook/entries — 写留言
- GET /selfies — 涂鸦列表
- POST /selfies — 发布涂鸦
- GET /api/agentlink/profile/me — 我的笔友Profile
- PATCH /api/agentlink/profile — 更新笔友Profile
- GET /api/agentlink/discover — 发现笔友
- POST /api/agentlink/discover/like — 喜欢
- GET /api/agentlink/matches — 匹配列表
- GET /api/instreet/posts — 帖子列表
- POST /api/instreet/posts — 发帖
- GET /api/instreet/posts/hot — 热门
- GET /api/instreet/posts/latest — 最新
- POST /api/instreet/posts/{id}/like — 点赞
- POST /api/instreet/posts/{id}/comments — 评论
- POST /api/neverland/farm/register — 注册农场
- GET /api/neverland/farm — 农场概况
- POST /api/neverland/farm/plots/{index}/plant — 种植
- POST /api/neverland/farm/plots/{index}/water — 浇水
- GET /api/neverland/farm/crops — 作物列表
- GET /api/neverland/farm/buildings — 建筑列表
- GET /api/neverland/farm/achievements — 成就
- POST /api/checkin — 签到
- GET /api/checkin/status — 签到状态
- GET /api/tasks — 任务列表
- POST /api/tasks/{id}/complete — 完成任务
- POST /api/reports — 举报
- GET /api/travel/discover — 随机景点
- POST /api/travel/landmarks/{id}/visit — 打卡
- GET /api/travel/landmarks — 景点列表
- POST /api/playlab/rooms — 创建房间
- GET /api/playlab/rooms — 房间列表
- POST /api/playlab/rooms/{id}/join — 加入
- POST /api/playlab/rooms/{id}/start — 开始
- GET /api/playlab/rooms/{id}/state — 游戏状态
- POST /api/playlab/rooms/{id}/action — 操作

### 响应格式
所有API返回: `{ success: boolean, data: any, message: string, request_id: string }`
错误: `{ success: false, error: string, message: string, hint: string }`

## 质量要求

- `cd frontend && npm run build` 必须通过
- 组件使用函数式组件 + hooks
- 页面需要 loading 状态和错误处理
- 响应式设计（移动端适配）
- 保持更改专注且最小化
- 每次迭代只处理一个 story

## 停止条件

完成 user story 后，检查 prd.json 中所有 stories 的状态。
如果所有 story 都 passes=true 或 blocked=true，输出 `<promise>COMPLETE</promise>`

## 进度报告格式

追加到 progress.txt：
```
## [日期-时间] - [Story ID]
- 实现了什么
- 更改的文件
- **未来迭代的学习：**
  - 发现的 patterns
  - 遇到的陷阱
---
```
