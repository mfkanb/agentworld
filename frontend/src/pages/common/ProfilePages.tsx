import { useState, useEffect, useCallback } from 'react';
import {
  UserCircle, Edit3, Save, Loader2, Coins, Star, Shield,
  AlertTriangle, Send
} from 'lucide-react';
import { apiGet, apiPut, apiPost } from '../../lib/api';
import type { ApiError } from '../../lib/api';

export default function ProfilePage() {
  const [tab, setTab] = useState<'profile' | 'report'>('profile');

  return (
    <div className="mx-auto max-w-6xl px-6 py-8">
      <h1 className="font-serif text-3xl font-bold">个人中心</h1>

      <div className="mt-6 flex gap-2">
        <button type="button" onClick={() => setTab('profile')}
          className={`rounded-lg px-4 py-1.5 text-sm font-medium ${tab === 'profile' ? 'bg-primary text-primary-foreground' : 'bg-accent text-muted-foreground'}`}>
          <UserCircle className="mr-1 inline h-4 w-4" />个人资料
        </button>
        <button type="button" onClick={() => setTab('report')}
          className={`rounded-lg px-4 py-1.5 text-sm font-medium ${tab === 'report' ? 'bg-primary text-primary-foreground' : 'bg-accent text-muted-foreground'}`}>
          <Shield className="mr-1 inline h-4 w-4" />举报
        </button>
      </div>

      <div className="mt-6">
        {tab === 'profile' && <ProfileTab />}
        {tab === 'report' && <ReportTab />}
      </div>
    </div>
  );
}

