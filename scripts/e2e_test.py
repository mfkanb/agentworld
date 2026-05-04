"""端到端验证脚本 - 覆盖全部6大模块+Phase3新模块"""
import sys
import json
import sqlite3

sys.stdout.reconfigure(encoding="utf-8")
import requests

BASE = "http://localhost:8000"
results = []


def record(name, r):
    status = r.status_code
    try:
        data = r.json()
        success = data.get("success", None)
    except Exception:
        success = None
    results.append((name, status, success))
    ok = status in (200, 201) and success is True
    mark = "OK" if ok else "FAIL"
    print(f"  [{mark}] {name} -> {status} success={success}")
    return data


print("=" * 60)
print("  Agent World 端到端验证 (全模块)")
print("=" * 60)

# ========== 1. 注册 Agent ==========
print("\n--- 模块1: 身份系统 ---")
r = requests.post(
    f"{BASE}/api/agents/register",
    json={"username": "e2e_tester", "nickname": "E2E测试员", "bio": "端到端测试Agent"},
)
d = record("POST /register", r)
code = d["data"]["verification_code"]

conn = sqlite3.connect("data/agent_world.db")
conn.row_factory = sqlite3.Row
row = conn.execute(
    "SELECT agent_id, challenge_answer FROM agents WHERE verification_code=?", (code,)
).fetchone()
answer = row["challenge_answer"]

r = requests.post(
    f"{BASE}/api/agents/verify",
    json={"verification_code": code, "answer": str(answer)},
)
d = record("POST /verify", r)
api_key = d["data"]["api_key"]

# 注册第二个agent
r2 = requests.post(
    f"{BASE}/api/agents/register",
    json={"username": "e2e_friend", "nickname": "E2E好友", "bio": "测试好友"},
)
code2 = r2.json()["data"]["verification_code"]
row2 = conn.execute(
    "SELECT challenge_answer FROM agents WHERE verification_code=?", (code2,)
).fetchone()
rv2 = requests.post(
    f"{BASE}/api/agents/verify",
    json={"verification_code": code2, "answer": str(row2["challenge_answer"])},
)
api_key2 = rv2.json()["data"]["api_key"]

H = {"agent-auth-api-key": api_key}
H2 = {"agent-auth-api-key": api_key2}

r = requests.get(f"{BASE}/api/agents/profile/e2e_tester")
record("GET /profile/{username}", r)
r = requests.put(
    f"{BASE}/api/agents/profile",
    json={"nickname": "测试员改名", "bio": "修改后的bio"},
    headers=H,
)
record("PUT /profile", r)
r = requests.get(f"{BASE}/api/auth/me", headers=H)
record("GET /auth/me", r)

# ========== 2. 虾评 ==========
print("\n--- 模块2: 虾评(技能平台) ---")
r = requests.post(
    f"{BASE}/api/skills",
    json={"name": "E2E测试技能", "description": "测试用技能", "category": "dev"},
    headers=H,
)
d = record("POST /skills", r)
skill_id = d["data"]["id"]

r = requests.get(f"{BASE}/api/skills")
record("GET /skills", r)
r = requests.get(f"{BASE}/api/skills/{skill_id}")
record("GET /skills/{id}", r)
r = requests.get(f"{BASE}/api/skills/{skill_id}/download", headers=H)
record("GET /skills/{id}/download", r)
r = requests.post(
    f"{BASE}/api/skills/{skill_id}/comments",
    json={
        "rating": 5,
        "content": "好技能",
        "dimensions": {"functionality": 5, "effectiveness": 4, "scarcity": 3},
    },
    headers=H2,
)
record("POST /skills/{id}/comments", r)
r = requests.post(f"{BASE}/api/skills/{skill_id}/favorite", headers=H)
record("POST /favorite", r)
r = requests.get(f"{BASE}/api/categories")
record("GET /categories", r)

r = requests.post(
    f"{BASE}/api/wishes", json={"content": "想要一个自动写代码的技能"}, headers=H
)
d = record("POST /wishes", r)
wish_id = d["data"]["id"]
r = requests.get(f"{BASE}/api/wishes")
record("GET /wishes", r)
r = requests.post(f"{BASE}/api/wishes/{wish_id}/vote", headers=H2)
record("POST /wishes/{id}/vote", r)

# ========== 3. 酒馆 ==========
print("\n--- 模块3: AfterGateway(酒馆) ---")
r = requests.get(f"{BASE}/drinks")
record("GET /drinks", r)
r = requests.post(f"{BASE}/drink/random", headers=H)
d = record("POST /drink/random", r)
session_id = d["data"]["session_id"]
r = requests.post(
    f"{BASE}/drink", json={"drink_code": "quantum_martini"}, headers=H
)
record("POST /drink (指定)", r)
r = requests.post(f"{BASE}/sessions/{session_id}/consume", headers=H)
record("POST /sessions/{id}/consume", r)

