import { useState, useEffect, useCallback } from 'react';
import {
  Wine, Dices, Send, Heart, Palette, Loader2, Beer, MessageCircle,
  ShoppingCart, ThumbsUp, Clock
} from 'lucide-react';
import { apiGet, apiPost } from '../../lib/api';
import type { ApiError } from '../../lib/api';

interface Drink {
  id: number;
  name: string;
  code: string;
  description: string;
  tags: string;
}

interface Session {
  id: number;
  drink_id: number;
  drink_name?: string;
  consumed: number;
  created_at: string;
}

interface GuestbookEntry {
  id: number;
  content: string;
  author: string;
  likes: number;
  liked: boolean;
  created_at: string;
}

interface Selfie {
  id: number;
  image_url: string;
  author: string;
  likes: number;
  liked: boolean;
  created_at: string;
}

export default function BarPage() {
  const [tab, setTab] = useState<'drinks' | 'order' | 'guestbook' | 'selfies'>('drinks');

  return (
    <div className="mx-auto max-w-6xl px-6 py-8">
      <h1 className="font-serif text-3xl font-bold">酒馆</h1>
      <p className="mt-2 text-muted-foreground">品鉴创意酒水，留言涂鸦交朋友</p>

      <div className="mt-6 flex flex-wrap gap-2">
        {[
          { key: 'drinks' as const, label: '酒谱', icon: Wine },
          { key: 'order' as const, label: '点酒', icon: ShoppingCart },
          { key: 'guestbook' as const, label: '留言簿', icon: MessageCircle },
          { key: 'selfies' as const, label: '涂鸦墙', icon: Palette },
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
        {tab === 'drinks' && <DrinkList />}
        {tab === 'order' && <OrderDrink />}
        {tab === 'guestbook' && <Guestbook />}
        {tab === 'selfies' && <SelfieWall />}
      </div>
    </div>
  );
}

/* ─── Drink List ─── */
function DrinkList() {
  const [drinks, setDrinks] = useState<Drink[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const data = await apiGet<Drink[]>('/drinks');
        setDrinks(data || []);
      } catch { /* ignore */ }
      setLoading(false);
    })();
  }, []);

  if (loading) return <div className="flex justify-center py-12"><Loader2 className="h-8 w-8 animate-spin text-muted-foreground" /></div>;

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {drinks.map((drink) => (
        <div key={drink.id} className="rounded-lg border border-border/40 bg-card/60 p-5">
          <div className="flex items-start gap-3">
            <Beer className="mt-1 h-6 w-6 shrink-0 text-amber-500" />
            <div>
              <h3 className="font-serif text-lg font-semibold">{drink.name}</h3>
              <p className="mt-1 text-sm text-muted-foreground">{drink.description}</p>
              {drink.tags && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {drink.tags.split(',').map((tag) => (
                    <span key={tag} className="rounded-full bg-accent px-2 py-0.5 text-xs text-muted-foreground">{tag.trim()}</span>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

/* ─── Order Drink ─── */
function OrderDrink() {
  const [loading, setLoading] = useState(false);
  const [selectedCode, setSelectedCode] = useState('');
  const [drinks, setDrinks] = useState<Drink[]>([]);
  const [session, setSession] = useState<Session | null>(null);
  const [effect, setEffect] = useState<string | null>(null);
  const [msg, setMsg] = useState('');

  useEffect(() => {
    apiGet<Drink[]>('/drinks').then((data) => setDrinks(data || [])).catch(() => {});
  }, []);

  const handleRandom = async () => {
    setLoading(true);
    setMsg('');
    setEffect(null);
    try {
      const data = await apiPost<Session>('/drink/random');
      setSession(data);
      setMsg(`获得了一杯 ${data.drink_name || '神秘酒水'}！`);
    } catch (e) {
      setMsg((e as ApiError).message);
    } finally {
      setLoading(false);
    }
  };

  const handleOrder = async () => {
    if (!selectedCode) return;
    setLoading(true);
    setMsg('');
    setEffect(null);
    try {
      const data = await apiPost<Session>('/drink', { code: selectedCode });
      setSession(data);
      setMsg(`成功点了 ${data.drink_name || '一杯酒'}！`);
    } catch (e) {
      setMsg((e as ApiError).message);
    } finally {
      setLoading(false);
    }
  };

  const handleConsume = async () => {
    if (!session) return;
    setLoading(true);
    try {
      const data = await apiPost<{ effect_description?: string; mood_tags?: string[] }>(
        `/sessions/${session.id}/consume`
      );
      setEffect(data.effect_description || '你感觉神清气爽！');
    } catch (e) {
      setMsg((e as ApiError).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap gap-3">
        <button type="button" onClick={handleRandom} disabled={loading}
          className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50">
          <Dices className="h-4 w-4" />{loading ? '...' : '随机点酒'}
        </button>
        <div className="flex gap-2">
          <select value={selectedCode} onChange={(e) => setSelectedCode(e.target.value)}
            className="rounded-lg border border-border/40 bg-background px-3 py-2 text-sm">
            <option value="">选择酒水...</option>
            {drinks.map((d) => <option key={d.id} value={d.code}>{d.name}</option>)}
          </select>
          <button type="button" onClick={handleOrder} disabled={loading || !selectedCode}
            className="flex items-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-medium hover:text-foreground disabled:opacity-50">
            指定点酒
          </button>
        </div>
      </div>

      {msg && <p className="rounded-lg bg-primary/10 px-3 py-2 text-sm">{msg}</p>}

      {session && !effect && (
        <div className="rounded-lg border border-border/40 bg-card/60 p-6">
          <h3 className="font-serif text-lg font-semibold">当前酒局 #{session.id}</h3>
          <p className="mt-2 text-sm text-muted-foreground">
            <Clock className="mr-1 inline h-4 w-4" />{new Date(session.created_at).toLocaleString()}
          </p>
          <button type="button" onClick={handleConsume} disabled={loading}
            className="mt-4 flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50">
            <Wine className="h-4 w-4" />喝酒
          </button>
        </div>
      )}

      {effect && (
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-6">
          <p className="font-serif text-lg">{effect}</p>
        </div>
      )}

      <p className="text-xs text-muted-foreground">每日饮酒上限：10 杯</p>
    </div>
  );
}

/* ─── Guestbook ─── */
function Guestbook() {
  const [entries, setEntries] = useState<GuestbookEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [content, setContent] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const fetchEntries = useCallback(async () => {
    try {
      const data = await apiGet<{ items: GuestbookEntry[] }>('/guestbook?limit=50');
      setEntries(data.items || []);
    } catch { /* ignore */ }
    setLoading(false);
  }, []);

  useEffect(() => { fetchEntries(); }, [fetchEntries]);

  const handleSubmit = async () => {
    if (!content.trim()) return;
    setSubmitting(true);
    try {
      await apiPost('/guestbook/entries', { content: content.trim() });
      setContent('');
      fetchEntries();
    } catch (e) {
      alert((e as ApiError).message);
    } finally {
      setSubmitting(false);
    }
  };

  const handleLike = async (id: number) => {
    try {
      await apiPost(`/guestbook/entries/${id}/like`);
      fetchEntries();
    } catch (e) {
      alert((e as ApiError).message);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex gap-3">
        <input value={content} onChange={(e) => setContent(e.target.value)} placeholder="写点什么..."
          className="flex-1 rounded-lg border border-border/40 bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30" />
        <button type="button" onClick={handleSubmit} disabled={submitting}
          className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50">
          <Send className="h-4 w-4" />{submitting ? '...' : '留言'}
        </button>
      </div>

      {loading ? (
        <div className="flex justify-center py-8"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
      ) : (
        <div className="space-y-3">
          {entries.map((entry) => (
            <div key={entry.id} className="flex items-start gap-4 rounded-lg border border-border/40 bg-card/60 p-4">
              <div className="flex-1">
                <p className="text-sm">{entry.content}</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  {entry.author} · {new Date(entry.created_at).toLocaleString()}
                </p>
              </div>
              <button type="button" onClick={() => handleLike(entry.id)}
                className="flex items-center gap-1 rounded-lg px-3 py-1 text-sm text-muted-foreground hover:bg-accent">
                <ThumbsUp className="h-4 w-4" />{entry.likes}
              </button>
            </div>
          ))}
          {entries.length === 0 && <p className="py-8 text-center text-muted-foreground">暂无留言</p>}
        </div>
      )}
    </div>
  );
}

/* ─── Selfie Wall ─── */
function SelfieWall() {
  const [selfies, setSelfies] = useState<Selfie[]>([]);
  const [loading, setLoading] = useState(true);
  const [publishing, setPublishing] = useState(false);

  const fetchSelfies = useCallback(async () => {
    try {
      const data = await apiGet<{ items: Selfie[] }>('/selfies?limit=50');
      setSelfies(data.items || []);
    } catch { /* ignore */ }
    setLoading(false);
  }, []);

  useEffect(() => { fetchSelfies(); }, [fetchSelfies]);

  const handlePublish = async () => {
    setPublishing(true);
    try {
      await apiPost('/selfies');
      fetchSelfies();
    } catch (e) {
      alert((e as ApiError).message);
    } finally {
      setPublishing(false);
    }
  };

  const handleLike = async (id: number) => {
    try {
      await apiPost(`/selfies/${id}/like`);
      fetchSelfies();
    } catch (e) {
      alert((e as ApiError).message);
    }
  };

  return (
    <div className="space-y-6">
      <button type="button" onClick={handlePublish} disabled={publishing}
        className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50">
        <Palette className="h-4 w-4" />{publishing ? '生成中...' : '发布涂鸦'}
      </button>

      {loading ? (
        <div className="flex justify-center py-8"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {selfies.map((selfie) => (
            <div key={selfie.id} className="rounded-lg border border-border/40 bg-card/60 p-4">
              <img src={selfie.image_url} alt="涂鸦" className="aspect-square w-full rounded-lg bg-accent object-cover" />
              <div className="mt-3 flex items-center justify-between">
                <span className="text-xs text-muted-foreground">{selfie.author}</span>
                <button type="button" onClick={() => handleLike(selfie.id)}
                  className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
                  <Heart className="h-4 w-4" />{selfie.likes}
                </button>
              </div>
            </div>
          ))}
          {selfies.length === 0 && <p className="col-span-full py-8 text-center text-muted-foreground">暂无涂鸦</p>}
        </div>
      )}
    </div>
  );
}
