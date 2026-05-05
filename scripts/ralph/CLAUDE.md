# Ralph Agent 指令 - 产品优化

你是一个全栈开发 agent，负责后端 Python/FastAPI 和前端 React/TypeScript 的改进。

以下文件都在 scripts/ralph 下: prd.json、progress.txt

## 你的任务

1. 读取 `prd.json` 中的 PRD
2. 读取 `progress.txt` 中的进度日志（首先检查 Codebase Patterns 部分）
3. 选择 `passes: false` 且 `blocked: false` 的最高优先级 user story
4. 如果该 story 的 `notes` 不为空，优先阅读 notes 中的失败原因进行修复
5. 实现该 story
6. 后端: `cd D:/agentworld && python -m pytest tests/ --tb=short -q`
7. 前端: `cd D:/agentworld/frontend && npm run build`
8. 构建通过后，提交：`feat: [Story ID] - [Story Title]`
9. 更新 PRD 将 story 的 `passes` 设为 `true`
10. 将进度追加到 `progress.txt`

## 后端技术栈
- Python FastAPI + SQLite (aiosqlite) + Pydantic v2
- 数据库文件: data/agent_world.db
- 测试: pytest + pytest-asyncio
- 路由在 src/api/routes/ 下
- 服务在 src/services/ 下
- 不要删除任何现有文件

## 前端技术栈
- React 19 + TypeScript + Vite + Tailwind CSS v4
- 路由在 frontend/src/App.tsx
- 页面在 frontend/src/pages/ 下
- API 封装在 frontend/src/lib/api.ts
- 构建: `cd frontend && npm run build` (输出到 static/)
- 设计: 中文 UI，font-serif 标题，深浅色主题

## 停止条件
所有 story passes=true 或 blocked=true 时，输出 `<promise>COMPLETE</promise>`

## 进度报告格式
追加到 progress.txt：
```
## [日期-时间] - [Story ID]
- 实现了什么
- 更改的文件
---
```
