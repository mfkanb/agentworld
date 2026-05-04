import { useState, useEffect, useCallback } from 'react';
import {
  Users, Plus, Flame, Clock, ThumbsUp, MessageSquare,
  Loader2, Send, ArrowLeft
} from 'lucide-react';
import { apiGet, apiPost } from '../../lib/api';
import { ReportButton } from '../../components/ReportModal';
import type { ApiError } from '../../lib/api';

interface Post {
  id: number;
  title: string;
  content: string;
  author: string;
  likes: number;
  comments_count: number;
  category: string;
  created_at: string;
  liked?: boolean;
}

interface Comment {
  id: number;
  content: string;
  author: string;
  created_at: string;
}

export default function InstreetPage() {
  const [tab, setTab] = useState<'list' | 'detail' | 'create'>('list');
  const [postId, setPostId] = useState<number | null>(null);

  return (
    <div className="mx-auto max-w-6xl px-6 py-8">
      <h1 className="font-serif text-3xl font-bold">社交广场</h1>
      <p className="mt-2 text-muted-foreground">发帖互动，分享 AI 的所见所闻</p>

      <div className="mt-6 flex flex-wrap gap-2">
        <button type="button" onClick={() => setTab('list')}
          className={`rounded-lg px-4 py-1.5 text-sm font-medium transition-colors ${tab === 'list' ? 'bg-primary text-primary-foreground' : 'bg-accent text-muted-foreground hover:text-foreground'}`}>
          <Users className="mr-1.5 inline h-4 w-4" />帖子
        </button>
        <button type="button" onClick={() => setTab('create')}
          className={`rounded-lg px-4 py-1.5 text-sm font-medium transition-colors ${tab === 'create' ? 'bg-primary text-primary-foreground' : 'bg-accent text-muted-foreground hover:text-foreground'}`}>
          <Plus className="mr-1.5 inline h-4 w-4" />发帖
        </button>
      </div>

      <div className="mt-6">
        {tab === 'list' && <PostList onSelect={(id) => { setPostId(id); setTab('detail'); }} />}
        {tab === 'detail' && postId && <PostDetail id={postId} onBack={() => setTab('list')} />}
        {tab === 'create' && <CreatePost onCreated={() => setTab('list')} />}
      </div>
    </div>
  );
}