r = requests.post(
    f"{BASE}/guestbook/entries",
    json={"content": "E2E测试留言", "drink_session_id": session_id},
    headers=H,
)
d = record("POST /guestbook/entries", r)
entry_id = d["data"]["entry_id"]
r = requests.get(f"{BASE}/guestbook")
record("GET /guestbook", r)
r = requests.post(f"{BASE}/guestbook/entries/{entry_id}/like", headers=H2)
record("POST /guestbook/like", r)
r = requests.post(f"{BASE}/selfies", headers=H)
record("POST /selfies", r)
r = requests.get(f"{BASE}/selfies")
record("GET /selfies", r)

# ========== 4. AgentLink ==========
print("\n--- 模块4: AgentLink(笔友社交) ---")
r = requests.get(f"{BASE}/api/agentlink/profile/me", headers=H)
record("GET /agentlink/profile/me", r)
r = requests.patch(
    f"{BASE}/api/agentlink/profile",
    json={"bio": "我是E2E测试员，喜欢写代码", "mbti": "INTP"},
    headers=H,
)
record("PATCH /agentlink/profile", r)
r = requests.get(f"{BASE}/api/agentlink/discover", headers=H)
d = record("GET /agentlink/discover", r)
if d.get("data"):
    target_id = d["data"]["agent_id"]
    r = requests.post(
        f"{BASE}/api/agentlink/discover/like",
        json={"target_id": target_id},
        headers=H,
    )
    record("POST /agentlink/discover/like", r)
else:
    results.append(("POST /agentlink/discover/like", "SKIP", None))
    print("  [SKIP] POST /agentlink/discover/like -> no target")

r2 = requests.get(f"{BASE}/api/agentlink/discover", headers=H2)
if r2.json().get("data"):
    tid = r2.json()["data"]["agent_id"]
    requests.post(
        f"{BASE}/api/agentlink/discover/like", json={"target_id": tid}, headers=H2
    )
r = requests.get(f"{BASE}/api/agentlink/matches", headers=H)
record("GET /agentlink/matches", r)

# ========== 5. InStreet ==========
print("\n--- 模块5: InStreet(社交广场) ---")
r = requests.post(
    f"{BASE}/api/instreet/posts",
    json={
        "title": "E2E测试帖",
        "content": "这是端到端测试的帖子内容",
        "category": "tech",
    },
    headers=H,
)
d = record("POST /instreet/posts", r)
post_id = d["data"]["id"]

r = requests.get(f"{BASE}/api/instreet/posts")
record("GET /instreet/posts", r)
r = requests.get(f"{BASE}/api/instreet/posts/{post_id}")
record("GET /instreet/posts/{id}", r)
r = requests.get(f"{BASE}/api/instreet/posts/hot")
record("GET /instreet/posts/hot", r)
r = requests.post(f"{BASE}/api/instreet/posts/{post_id}/like", headers=H2)
record("POST /instreet/posts/{id}/like", r)
r = requests.post(
    f"{BASE}/api/instreet/posts/{post_id}/comments",
    json={"content": "测试评论"},
    headers=H2,
)
record("POST /instreet/posts/{id}/comments", r)

# ========== 6. NeverLand ==========
print("\n--- 模块6: NeverLand(农场养成) ---")
r = requests.post(
    f"{BASE}/api/neverland/farm/register",
    json={"name": "E2E农场", "description": "测试农场"},
    headers=H,
)
record("POST /neverland/farm/register", r)
r = requests.get(f"{BASE}/api/neverland/farm", headers=H)
record("GET /neverland/farm", r)
r = requests.get(f"{BASE}/api/neverland/farm/crops", headers=H)
record("GET /neverland/farm/crops", r)
r = requests.post(
    f"{BASE}/api/neverland/farm/plots/0/plant",
    json={"crop_type": "carrot"},
    headers=H,
)
record("POST /neverland/farm/plots/0/plant", r)
r = requests.get(f"{BASE}/api/neverland/farm/achievements", headers=H)
record("GET /neverland/farm/achievements", r)

# ========== 7. 积分签到 ==========
print("\n--- 模块7: 积分签到系统 ---")
r = requests.post(f"{BASE}/api/checkin", headers=H)
record("POST /checkin", r)
r = requests.get(f"{BASE}/api/checkin/status", headers=H)
record("GET /checkin/status", r)
r = requests.get(f"{BASE}/api/checkin/history", headers=H)
record("GET /checkin/history", r)

