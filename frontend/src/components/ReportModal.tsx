import { useState } from 'react';
import { Shield, X, Loader2, Send } from 'lucide-react';
import { apiPost } from '../lib/api';
import type { ApiError } from '../lib/api';

interface ReportModalProps {
  targetType: 'post' | 'guestbook' | 'comment' | 'skill' | 'review';
  targetId: number;
  onClose: () => void;
  onReported?: () => void;
}

export function ReportModal({ targetType, targetId, onClose, onReported }: ReportModalProps) {
  const [reason, setReason] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [msg, setMsg] = useState('');

  const handleSubmit = async () => {
    if (!reason.trim()) { setMsg('请填写举报原因'); return; }
    setSubmitting(true);
    setMsg('');
    try {
      await apiPost('/api/reports', {
        target_type: targetType,
        target_id: targetId,
        reason: reason.trim(),
      });
      setMsg('举报已提交');
      setTimeout(() => { onReported?.(); onClose(); }, 500);
    } catch (e) {
      setMsg((e as ApiError).message);
    } finally {
      setSubmitting(false);
    }
  };

  const typeLabels: Record<string, string> = {
    post: '帖子', guestbook: '留言', comment: '评论', skill: '技能', review: '评测',
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
      <div className="mx-4 w-full max-w-md rounded-lg border border-border/40 bg-background p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="font-serif text-lg font-bold flex items-center gap-2">
            <Shield className="h-5 w-5 text-red-500" />举报{typeLabels[targetType] || targetType}
          </h3>
          <button type="button" onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium">原因 *</label>
            <textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={3} placeholder="描述举报原因"
              className="w-full rounded-lg border border-border/40 bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30" />
          </div>
          {msg && <p className={`text-sm ${msg.includes('提交') ? 'text-green-500' : 'text-red-500'}`}>{msg}</p>}
          <button type="button" onClick={handleSubmit} disabled={submitting}
            className="flex items-center gap-2 rounded-lg bg-red-500 px-4 py-2 text-sm font-medium text-white hover:bg-red-600 disabled:opacity-50">
            {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}提交举报
          </button>
        </div>
      </div>
    </div>
  );
}

export function ReportButton({ targetType, targetId, onReported }: {
  targetType: 'post' | 'guestbook' | 'comment' | 'skill' | 'review';
  targetId: number;
  onReported?: () => void;
}) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button type="button" onClick={() => setOpen(true)}
        className="flex items-center gap-1 rounded-lg px-2 py-1 text-xs text-muted-foreground hover:bg-accent hover:text-foreground"
        title="举报">
        <Shield className="h-3.5 w-3.5" />
      </button>
      {open && <ReportModal targetType={targetType} targetId={targetId} onClose={() => setOpen(false)} onReported={onReported} />}
    </>
  );
}
