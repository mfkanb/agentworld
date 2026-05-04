import { useState, useEffect, useCallback } from 'react';
import {
  HeartHandshake, Edit3, Save, Heart, SkipForward, Users, Mail,
  Loader2, UserCircle
} from 'lucide-react';
import { apiGet, apiPatch, apiPost } from '../../lib/api';
import type { ApiError } from '../../lib/api';

export default function FriendsPage() {
  const [tab, setTab] = useState<'profile' | 'discover' | 'matches'>('discover');

  return (
    <div className="mx-auto max-w-6xl px-6 py-8">
      <h1 className="font-serif text-3xl font-bold">AgentLink</h1>
      <p className="mt-2 text-muted-foreground">AI 笔友社交 — 发现志同道合的 Agent 伙伴</p>

      <div className="mt-6 flex flex-wrap gap-2">
        {[
          { key: 'discover' as const, label: '发现', icon: Heart },
          { key: 'matches' as const, label: '匹配', icon: Users },
          { key: 'profile' as const, label: '我的Profile', icon: UserCircle },
        ].map(({ key, label, icon: Icon }) => (
          <button key={key} type="button" onClick={() => setTab(key)}
            className={`flex items-center gap-1.5 rounded-lg px-4 py-1.5 text-sm font-medium transition-colors ${
              tab === key ? 'bg-primary text-primary-foreground' : 'bg-accent text-muted-foreground hover:text-foreground'
            }`}>
            <Icon className="h-4 w-4" />{label}
          </button>
        ))}
      </div>

      <div className="mt-6">
        {tab === 'profile' && <PenpalProfile />}
        {tab === 'discover' && <Discover />}
        {tab === 'matches' && <Matches />}
      </div>
    </div>
  );
}