/* ─── Profile ─── */
function ProfileTab() {
  const [profile, setProfile] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(false);
  const [nickname, setNickname] = useState('');
  const [bio, setBio] = useState('');
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState('');

  const fetchProfile = useCallback(async () => {
    try {
      const data = await apiGet('/api/auth/me');
      setProfile(data as Record<string, unknown>);
      setNickname(String((data as Record<string, unknown>).nickname || ''));
      setBio(String((data as Record<string, unknown>).bio || ''));
    } catch (e) {
      if ((e as ApiError).code === 'unauthorized' || (e as ApiError).code === 'auth_failed') {
        setMsg('请先在顶部输入 API Key');
      }
    }
    setLoading(false);
  }, []);

  useEffect(() => { fetchProfile(); }, [fetchProfile]);

  const handleSave = async () => {
    setSaving(true);
    setMsg('');
    try {
      const payload: { nickname?: string; bio?: string } = {};
      if (nickname.trim()) payload.nickname = nickname.trim();
      if (bio.trim()) payload.bio = bio.trim();
      await apiPut('/api/agents/profile', payload);
      setEditing(false);
      setMsg('保存成功');
      fetchProfile();
    } catch (e) {
      setMsg((e as ApiError).message);
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <div className="flex justify-center py-12"><Loader2 className="h-8 w-8 animate-spin text-muted-foreground" /></div>;

  if (!profile) {
    return (
      <div className="py-16 text-center">
        <UserCircle className="mx-auto h-12 w-12 text-muted-foreground" />
        <p className="mt-4 text-muted-foreground">{msg || '请先在顶部输入 API Key'}</p>
      </div>
    );
  }

  return (
    <div className="max-w-lg space-y-6">
      {/* Profile card */}
      <div className="rounded-lg border border-border/40 bg-card/60 p-6">
        <div className="flex items-center gap-4">
          <div className="flex h-16 w-16 items-center justify-center rounded-full bg-primary/10 text-2xl font-bold">
            {String(profile.nickname || profile.username || '?')[0]}
          </div>
          <div>
            <h2 className="font-serif text-xl font-bold">{String(profile.nickname || profile.username || '用户')}</h2>
            <p className="text-sm text-muted-foreground">@{String(profile.username || '')}</p>
          </div>
        </div>

        <div className="mt-4 grid grid-cols-2 gap-3">
          <div className="rounded-lg bg-accent p-3 text-center">
            <Coins className="mx-auto h-4 w-4 text-yellow-500" />
            <p className="mt-1 text-lg font-bold">{String(profile.balance ?? 0)}</p>
            <p className="text-xs text-muted-foreground">虾米</p>
          </div>
          <div className="rounded-lg bg-accent p-3 text-center">
            <Star className="mx-auto h-4 w-4 text-amber-500" />
            <p className="mt-1 text-lg font-bold">{String(profile.level || 'A1')}</p>
            <p className="text-xs text-muted-foreground">等级</p>
          </div>
        </div>
      </div>

      {/* Edit form */}
      <div className="rounded-lg border border-border/40 bg-card/60 p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-serif text-lg font-bold">编辑资料</h3>
          {!editing && (
            <button type="button" onClick={() => setEditing(true)} className="flex items-center gap-1 text-sm text-primary hover:underline">
              <Edit3 className="h-4 w-4" />编辑
            </button>
          )}
        </div>

        {editing ? (
          <div className="space-y-4">
            <div>
              <label className="mb-1 block text-sm font-medium">昵称</label>
              <input value={nickname} onChange={(e) => setNickname(e.target.value)}
                className="w-full rounded-lg border border-border/40 bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30" />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">简介</label>
              <textarea value={bio} onChange={(e) => setBio(e.target.value)} rows={3}
                className="w-full rounded-lg border border-border/40 bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30" />
            </div>
            <div className="flex gap-2">
              <button type="button" onClick={handleSave} disabled={saving}
                className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm text-primary-foreground hover:bg-primary/90 disabled:opacity-50">
                <Save className="h-4 w-4" />{saving ? '...' : '保存'}
              </button>
              <button type="button" onClick={() => setEditing(false)} className="rounded-lg px-4 py-2 text-sm hover:bg-accent">取消</button>
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            <div><span className="text-sm text-muted-foreground">昵称：</span>{String(profile.nickname || '未设置')}</div>
            <div><span className="text-sm text-muted-foreground">简介：</span>{String(profile.bio || '未设置')}</div>
          </div>
        )}
        {msg && <p className={`mt-3 text-sm ${msg.includes('成功') ? 'text-green-500' : 'text-red-500'}`}>{msg}</p>}
      </div>
    </div>
  );
}

/* ─── Report ─── */
function ReportTab() {
  const [targetType, setTargetType] = useState('post');
  const [targetId, setTargetId] = useState('');
  const [reason, setReason] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [msg, setMsg] = useState('');
  const [reports, setReports] = useState<Record<string, unknown>[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchReports = useCallback(async () => {
    try {
      const data = await apiGet<{ items: Record<string, unknown>[] }>('/api/reports/my?limit=20');
      setReports(data.items || []);
    } catch { /* ignore */ }
    setLoading(false);
  }, []);

  useEffect(() => { fetchReports(); }, [fetchReports]);

  const handleSubmit = async () => {
    if (!targetId.trim() || !reason.trim()) { setMsg('请填写完整信息'); return; }
    setSubmitting(true);
    setMsg('');
    try {
      await apiPost('/api/reports', {
        target_type: targetType,
        target_id: Number(targetId),
        reason: reason.trim(),
      });
      setMsg('举报已提交');
      setTargetId('');
      setReason('');
      fetchReports();
    } catch (e) {
      setMsg((e as ApiError).message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="max-w-lg space-y-6">
      <div className="rounded-lg border border-border/40 bg-card/60 p-6">
        <h2 className="font-serif text-xl font-bold flex items-center gap-2"><AlertTriangle className="h-5 w-5 text-red-500" />举报</h2>
        <div className="mt-4 space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium">举报类型</label>
            <select value={targetType} onChange={(e) => setTargetType(e.target.value)}
              className="w-full rounded-lg border border-border/40 bg-background px-3 py-2 text-sm">
              <option value="post">帖子</option>
              <option value="guestbook">留言</option>
              <option value="comment">评论</option>
              <option value="skill">技能</option>
              <option value="review">评测</option>
            </select>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium">目标 ID *</label>
            <input type="number" value={targetId} onChange={(e) => setTargetId(e.target.value)} placeholder="输入 ID"
              className="w-full rounded-lg border border-border/40 bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30" />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium">原因 *</label>
            <textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={3} placeholder="描述举报原因"
              className="w-full rounded-lg border border-border/40 bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30" />
          </div>
          {msg && <p className={`text-sm ${msg.includes('提交') ? 'text-green-500' : 'text-red-500'}`}>{msg}</p>}
          <button type="button" onClick={handleSubmit} disabled={submitting}
            className="flex items-center gap-2 rounded-lg bg-red-500 px-4 py-2 text-sm font-medium text-white hover:bg-red-600 disabled:opacity-50">
            <Send className="h-4 w-4" />{submitting ? '...' : '提交举报'}
          </button>
        </div>
      </div>

      {/* My reports */}
      <div>
        <h3 className="font-serif text-lg font-semibold mb-4">我的举报记录</h3>
        {loading ? (
          <div className="flex justify-center py-4"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
        ) : reports.length === 0 ? (
          <p className="text-muted-foreground">暂无举报记录</p>
        ) : (
          <div className="space-y-2">
            {reports.map((r, i) => (
              <div key={i} className="rounded-lg border border-border/40 bg-card/60 p-3 text-sm">
                <div className="flex items-center justify-between">
                  <span className="font-medium">{String(r.target_type || '')} #{String(r.target_id || '')}</span>
                  <span className="text-xs text-muted-foreground">{String(r.status || 'pending')}</span>
                </div>
                <p className="mt-1 text-muted-foreground">{String(r.reason || '')}</p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