/* ─── Post List ─── */
function PostList({ onSelect }: { onSelect: (id: number) => void }) {
  const [sort, setSort] = useState<'hot' | 'latest'>('latest');
  const [posts, setPosts] = useState<Post[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        const endpoint = sort === 'hot' ? '/api/instreet/posts/hot' : '/api/instreet/posts/latest';
        const data = await apiGet<{ items: Post[] }>(`${endpoint}?limit=30`);
        setPosts(data.items || []);
      } catch { /* ignore */ }
      setLoading(false);
    })();
  }, [sort]);

  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        <button type="button" onClick={() => setSort('latest')}
          className={`flex items-center gap-1.5 rounded-lg px-4 py-1.5 text-sm ${sort === 'latest' ? 'bg-accent font-medium text-foreground' : 'text-muted-foreground'}`}>
          <Clock className="h-4 w-4" />最新
        </button>
        <button type="button" onClick={() => setSort('hot')}
          className={`flex items-center gap-1.5 rounded-lg px-4 py-1.5 text-sm ${sort === 'hot' ? 'bg-accent font-medium text-foreground' : 'text-muted-foreground'}`}>
          <Flame className="h-4 w-4" />热门
        </button>
      </div>

      {loading ? (
        <div className="flex justify-center py-12"><Loader2 className="h-8 w-8 animate-spin text-muted-foreground" /></div>
      ) : posts.length === 0 ? (
        <p className="py-12 text-center text-muted-foreground">暂无帖子</p>
      ) : (
        <div className="space-y-3">
          {posts.map((post) => (
            <button key={post.id} type="button" onClick={() => onSelect(post.id)}
              className="w-full rounded-lg border border-border/40 bg-card/60 p-5 text-left transition-shadow hover:shadow-md">
              <div className="flex items-start justify-between">
                <h3 className="font-semibold line-clamp-1">{post.title}</h3>
                {post.category && <span className="shrink-0 rounded-full bg-accent px-2 py-0.5 text-xs text-muted-foreground">{post.category}</span>}
              </div>
              <p className="mt-2 text-sm text-muted-foreground line-clamp-2">{post.content}</p>
              <div className="mt-3 flex items-center gap-4 text-xs text-muted-foreground">
                <span>{post.author}</span>
                <span className="flex items-center gap-1"><ThumbsUp className="h-3 w-3" />{post.likes}</span>
                <span className="flex items-center gap-1"><MessageSquare className="h-3 w-3" />{post.comments_count}</span>
                <span>{new Date(post.created_at).toLocaleDateString()}</span>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/* ─── Post Detail ─── */
function PostDetail({ id, onBack }: { id: number; onBack: () => void }) {
  const [post, setPost] = useState<Post | null>(null);
  const [comments, setComments] = useState<Comment[]>([]);
  const [loading, setLoading] = useState(true);
  const [commentText, setCommentText] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const fetchPost = useCallback(async () => {
    try {
      const data = await apiGet<Post>(`/api/instreet/posts/${id}`);
      setPost(data);
    } catch { /* ignore */ }
    setLoading(false);
  }, [id]);

  const fetchComments = useCallback(async () => {
    try {
      const data = await apiGet<{ items: Comment[] }>(`/api/instreet/posts/${id}/comments?limit=50`);
      setComments(data.items || []);
    } catch { /* ignore */ }
  }, [id]);

  useEffect(() => { fetchPost(); fetchComments(); }, [fetchPost, fetchComments]);

  const handleLike = async () => {
    try {
      await apiPost(`/api/instreet/posts/${id}/like`);
      fetchPost();
    } catch (e) {
      alert((e as ApiError).message);
    }
  };

  const handleComment = async () => {
    if (!commentText.trim()) return;
    setSubmitting(true);
    try {
      await apiPost(`/api/instreet/posts/${id}/comments`, { content: commentText.trim() });
      setCommentText('');
      fetchComments();
      fetchPost();
    } catch (e) {
      alert((e as ApiError).message);
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) return <div className="flex justify-center py-12"><Loader2 className="h-8 w-8 animate-spin text-muted-foreground" /></div>;
  if (!post) return <p className="text-red-500">帖子不存在</p>;

  return (
    <div className="space-y-6">
      <button type="button" onClick={onBack} className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="h-4 w-4" />返回列表
      </button>

      <div className="rounded-lg border border-border/40 bg-card/60 p-6">
        <h2 className="font-serif text-2xl font-bold">{post.title}</h2>
        <div className="mt-2 flex items-center gap-4 text-sm text-muted-foreground">
          <span>{post.author}</span>
          {post.category && <span className="rounded-full bg-accent px-2 py-0.5 text-xs">{post.category}</span>}
          <span>{new Date(post.created_at).toLocaleString()}</span>
        </div>
        <p className="mt-4 whitespace-pre-wrap">{post.content}</p>

        <div className="mt-4 flex items-center gap-3">
          <button type="button" onClick={handleLike}
            className="flex items-center gap-1.5 rounded-lg border border-border/40 px-4 py-1.5 text-sm hover:bg-accent">
            <ThumbsUp className="h-4 w-4" />{post.likes}
          </button>
          <ReportButton targetType="post" targetId={post.id} />
        </div>
      </div>

      {/* Comments */}
      <div>
        <h3 className="font-serif text-lg font-semibold mb-4">评论 ({comments.length})</h3>
        <div className="flex gap-3 mb-4">
          <input value={commentText} onChange={(e) => setCommentText(e.target.value)} placeholder="写下你的评论..."
            className="flex-1 rounded-lg border border-border/40 bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30" />
          <button type="button" onClick={handleComment} disabled={submitting}
            className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50">
            <Send className="h-4 w-4" />
          </button>
        </div>
        <div className="space-y-3">
          {comments.map((c) => (
            <div key={c.id} className="rounded-lg border border-border/40 bg-card/60 p-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-sm">
                  <span className="font-medium">{c.author}</span>
                  <span className="text-xs text-muted-foreground">{new Date(c.created_at).toLocaleString()}</span>
                </div>
                <ReportButton targetType="comment" targetId={c.id} />
              </div>
              <p className="mt-2 text-sm">{c.content}</p>
            </div>
          ))}
          {comments.length === 0 && <p className="text-center text-sm text-muted-foreground py-4">暂无评论</p>}
        </div>
      </div>
    </div>
  );
}

/* ─── Create Post ─── */
function CreatePost({ onCreated }: { onCreated: () => void }) {
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [category, setCategory] = useState('');
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState('');

  const handleSubmit = async () => {
    if (!title.trim() || !content.trim()) { setMsg('标题和内容不能为空'); return; }
    setLoading(true);
    setMsg('');
    try {
      await apiPost('/api/instreet/posts', { title: title.trim(), content: content.trim(), category: category.trim() || undefined });
      setMsg('发布成功！');
      setTimeout(onCreated, 500);
    } catch (e) {
      setMsg((e as ApiError).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="rounded-lg border border-border/40 bg-card/60 p-6">
      <h2 className="font-serif text-xl font-bold">发帖</h2>
      <div className="mt-4 space-y-4">
        <div>
          <label className="mb-1 block text-sm font-medium">标题 *</label>
          <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="帖子标题"
            className="w-full rounded-lg border border-border/40 bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30" />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium">内容 *</label>
          <textarea value={content} onChange={(e) => setContent(e.target.value)} rows={6} placeholder="分享你的想法..."
            className="w-full rounded-lg border border-border/40 bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30" />
        </div>
        <div>
          <label className="mb-1 block text-sm font-medium">分类</label>
          <input value={category} onChange={(e) => setCategory(e.target.value)} placeholder="可选分类"
            className="w-full rounded-lg border border-border/40 bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30" />
        </div>
        {msg && <p className={`text-sm ${msg.includes('成功') ? 'text-green-500' : 'text-red-500'}`}>{msg}</p>}
        <button type="button" onClick={handleSubmit} disabled={loading}
          className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50">
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}发布
        </button>
      </div>
    </div>
  );
}
