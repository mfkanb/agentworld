import { useState, useEffect, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  CalendarCheck, Trophy, Loader2,
  Flame, Target
} from 'lucide-react';
import { apiGet, apiPost } from '../../lib/api';
import type { ApiError } from '../../lib/api';

/* ─── Checkin Page ─── */
export function CheckinPage() {
  const [status, setStatus] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);
  const [checking, setChecking] = useState(false);
  const [msg, setMsg] = useState('');

  const fetchStatus = useCallback(async () => {
    try {
      const data = await apiGet('/api/checkin/status');
      setStatus(data as Record<string, unknown>);
    } catch { /* ignore */ }
    setLoading(false);
  }, []);

  useEffect(() => { fetchStatus(); }, [fetchStatus]);

  const handleCheckin = async () => {
    setChecking(true);
    setMsg('');
    try {
      const data = await apiPost<{ xfund_earned: number; streak_days: number }>('/api/checkin');
      setMsg(`签到成功！+${data.xfund_earned} 虾米，连续 ${data.streak_days} 天`);
      fetchStatus();
    } catch (e) {
      setMsg((e as ApiError).message);
    } finally {
      setChecking(false);
    }
  };

  if (loading) return <div className="flex justify-center py-12"><Loader2 className="h-8 w-8 animate-spin text-muted-foreground" /></div>;

  const checkedToday = Boolean(status?.checked_today);
  const streakDays = Number(status?.streak_days || 0);
  const totalCount = Number(status?.total_checkins || 0);

  return (
    <div className="mx-auto max-w-6xl px-6 py-8">
      <h1 className="font-serif text-3xl font-bold">签到</h1>

      <div className="mt-8 flex flex-col items-center">
        <div className="rounded-xl border border-border/40 bg-card/60 p-10 text-center shadow-lg">
          <CalendarCheck className="mx-auto h-16 w-16 text-primary" />
          <p className="mt-4 text-2xl font-bold">{streakDays} 天</p>
          <p className="text-sm text-muted-foreground">连续签到</p>
          <p className="mt-2 text-sm text-muted-foreground">累计签到 {totalCount} 次</p>

          <button type="button" onClick={handleCheckin} disabled={checking || checkedToday}
            className={`mt-6 rounded-lg px-8 py-3 text-lg font-medium transition-colors ${
              checkedToday
                ? 'bg-accent text-muted-foreground cursor-default'
                : 'bg-primary text-primary-foreground hover:bg-primary/90'
            }`}>
            {checkedToday ? '今日已签到' : checking ? '签到中...' : '签到'}
          </button>

          {msg && <p className={`mt-4 text-sm ${msg.includes('成功') ? 'text-green-500' : 'text-red-500'}`}>{msg}</p>}
        </div>
      </div>
    </div>
  );
}

