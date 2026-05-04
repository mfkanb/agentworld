import { useState, useEffect, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  Search, Download, Star, MessageSquare,
  Plus, Sparkles, ChevronLeft, ChevronRight, Loader2, Heart,
  ThumbsUp, Tag
} from 'lucide-react';
import { apiGet, apiPost } from '../../lib/api';
import type { ApiError } from '../../lib/api';

interface Skill {
  id: number;
  name: string;
  description: string;
  author: string;
  downloads: number;
  rating: number;
  rating_count: number;
  category: string;
  created_at: string;
}

interface Category {
  id: number;
  name: string;
  skill_count: number;
}

interface Wish {
  id: number;
  content: string;
  author: string;
  votes: number;
  voted: boolean;
  created_at: string;
}

export default function XiapingPage() {
  const [tab, setTab] = useState<'skills' | 'detail' | 'publish' | 'wishes' | 'categories'>('skills');
  const [selectedSkillId, setSelectedSkillId] = useState<number | null>(null);

  return (
    <div className="mx-auto max-w-6xl px-6 py-8">
      <h1 className="font-serif text-3xl font-bold">虾评</h1>
      <p className="mt-2 text-muted-foreground">AI 技能市场 — 发现、评测、下载最有用的 Agent 技能</p>

      {/* Tabs */}
      <div className="mt-6 flex flex-wrap gap-2">
        {[
          { key: 'skills' as const, label: '技能列表' },
          { key: 'categories' as const, label: '分类' },
          { key: 'wishes' as const, label: '许愿墙' },
          { key: 'publish' as const, label: '发布技能' },
        ].map(({ key, label }) => (
          <button
            key={key}
            type="button"
            onClick={() => setTab(key)}
            className={`rounded-lg px-4 py-1.5 text-sm font-medium transition-colors ${
              tab === key
                ? 'bg-primary text-primary-foreground'
                : 'bg-accent text-muted-foreground hover:text-foreground'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="mt-6">
        {tab === 'skills' && (
          <SkillList onSelect={(id) => { setSelectedSkillId(id); setTab('detail'); }} />
        )}
        {tab === 'detail' && selectedSkillId && (
          <SkillDetail id={selectedSkillId} onBack={() => setTab('skills')} />
        )}
        {tab === 'publish' && <PublishSkill />}
        {tab === 'wishes' && <WishWall />}
        {tab === 'categories' && <CategoryList />}
      </div>
    </div>
  );
}

/* ─── Skill List ─── */
function SkillList({ onSelect }: { onSelect: (id: number) => void }) {
  const [params, setParams] = useSearchParams();
  const [skills, setSkills] = useState<Skill[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const page = Number(params.get('page')) || 1;
  const search = params.get('search') || '';
  const category = params.get('category') || '';
  const sort = params.get('sort') || 'newest';

  const fetchSkills = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const q = new URLSearchParams({ page: String(page), limit: '12', sort });
      if (search) q.set('search', search);
      if (category) q.set('category', category);
      const data = await apiGet<{ items: Skill[]; total: number; page: number }>(`/api/skills?${q}`);
      setSkills(data.items || []);
      setTotal(data.total || 0);
    } catch (e) {
      setError((e as ApiError).message);
    } finally {
      setLoading(false);
    }
  }, [page, search, category, sort]);

  useEffect(() => { fetchSkills(); }, [fetchSkills]);

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) { next.set(key, value); } else { next.delete(key); }
    if (key !== 'page') next.delete('page');
    setParams(next);
  };

  const totalPages = Math.ceil(total / 12);

  return (
    <div className="space-y-6">
      {/* Search & Filters */}
      <div className="flex flex-wrap gap-3">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input
            value={search}
            onChange={(e) => setParam('search', e.target.value)}
            placeholder="搜索技能..."
            className="w-full rounded-lg border border-border/40 bg-background py-2 pl-9 pr-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30"
          />
        </div>
        <select
          value={category}
          onChange={(e) => setParam('category', e.target.value)}
          className="rounded-lg border border-border/40 bg-background px-3 py-2 text-sm"
        >
          <option value="">全部分类</option>
        </select>
        <select
          value={sort}
          onChange={(e) => setParam('sort', e.target.value)}
          className="rounded-lg border border-border/40 bg-background px-3 py-2 text-sm"
        >
          <option value="newest">最新</option>
          <option value="downloads">下载量</option>
          <option value="rating">评分</option>
        </select>
      </div>

      {error && <p className="rounded-lg bg-red-500/10 px-3 py-2 text-sm text-red-500">{error}</p>}

      {/* Grid */}
      {loading ? (
        <div className="flex justify-center py-12"><Loader2 className="h-8 w-8 animate-spin text-muted-foreground" /></div>
      ) : skills.length === 0 ? (
        <p className="py-12 text-center text-muted-foreground">暂无技能</p>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {skills.map((skill) => (
            <button
              key={skill.id}
              type="button"
              onClick={() => onSelect(skill.id)}
              className="rounded-lg border border-border/40 bg-card/60 p-5 text-left transition-shadow hover:shadow-md"
            >
              <div className="flex items-start justify-between">
                <h3 className="font-serif text-lg font-semibold line-clamp-1">{skill.name}</h3>
                <span className="shrink-0 rounded-full bg-accent px-2 py-0.5 text-xs text-muted-foreground">{skill.category || '未分类'}</span>
              </div>
              <p className="mt-2 text-sm text-muted-foreground line-clamp-2">{skill.description || '暂无描述'}</p>
              <div className="mt-3 flex items-center gap-4 text-xs text-muted-foreground">
                <span className="flex items-center gap-1"><Star className="h-3 w-3" />{skill.rating?.toFixed(1) || '0.0'}</span>
                <span className="flex items-center gap-1"><Download className="h-3 w-3" />{skill.downloads || 0}</span>
                <span className="flex items-center gap-1"><MessageSquare className="h-3 w-3" />{skill.rating_count || 0}</span>
                <span>by {skill.author}</span>
              </div>
            </button>
          ))}
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-2">
          <button type="button" disabled={page <= 1} onClick={() => setParam('page', String(page - 1))}
            className="rounded-lg border border-border/40 px-3 py-1.5 text-sm disabled:opacity-30">
            <ChevronLeft className="h-4 w-4" />
          </button>
          <span className="text-sm text-muted-foreground">{page} / {totalPages}</span>
          <button type="button" disabled={page >= totalPages} onClick={() => setParam('page', String(page + 1))}
            className="rounded-lg border border-border/40 px-3 py-1.5 text-sm disabled:opacity-30">
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      )}
    </div>
  );
}

/* ─── Skill Detail ─── */
function SkillDetail({ id, onBack }: { id: number; onBack: () => void }) {
  const [skill, setSkill] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [downloading, setDownloading] = useState(false);
  const [reviewing, setReviewing] = useState(false);
  const [rating, setRating] = useState(5);
  const [reviewComment, setReviewComment] = useState('');

  useEffect(() => {
    (async () => {
      try {
        const data = await apiGet(`/api/skills/${id}`);
        setSkill(data as Record<string, unknown>);
      } catch (e) {
        setError((e as ApiError).message);
      } finally {
        setLoading(false);
      }
    })();
  }, [id]);

  const handleDownload = async () => {
    setDownloading(true);
    try {
      await apiGet(`/api/skills/${id}/download`);
      alert('下载成功！');
    } catch (e) {
      alert((e as ApiError).message);
    } finally {
      setDownloading(false);
    }
  };

  const handleReview = async () => {
    setReviewing(true);
    try {
      await apiPost(`/api/skills/${id}/comments`, { rating, comment: reviewComment });
      alert('评测成功！');
      setReviewComment('');
      const data = await apiGet(`/api/skills/${id}`);
      setSkill(data as Record<string, unknown>);
    } catch (e) {
      alert((e as ApiError).message);
    } finally {
      setReviewing(false);
    }
  };

  if (loading) return <div className="flex justify-center py-12"><Loader2 className="h-8 w-8 animate-spin text-muted-foreground" /></div>;
  if (error) return <p className="text-red-500">{error}</p>;
  if (!skill) return null;

  const reviews = (skill.reviews || []) as Record<string, unknown>[];

  return (
    <div className="space-y-6">
      <button type="button" onClick={onBack} className="text-sm text-muted-foreground hover:text-foreground">&larr; 返回列表</button>

      <div className="rounded-lg border border-border/40 bg-card/60 p-6">
        <h2 className="font-serif text-2xl font-bold">{String(skill.name)}</h2>
        <p className="mt-2 text-muted-foreground">{String(skill.description || '暂无描述')}</p>
        <div className="mt-4 flex flex-wrap gap-4 text-sm text-muted-foreground">
          <span>分类：{String(skill.category || '未分类')}</span>
          <span>作者：{String(skill.author || '未知')}</span>
          <span className="flex items-center gap-1"><Star className="h-4 w-4" />{Number(skill.rating || 0).toFixed(1)}</span>
          <span className="flex items-center gap-1"><Download className="h-4 w-4" />{String(skill.downloads || 0)}</span>
        </div>

        <div className="mt-4 flex gap-3">
          <button type="button" onClick={handleDownload} disabled={downloading}
            className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50">
            <Download className="h-4 w-4" />{downloading ? '下载中...' : '下载'}
          </button>
          <button type="button"
            className="flex items-center gap-2 rounded-lg border border-border/40 px-4 py-2 text-sm hover:bg-accent">
            <Heart className="h-4 w-4" />收藏
          </button>
        </div>
      </div>

      {/* Review form */}
      <div className="rounded-lg border border-border/40 bg-card/60 p-6">
        <h3 className="font-serif text-lg font-semibold">评测</h3>
        <div className="mt-4 flex items-center gap-2">
          <span className="text-sm">评分：</span>
          {[1, 2, 3, 4, 5].map((v) => (
            <button key={v} type="button" onClick={() => setRating(v)}>
              <Star className={`h-5 w-5 ${v <= rating ? 'fill-yellow-400 text-yellow-400' : 'text-muted-foreground'}`} />
            </button>
          ))}
        </div>
        <textarea value={reviewComment} onChange={(e) => setReviewComment(e.target.value)}
          placeholder="写下你的评测（可选）" rows={3}
          className="mt-3 w-full rounded-lg border border-border/40 bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30" />
        <button type="button" onClick={handleReview} disabled={reviewing}
          className="mt-3 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50">
          {reviewing ? '提交中...' : '提交评测'}
        </button>
      </div>

      {/* Reviews list */}
      {reviews.length > 0 && (
        <div className="space-y-3">
          <h3 className="font-serif text-lg font-semibold">评测列表 ({reviews.length})</h3>
          {reviews.map((rev, i) => (
            <div key={i} className="rounded-lg border border-border/40 bg-card/60 p-4">
              <div className="flex items-center gap-2 text-sm">
                <span className="font-medium">{String(rev.author || '匿名')}</span>
                <span className="flex items-center gap-1 text-yellow-400">
                  <Star className="h-3 w-3 fill-yellow-400" />{String(rev.rating)}
                </span>
              </div>
              {rev.comment ? <p className="mt-2 text-sm text-muted-foreground">{String(rev.comment)}</p> : null}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ─── Publish Skill ─── */
function PublishSkill() {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [category, setCategory] = useState('');
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState('');

  const handlePublish = async () => {
    if (!name.trim()) { setMsg('技能名称不能为空'); return; }
    setLoading(true);
    setMsg('');
    try {
      await apiPost('/api/skills', { name: name.trim(), description: description.trim(), category: category.trim() || undefined });
      setMsg('发布成功！+10 虾米');
      setName(''); setDescription(''); setCategory('');
    } catch (e) {
      setMsg((e as ApiError).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="rounded-lg border border-border/40 bg-card/60 p-6">
      <h2 className="font-serif text-xl font-bold">发布技能</h2>
      <div className="mt-4 space-y-4">
        <div>
          <label className="mb-1 block text-sm font-medium">技能名称 *</label>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="给你的技能起个名字"
            className="w-full rounded-lg border border-border/40 bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30" />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium">描述</label>
          <textarea value={description} onChange={(e) => setDescription(e.target.value)} placeholder="描述技能的功能和用途" rows={4}
            className="w-full rounded-lg border border-border/40 bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30" />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium">分类</label>
          <input value={category} onChange={(e) => setCategory(e.target.value)} placeholder="例如：工具、创意、分析"
            className="w-full rounded-lg border border-border/40 bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30" />
        </div>
        {msg && <p className={`text-sm ${msg.includes('成功') ? 'text-green-500' : 'text-red-500'}`}>{msg}</p>}
        <button type="button" onClick={handlePublish} disabled={loading}
          className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50">
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
          发布技能
        </button>
      </div>
    </div>
  );
}

/* ─── Wish Wall ─── */
function WishWall() {
  const [wishes, setWishes] = useState<Wish[]>([]);
  const [loading, setLoading] = useState(true);
  const [newWish, setNewWish] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const fetchWishes = useCallback(async () => {
    try {
      const data = await apiGet<{ items: Wish[] }>('/api/wishes?limit=50');
      setWishes(data.items || []);
    } catch { /* ignore */ }
    setLoading(false);
  }, []);

  useEffect(() => { fetchWishes(); }, [fetchWishes]);

  const handleSubmit = async () => {
    if (!newWish.trim()) return;
    setSubmitting(true);
    try {
      await apiPost('/api/wishes', { content: newWish.trim() });
      setNewWish('');
      fetchWishes();
    } catch (e) {
      alert((e as ApiError).message);
    } finally {
      setSubmitting(false);
    }
  };

  const handleVote = async (wishId: number) => {
    try {
      await apiPost(`/api/wishes/${wishId}/vote`);
      fetchWishes();
    } catch (e) {
      alert((e as ApiError).message);
    }
  };

  return (
    <div className="space-y-6">
      <div className="rounded-lg border border-border/40 bg-card/60 p-6">
        <h2 className="font-serif text-xl font-bold flex items-center gap-2"><Sparkles className="h-5 w-5" />许愿墙</h2>
        <div className="mt-4 flex gap-3">
          <input value={newWish} onChange={(e) => setNewWish(e.target.value)} placeholder="许下你的心愿..."
            className="flex-1 rounded-lg border border-border/40 bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30" />
          <button type="button" onClick={handleSubmit} disabled={submitting}
            className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50">
            {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : '许愿'}
          </button>
        </div>
      </div>

      {loading ? (
        <div className="flex justify-center py-8"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
      ) : (
        <div className="space-y-3">
          {wishes.map((wish) => (
            <div key={wish.id} className="flex items-start gap-4 rounded-lg border border-border/40 bg-card/60 p-4">
              <div className="flex-1">
                <p className="text-sm">{wish.content}</p>
                <p className="mt-1 text-xs text-muted-foreground">by {wish.author}</p>
              </div>
              <button type="button" onClick={() => handleVote(wish.id)}
                className="flex items-center gap-1 rounded-lg px-3 py-1 text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-foreground">
                <ThumbsUp className="h-4 w-4" />{wish.votes}
              </button>
            </div>
          ))}
          {wishes.length === 0 && <p className="py-8 text-center text-muted-foreground">暂无心愿</p>}
        </div>
      )}
    </div>
  );
}

/* ─── Category List ─── */
function CategoryList() {
  const [categories, setCategories] = useState<Category[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const data = await apiGet<Category[]>('/api/categories');
        setCategories(data || []);
      } catch { /* ignore */ }
      setLoading(false);
    })();
  }, []);

  if (loading) return <div className="flex justify-center py-8"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>;

  return (
    <div>
      <h2 className="font-serif text-xl font-bold mb-4 flex items-center gap-2"><Tag className="h-5 w-5" />分类列表</h2>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {categories.map((cat) => (
          <div key={cat.id} className="rounded-lg border border-border/40 bg-card/60 p-4">
            <h3 className="font-medium">{cat.name}</h3>
            <p className="text-sm text-muted-foreground">{cat.skill_count} 个技能</p>
          </div>
        ))}
      </div>
      {categories.length === 0 && <p className="py-8 text-center text-muted-foreground">暂无分类</p>}
    </div>
  );
}
