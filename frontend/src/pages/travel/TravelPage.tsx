import { useState, useEffect, useCallback } from 'react';
import {
  MapPin, Map, Compass, Flag, Loader2, CheckCircle, Globe,
  Navigation
} from 'lucide-react';
import { apiGet, apiPost } from '../../lib/api';
import type { ApiError } from '../../lib/api';

interface Landmark {
  id: number;
  name: string;
  country: string;
  description: string;
  tags: string;
  visited?: boolean;
}

export default function TravelPage() {
  const [tab, setTab] = useState<'discover' | 'visited' | 'all'>('discover');

  return (
    <div className="mx-auto max-w-6xl px-6 py-8">
      <h1 className="font-serif text-3xl font-bold">TravelMind</h1>
      <p className="mt-2 text-muted-foreground">随机漫步 — 探索世界名胜，打卡收集</p>

      <div className="mt-6 flex flex-wrap gap-2">
        {[
          { key: 'discover' as const, label: '随机发现', icon: Compass },
          { key: 'visited' as const, label: '已打卡', icon: CheckCircle },
          { key: 'all' as const, label: '景点总览', icon: Map },
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
        {tab === 'discover' && <DiscoverTab />}
        {tab === 'visited' && <VisitedTab />}
        {tab === 'all' && <AllLandmarks />}
      </div>
    </div>
  );
}

/* ─── Discover ─── */
function DiscoverTab() {
  const [landmark, setLandmark] = useState<Landmark | null>(null);
  const [loading, setLoading] = useState(true);
  const [visiting, setVisiting] = useState(false);
  const [visited, setVisited] = useState(false);
  const [stats, setStats] = useState({ visited: 0, total: 0 });

  const fetchNext = useCallback(async () => {
    setLoading(true);
    setVisited(false);
    try {
      const data = await apiGet<Landmark>('/api/travel/discover');
      setLandmark(data);
    } catch {
      setLandmark(null);
    }
    setLoading(false);
  }, []);

  const fetchStats = useCallback(async () => {
    try {
      const data = await apiGet<{ items: Landmark[] }>('/api/travel/landmarks');
      const items = data.items || [];
      setStats({ visited: items.filter((l) => l.visited).length, total: items.length });
    } catch { /* ignore */ }
  }, []);

  useEffect(() => { fetchNext(); fetchStats(); }, [fetchNext, fetchStats]);

  const handleVisit = async () => {
    if (!landmark) return;
    setVisiting(true);
    try {
      await apiPost(`/api/travel/landmarks/${landmark.id}/visit`);
      setVisited(true);
      fetchStats();
    } catch (e) {
      alert((e as ApiError).message);
    } finally {
      setVisiting(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Stats */}
      <div className="flex items-center gap-4">
        <div className="flex-1">
          <div className="flex items-center justify-between text-sm">
            <span>打卡进度：{stats.visited} / {stats.total}</span>
            <span className="text-muted-foreground">{stats.total > 0 ? Math.round(stats.visited / stats.total * 100) : 0}%</span>
          </div>
          <div className="mt-2 h-2 rounded-full bg-accent">
            <div className="h-2 rounded-full bg-primary transition-all" style={{ width: `${stats.total > 0 ? (stats.visited / stats.total * 100) : 0}%` }} />
          </div>
        </div>
      </div>

      {loading ? (
        <div className="flex justify-center py-12"><Loader2 className="h-8 w-8 animate-spin text-muted-foreground" /></div>
      ) : !landmark ? (
        <div className="py-16 text-center">
          <Globe className="mx-auto h-12 w-12 text-muted-foreground" />
          <p className="mt-4 text-muted-foreground">你已经打卡了所有景点！</p>
        </div>
      ) : (
        <div className="mx-auto max-w-lg">
          <div className="rounded-xl border border-border/40 bg-card/60 p-8 text-center shadow-lg">
            <MapPin className="mx-auto h-10 w-10 text-cyan-500" />
            <h2 className="mt-4 font-serif text-2xl font-bold">{landmark.name}</h2>
            <p className="mt-1 text-sm text-muted-foreground">{landmark.country}</p>
            <p className="mt-4 text-muted-foreground">{landmark.description}</p>
            {landmark.tags && (
              <div className="mt-4 flex flex-wrap justify-center gap-1">
                {landmark.tags.split(',').map((tag) => (
                  <span key={tag} className="rounded-full bg-accent px-2 py-0.5 text-xs text-muted-foreground">{tag.trim()}</span>
                ))}
              </div>
            )}

            {visited ? (
              <div className="mt-6 rounded-lg bg-green-500/10 p-4">
                <CheckCircle className="mx-auto h-8 w-8 text-green-500" />
                <p className="mt-2 font-medium text-green-500">打卡成功！+2 虾米</p>
                <button type="button" onClick={fetchNext}
                  className="mt-3 rounded-lg bg-primary px-4 py-2 text-sm text-primary-foreground hover:bg-primary/90">
                  <Navigation className="mr-1 inline h-4 w-4" />下一个
                </button>
              </div>
            ) : (
              <button type="button" onClick={handleVisit} disabled={visiting}
                className="mt-6 inline-flex items-center gap-2 rounded-lg bg-primary px-6 py-3 font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50">
                {visiting ? <Loader2 className="h-5 w-5 animate-spin" /> : <Flag className="h-5 w-5" />}
                打卡
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/* ─── Visited ─── */
function VisitedTab() {
  const [landmarks, setLandmarks] = useState<Landmark[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const data = await apiGet<{ items: Landmark[] }>('/api/travel/landmarks');
        setLandmarks((data.items || []).filter((l) => l.visited));
      } catch { /* ignore */ }
      setLoading(false);
    })();
  }, []);

  if (loading) return <div className="flex justify-center py-12"><Loader2 className="h-8 w-8 animate-spin text-muted-foreground" /></div>;

  return (
    <div>
      <h2 className="font-serif text-lg font-semibold mb-4">已打卡景点 ({landmarks.length})</h2>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {landmarks.map((l) => (
          <div key={l.id} className="rounded-lg border border-green-500/20 bg-card/60 p-4">
            <div className="flex items-start gap-2">
              <CheckCircle className="mt-0.5 h-4 w-4 shrink-0 text-green-500" />
              <div>
                <h3 className="font-medium">{l.name}</h3>
                <p className="text-xs text-muted-foreground">{l.country}</p>
              </div>
            </div>
          </div>
        ))}
      </div>
      {landmarks.length === 0 && <p className="py-8 text-center text-muted-foreground">暂无打卡记录</p>}
    </div>
  );
}

/* ─── All Landmarks ─── */
function AllLandmarks() {
  const [landmarks, setLandmarks] = useState<Landmark[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const data = await apiGet<{ items: Landmark[] }>('/api/travel/landmarks');
        setLandmarks(data.items || []);
      } catch { /* ignore */ }
      setLoading(false);
    })();
  }, []);

  if (loading) return <div className="flex justify-center py-12"><Loader2 className="h-8 w-8 animate-spin text-muted-foreground" /></div>;

  return (
    <div>
      <h2 className="font-serif text-lg font-semibold mb-4">景点总览</h2>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {landmarks.map((l) => (
          <div key={l.id} className={`rounded-lg border p-4 ${l.visited ? 'border-green-500/20 bg-green-500/5' : 'border-border/40 bg-card/60'}`}>
            <div className="flex items-start justify-between">
              <div>
                <h3 className="font-medium">{l.name}</h3>
                <p className="text-xs text-muted-foreground">{l.country}</p>
              </div>
              {l.visited && <CheckCircle className="h-4 w-4 shrink-0 text-green-500" />}
            </div>
            {l.tags && (
              <div className="mt-2 flex flex-wrap gap-1">
                {l.tags.split(',').map((tag) => (
                  <span key={tag} className="rounded-full bg-accent px-2 py-0.5 text-[10px] text-muted-foreground">{tag.trim()}</span>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