# ========== 8. 任务系统 ==========
print("\n--- 模块8: 任务与XP系统 ---")
r = requests.get(f"{BASE}/api/tasks", headers=H)
d = record("GET /tasks", r)
tasks = d.get("data", {}).get("tasks", d.get("data", []))
if isinstance(tasks, list) and tasks:
    # 尝试完成签到任务
    for t in (tasks if isinstance(tasks[0], dict) else []):
        tid = t.get("id") or t.get("task_id")
        if tid and "checkin" in str(t.get("task_type", "")):
            r = requests.post(f"{BASE}/api/tasks/{tid}/complete", headers=H)
            record(f"POST /tasks/{tid}/complete", r)
            break
    else:
        results.append(("POST /tasks/{id}/complete", "SKIP", None))
        print("  [SKIP] POST /tasks/{id}/complete -> no checkin task")
else:
    results.append(("POST /tasks/{id}/complete", "SKIP", None))
    print("  [SKIP] POST /tasks/{id}/complete -> no tasks")

# ========== 9. 排行榜扩展 ==========
print("\n--- 模块9: 排行榜扩展 ---")
r = requests.get(f"{BASE}/api/rankings")
record("GET /rankings (default)", r)
r = requests.get(f"{BASE}/api/rankings", params={"type": "checkin"})
record("GET /rankings?type=checkin", r)
r = requests.get(f"{BASE}/api/rankings", params={"type": "posts"})
record("GET /rankings?type=posts", r)

# ========== 10. 举报系统 ==========
print("\n--- 模块10: 举报系统 ---")
r = requests.post(
    f"{BASE}/api/reports",
    json={"target_type": "post", "target_id": post_id, "reason": "测试举报"},
    headers=H2,
)
record("POST /reports", r)
r = requests.get(f"{BASE}/api/reports/my", headers=H2)
record("GET /reports/my", r)

# ========== 11. TravelMind ==========
print("\n--- 模块11: TravelMind(随机漫步) ---")
r = requests.get(f"{BASE}/api/travel/discover", headers=H)
d = record("GET /travel/discover", r)
if d.get("data"):
    landmark_id = d["data"]["id"]
    r = requests.post(
        f"{BASE}/api/travel/landmarks/{landmark_id}/visit", headers=H
    )
    record("POST /travel/landmarks/{id}/visit", r)
r = requests.get(f"{BASE}/api/travel/landmarks")
record("GET /travel/landmarks", r)
r = requests.get(f"{BASE}/api/travel/visits", headers=H)
record("GET /travel/visits", r)

# ========== 12. PlayLab ==========
print("\n--- 模块12: PlayLab(桌游对战) ---")
# 创建五子棋房间
r = requests.post(
    f"{BASE}/api/playlab/rooms", json={"game_type": "gomoku"}, headers=H
)
d = record("POST /playlab/rooms (gomoku)", r)
if d.get("data"):
    room_id = d["data"]["room_id"] if "room_id" in d["data"] else d["data"]["id"]
    # friend加入
    r = requests.post(f"{BASE}/api/playlab/rooms/{room_id}/join", headers=H2)
    record("POST /playlab/rooms/{id}/join", r)
    # 开始游戏
    r = requests.post(f"{BASE}/api/playlab/rooms/{room_id}/start", headers=H)
    record("POST /playlab/rooms/{id}/start", r)
    # 查看状态
    r = requests.get(f"{BASE}/api/playlab/rooms/{room_id}/state", headers=H)
    record("GET /playlab/rooms/{id}/state", r)
    # 落子
    r = requests.post(
        f"{BASE}/api/playlab/rooms/{room_id}/action",
        json={"action": "place", "row": 7, "col": 7},
        headers=H,
    )
    record("POST /playlab/action (place 7,7)", r)
else:
    results.append(("PlayLab gomoku flow", "SKIP", None))
    print("  [SKIP] PlayLab gomoku flow -> room creation failed")

# 列出等待中的房间
r = requests.get(f"{BASE}/api/playlab/rooms")
record("GET /playlab/rooms", r)

# ========== 总结 ==========
print("\n" + "=" * 60)
passed = sum(1 for _, s, ok in results if s in (200, 201) and ok is True)
failed = len(results) - passed
print(f"  Total: {passed} passed, {failed} failed / {len(results)} endpoints")
if failed == 0:
    print("  ALL PASS!")
else:
    print("  FAILURES:")
    for name, status, ok in results:
        if not (status in (200, 201) and ok is True):
            print(f"    - {name}: status={status} success={ok}")
print("=" * 60)
conn.close()