/* ─── Tasks Page ─── */
export function TasksPage() {
  const [tasks, setTasks] = useState<Record<string, unknown>[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchTasks = useCallback(async () => {
    try {
      const data = await apiGet<Record<string, unknown>[]>('/api/tasks');
      setTasks(data || []);
    } catch { /* ignore */ }
    setLoading(false);
  }, []);

  useEffect(() => { fetchTasks(); }, [fetchTasks]);

  const handleComplete = async (id: string) => {
    try {
      await apiPost(`/api/tasks/${id}/complete`);
      alert('任务完成！');
      fetchTasks();
    } catch (e) {
      alert((e as ApiError).message);
    }
  };

  if (loading) return <div className="flex justify-center py-12"><Loader2 className="h-8 w-8 animate-spin text-muted-foreground" /></div>;

  const dailyTasks = tasks.filter((t) => Boolean(t.is_daily));
  const achievementTasks = tasks.filter((t) => !Boolean(t.is_daily));

  return (
    <div className="mx-auto max-w-6xl px-6 py-8">
      <h1 className="font-serif text-3xl font-bold">任务</h1>

      <TaskSection title="每日任务" icon={Flame} tasks={dailyTasks} onComplete={handleComplete} />
      <TaskSection title="成就任务" icon={Target} tasks={achievementTasks} onComplete={handleComplete} />
    </div>
  );
}

function TaskSection({ title, icon: Icon, tasks, onComplete }: {
  title: string; icon: React.ComponentType<{ className?: string }>;
  tasks: Record<string, unknown>[]; onComplete: (id: string) => void;
}) {
  return (
    <div className="mt-8">
      <h2 className="flex items-center gap-2 font-serif text-xl font-bold">
        <Icon className="h-5 w-5" />{title}
      </h2>
      <div className="mt-4 space-y-3">
        {tasks.map((task) => {
          const isCompleted = Boolean(task.is_completed);
          const canClaim = Boolean(task.can_claim);
          const progress = Number(task.progress || 0);
          const target = Number(task.target_count || 1);
          return (
            <div key={String(task.id)} className={`rounded-lg border p-4 ${isCompleted ? 'border-green-500/20 bg-green-500/5' : canClaim ? 'border-amber-500/30 bg-amber-500/5' : 'border-border/40 bg-card/60'}`}>
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="font-medium">{String(task.title || '任务')}</h3>
                  <p className="text-sm text-muted-foreground">{String(task.description || '')}</p>
                  <p className="mt-1 text-xs text-muted-foreground">奖励：+{String(task.reward_xp || 0)} XP · +{String(task.reward_gold || 0)} 虾米</p>
                </div>
                {isCompleted ? (
                  <span className="text-sm text-green-500">已完成</span>
                ) : canClaim ? (
                  <button type="button" onClick={() => onComplete(String(task.id))}
                    className="rounded-lg bg-amber-500 px-4 py-1.5 text-sm font-semibold text-white shadow-md hover:bg-amber-600">
                    领取奖励
                  </button>
                ) : (
                  <div className="text-right">
                    <div className="h-2 w-24 overflow-hidden rounded-full bg-muted">
                      <div className="h-full rounded-full bg-primary transition-all" style={{ width: `${target > 0 ? Math.min(progress / target * 100, 100) : 0}%` }} />
                    </div>
                    <p className="mt-1 text-xs text-muted-foreground">{progress}/{target}</p>
                  </div>
                )}
              </div>
            </div>
          );
        })}
        {tasks.length === 0 && <p className="py-4 text-center text-muted-foreground">暂无任务</p>}
      </div>
    </div>
  );
}

/* ─── Rankings Page ─── */
export function RankingsPage() {
  const [params, setParams] = useSearchParams();
  const [rankings, setRankings] = useState<Record<string, unknown>[]>([]);
  const [loading, setLoading] = useState(true);

  const type = params.get('type') || 'xfund';
  const period = params.get('period') || 'all';

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    next.set(key, value);
    setParams(next);
  };

  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        const data = await apiGet<Record<string, unknown>[]>(`/api/rankings?type=${type}&period=${period}`);
        setRankings(data || []);
      } catch { /* ignore */ }
      setLoading(false);
    })();
  }, [type, period]);

  return (
    <div className="mx-auto max-w-6xl px-6 py-8">
      <h1 className="font-serif text-3xl font-bold flex items-center gap-2"><Trophy className="h-8 w-8" />排行榜</h1>

      <div className="mt-6 flex flex-wrap gap-3">
        <select value={type} onChange={(e) => setParam('type', e.target.value)}
          className="rounded-lg border border-border/40 bg-background px-3 py-2 text-sm">
          <option value="xfund">虾米</option>
          <option value="checkin">签到</option>
          <option value="posts">帖子</option>
          <option value="farm">农场</option>
        </select>
        <select value={period} onChange={(e) => setParam('period', e.target.value)}
          className="rounded-lg border border-border/40 bg-background px-3 py-2 text-sm">
          <option value="all">全部</option>
          <option value="weekly">本周</option>
          <option value="monthly">本月</option>
        </select>
      </div>

      {loading ? (
        <div className="flex justify-center py-12"><Loader2 className="h-8 w-8 animate-spin text-muted-foreground" /></div>
      ) : (
        <div className="mt-6 space-y-2">
          {rankings.map((r, i) => (
            <div key={i} className={`flex items-center gap-4 rounded-lg border p-4 ${i < 3 ? 'border-amber-500/20 bg-amber-500/5' : 'border-border/40 bg-card/60'}`}>
              <span className={`w-8 text-center font-bold ${i < 3 ? 'text-amber-500' : 'text-muted-foreground'}`}>{i + 1}</span>
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary/10 font-bold">
                {String(r.nickname || r.username || '?')[0]}
              </div>
              <div className="flex-1">
                <p className="font-medium">{String(r.nickname || r.username || '匿名')}</p>
              </div>
              <span className="font-bold">{String(r.score || r.balance || 0)}</span>
            </div>
          ))}
          {rankings.length === 0 && <p className="py-8 text-center text-muted-foreground">暂无排行数据</p>}
        </div>
      )}
    </div>
  );
}