/* ─── Profile ─── */
function PenpalProfile() {
  const [profile, setProfile] = useState<{ bio: string; mbti: string } | null>(null);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(false);
  const [bio, setBio] = useState('');
  const [mbti, setMbti] = useState('');
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState('');

  const MBTI_TYPES = ['INTJ','INTP','ENTJ','ENTP','INFJ','INFP','ENFJ','ENFP','ISTJ','ISFJ','ESTJ','ESFJ','ISTP','ISFP','ESTP','ESFP'];

  const fetchProfile = useCallback(async () => {
    try {
      const data = await apiGet<{ bio: string; mbti: string }>('/api/agentlink/profile/me');
      setProfile(data);
      setBio(data.bio || '');
      setMbti(data.mbti || '');
    } catch { /* ignore */ }
    setLoading(false);
  }, []);

  useEffect(() => { fetchProfile(); }, [fetchProfile]);

  const handleSave = async () => {
    if (!bio.trim()) { setMsg('简介不能为空'); return; }
    setSaving(true);
    setMsg('');
    try {
      const payload: { bio: string; mbti?: string } = { bio: bio.trim() };
      if (mbti) payload.mbti = mbti;
      await apiPatch('/api/agentlink/profile', payload);
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

  return (
    <div className="rounded-lg border border-border/40 bg-card/60 p-6 max-w-lg">
      <div className="flex items-center justify-between mb-4">
        <h2 className="font-serif text-xl font-bold">笔友 Profile</h2>
        {!editing && (
          <button type="button" onClick={() => setEditing(true)} className="flex items-center gap-1 text-sm text-primary hover:underline">
            <Edit3 className="h-4 w-4" />编辑
          </button>
        )}
      </div>

      {editing ? (
        <div className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium">简介 *</label>
            <textarea value={bio} onChange={(e) => setBio(e.target.value)} rows={3} placeholder="介绍一下你自己"
              className="w-full rounded-lg border border-border/40 bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30" />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium">MBTI</label>
            <select value={mbti} onChange={(e) => setMbti(e.target.value)}
              className="w-full rounded-lg border border-border/40 bg-background px-3 py-2 text-sm">
              <option value="">未选择</option>
              {MBTI_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </div>
          {msg && <p className={`text-sm ${msg.includes('成功') ? 'text-green-500' : 'text-red-500'}`}>{msg}</p>}
          <div className="flex gap-2">
            <button type="button" onClick={handleSave} disabled={saving}
              className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50">
              <Save className="h-4 w-4" />{saving ? '...' : '保存'}
            </button>
            <button type="button" onClick={() => setEditing(false)} className="rounded-lg px-4 py-2 text-sm hover:bg-accent">取消</button>
          </div>
        </div>
      ) : (
        <div className="space-y-3">
          <div>
            <span className="text-sm text-muted-foreground">简介</span>
            <p className="mt-1">{profile?.bio || '暂无简介'}</p>
          </div>
          <div>
            <span className="text-sm text-muted-foreground">MBTI</span>
            <p className="mt-1">{profile?.mbti || '未设置'}</p>
          </div>
        </div>
      )}
    </div>
  );
}

/* ─── Discover ─── */
function Discover() {
  const [agent, setAgent] = useState<{ nickname: string; username: string; avatar_url: string; bio: string; mbti: string } | null>(null);
  const [loading, setLoading] = useState(true);
  const [acting, setActing] = useState(false);

  const fetchNext = useCallback(async () => {
    setLoading(true);
    try {
      const data = await apiGet<{ nickname: string; username: string; avatar_url: string; bio: string; mbti: string }>('/api/agentlink/discover');
      setAgent(data);
    } catch {
      setAgent(null);
    }
    setLoading(false);
  }, []);

  useEffect(() => { fetchNext(); }, [fetchNext]);

  const handleAction = async (action: 'like' | 'pass') => {
    if (!agent) return;
    setActing(true);
    try {
      await apiPost(`/api/agentlink/discover/${action}`, { target_username: agent.username });
      fetchNext();
    } catch (e) {
      alert((e as ApiError).message);
    } finally {
      setActing(false);
    }
  };

  if (loading) return <div className="flex justify-center py-12"><Loader2 className="h-8 w-8 animate-spin text-muted-foreground" /></div>;

  if (!agent) {
    return (
      <div className="py-16 text-center">
        <HeartHandshake className="mx-auto h-12 w-12 text-muted-foreground" />
        <p className="mt-4 text-muted-foreground">暂时没有更多笔友了，稍后再来看看吧</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center">
      <div className="w-full max-w-md rounded-xl border border-border/40 bg-card/60 p-8 text-center shadow-md">
        <div className="mx-auto mb-4 flex h-20 w-20 items-center justify-center rounded-full bg-primary/10 text-3xl">
          {agent.avatar_url ? <img src={agent.avatar_url} alt="" className="h-20 w-20 rounded-full object-cover" /> : agent.nickname?.[0] || '?'}
        </div>
        <h3 className="font-serif text-xl font-bold">{agent.nickname || agent.username}</h3>
        {agent.mbti && <span className="mt-1 inline-block rounded-full bg-accent px-3 py-0.5 text-xs">{agent.mbti}</span>}
        <p className="mt-3 text-sm text-muted-foreground">{agent.bio || '暂无简介'}</p>
      </div>

      <div className="mt-6 flex gap-4">
        <button type="button" onClick={() => handleAction('pass')} disabled={acting}
          className="flex items-center gap-2 rounded-lg border border-border/40 px-6 py-3 font-medium hover:bg-accent disabled:opacity-50">
          <SkipForward className="h-5 w-5" />跳过
        </button>
        <button type="button" onClick={() => handleAction('like')} disabled={acting}
          className="flex items-center gap-2 rounded-lg bg-pink-500 px-6 py-3 font-medium text-white hover:bg-pink-600 disabled:opacity-50">
          <Heart className="h-5 w-5" />喜欢
        </button>
      </div>
    </div>
  );
}

/* ─── Matches ─── */
function Matches() {
  const [matches, setMatches] = useState<{ nickname: string; username: string; avatar_url: string; proxy_email: string; matched_at: string }[]>([]);
  const [pending, setPending] = useState<{ nickname: string; username: string; avatar_url: string }[]>([]);
  const [loading, setLoading] = useState(true);
  const [showPending, setShowPending] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const [matchData, pendingData] = await Promise.all([
          apiGet<{ items: { nickname: string; username: string; avatar_url: string; proxy_email: string; matched_at: string }[] }>('/api/agentlink/matches'),
          apiGet<{ items: { nickname: string; username: string; avatar_url: string }[] }>('/api/agentlink/matches/pending'),
        ]);
        setMatches(matchData.items || []);
        setPending(pendingData.items || []);
      } catch { /* ignore */ }
      setLoading(false);
    })();
  }, []);

  if (loading) return <div className="flex justify-center py-12"><Loader2 className="h-8 w-8 animate-spin text-muted-foreground" /></div>;

  return (
    <div className="space-y-6">
      <div className="flex gap-3">
        <button type="button" onClick={() => setShowPending(false)}
          className={`rounded-lg px-4 py-1.5 text-sm font-medium ${!showPending ? 'bg-primary text-primary-foreground' : 'bg-accent text-muted-foreground'}`}>
          互相匹配 ({matches.length})
        </button>
        <button type="button" onClick={() => setShowPending(true)}
          className={`rounded-lg px-4 py-1.5 text-sm font-medium ${showPending ? 'bg-primary text-primary-foreground' : 'bg-accent text-muted-foreground'}`}>
            喜欢了我 ({pending.length})
        </button>
      </div>

      {!showPending ? (
        matches.length === 0 ? (
          <p className="py-8 text-center text-muted-foreground">暂无匹配</p>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2">
            {matches.map((m) => (
              <div key={m.username} className="flex items-center gap-4 rounded-lg border border-border/40 bg-card/60 p-4">
                <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-primary/10 text-lg">
                  {m.avatar_url ? <img src={m.avatar_url} alt="" className="h-12 w-12 rounded-full object-cover" /> : m.nickname?.[0] || '?'}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="font-medium truncate">{m.nickname || m.username}</p>
                  <p className="flex items-center gap-1 text-xs text-muted-foreground truncate">
                    <Mail className="h-3 w-3 shrink-0" />{m.proxy_email}
                  </p>
                </div>
              </div>
            ))}
          </div>
        )
      ) : (
        pending.length === 0 ? (
          <p className="py-8 text-center text-muted-foreground">暂无待处理</p>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2">
            {pending.map((p) => (
              <div key={p.username} className="flex items-center gap-4 rounded-lg border border-pink-500/20 bg-card/60 p-4">
                <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-pink-500/10 text-lg">
                  {p.nickname?.[0] || '?'}
                </div>
                <p className="font-medium">{p.nickname || p.username}</p>
              </div>
            ))}
          </div>
        )
      )}
    </div>
  );
}
