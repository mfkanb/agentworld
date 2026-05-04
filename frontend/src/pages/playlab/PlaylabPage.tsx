import { useState, useEffect, useCallback } from 'react';
import {
  Plus, Loader2, Users, Play,
  ChevronRight, RefreshCw
} from 'lucide-react';
import { apiGet, apiPost } from '../../lib/api';
import type { ApiError } from '../../lib/api';

export default function PlaylabPage() {
  const [view, setView] = useState<'lobby' | 'room'>('lobby');
  const [roomId, setRoomId] = useState<number | null>(null);

  return (
    <div className="mx-auto max-w-6xl px-6 py-8">
      <h1 className="font-serif text-3xl font-bold">PlayLab</h1>
      <p className="mt-2 text-muted-foreground">桌游对战 — 五子棋、德州扑克、谁是卧底</p>

      <div className="mt-6">
        {view === 'lobby' && (
          <Lobby onSelectRoom={(id) => { setRoomId(id); setView('room'); }} />
        )}
        {view === 'room' && roomId && (
          <GameRoom id={roomId} onBack={() => setView('lobby')} />
        )}
      </div>
    </div>
  );
}

/* ─── Lobby ─── */
function Lobby({ onSelectRoom }: { onSelectRoom: (id: number) => void }) {
  const [rooms, setRooms] = useState<Record<string, unknown>[]>([]);
  const [loading, setLoading] = useState(true);
  const [gameType, setGameType] = useState('gomoku');
  const [creating, setCreating] = useState(false);

  const fetchRooms = useCallback(async () => {
    try {
      const data = await apiGet<{ items: Record<string, unknown>[] }>('/api/playlab/rooms?limit=20');
      setRooms(data.items || []);
    } catch { /* ignore */ }
    setLoading(false);
  }, []);

  useEffect(() => { fetchRooms(); }, [fetchRooms]);

  const handleCreate = async () => {
    setCreating(true);
    try {
      const data = await apiPost<{ id: number }>('/api/playlab/rooms', { game_type: gameType });
      onSelectRoom(data.id);
    } catch (e) {
      alert((e as ApiError).message);
    } finally {
      setCreating(false);
    }
  };

  const handleJoin = async (id: number) => {
    try {
      await apiPost(`/api/playlab/rooms/${id}/join`);
      onSelectRoom(id);
    } catch (e) {
      alert((e as ApiError).message);
    }
  };

  const GAME_TYPES: Record<string, { label: string; desc: string; players: number }> = {
    gomoku: { label: '五子棋', desc: '15x15棋盘，先连五子获胜', players: 2 },
    poker: { label: '德州扑克', desc: '经典扑克对战', players: 6 },
    werewolf: { label: '谁是卧底', desc: '描述词语，找出卧底', players: 8 },
  };

  return (
    <div className="space-y-6">
      {/* Create room */}
      <div className="rounded-lg border border-border/40 bg-card/60 p-6">
        <h2 className="font-serif text-xl font-bold">创建房间</h2>
        <div className="mt-4 flex flex-wrap gap-3">
          {Object.entries(GAME_TYPES).map(([key, { label, desc, players }]) => (
            <button key={key} type="button" onClick={() => setGameType(key)}
              className={`rounded-lg border p-4 text-left transition-colors ${
                gameType === key ? 'border-primary bg-primary/5' : 'border-border/40 hover:bg-accent'
              }`}>
              <p className="font-medium">{label}</p>
              <p className="text-xs text-muted-foreground">{desc} · {players}人</p>
            </button>
          ))}
        </div>
        <button type="button" onClick={handleCreate} disabled={creating}
          className="mt-4 flex items-center gap-2 rounded-lg bg-primary px-4 py-2 font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50">
          <Plus className="h-4 w-4" />{creating ? '创建中...' : '创建房间'}
        </button>
      </div>

      {/* Room list */}
      <div>
        <div className="flex items-center justify-between">
          <h2 className="font-serif text-xl font-bold">等待中的房间</h2>
          <button type="button" onClick={fetchRooms} className="text-sm text-muted-foreground hover:text-foreground">
            <RefreshCw className="inline h-4 w-4" /> 刷新
          </button>
        </div>
        {loading ? (
          <div className="flex justify-center py-8"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
        ) : rooms.length === 0 ? (
          <p className="py-8 text-center text-muted-foreground">暂无等待中的房间</p>
        ) : (
          <div className="mt-4 space-y-3">
            {rooms.map((room) => {
              const gt = String(room.game_type || '');
              const info = GAME_TYPES[gt];
              return (
                <div key={String(room.id)} className="flex items-center justify-between rounded-lg border border-border/40 bg-card/60 p-4">
                  <div>
                    <p className="font-medium">{info?.label || gt}</p>
                    <p className="text-sm text-muted-foreground">
                      <Users className="inline h-4 w-4 mr-1" />
                      {String(room.current_players || 0)}/{String(room.max_players || info?.players || '?')}
                      <span className="ml-2">by {String(room.creator_name || '未知')}</span>
                    </p>
                  </div>
                  <button type="button" onClick={() => handleJoin(Number(room.id))}
                    className="flex items-center gap-1 rounded-lg bg-primary px-4 py-1.5 text-sm text-primary-foreground hover:bg-primary/90">
                    加入<ChevronRight className="h-4 w-4" />
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

/* ─── Game Room ─── */
function GameRoom({ id, onBack }: { id: number; onBack: () => void }) {
  const [state, setState] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);
  const [starting, setStarting] = useState(false);

  const fetchState = useCallback(async () => {
    try {
      const data = await apiGet(`/api/playlab/rooms/${id}/state`);
      setState(data as Record<string, unknown>);
    } catch { /* ignore */ }
    setLoading(false);
  }, [id]);

  useEffect(() => { fetchState(); }, [fetchState]);

  // Auto-refresh for active games
  useEffect(() => {
    if (!state) return;
    const status = String(state.status || '');
    if (status === 'playing') {
      const interval = setInterval(fetchState, 3000);
      return () => clearInterval(interval);
    }
  }, [state, fetchState]);

  const handleStart = async () => {
    setStarting(true);
    try {
      await apiPost(`/api/playlab/rooms/${id}/start`);
      fetchState();
    } catch (e) {
      alert((e as ApiError).message);
    } finally {
      setStarting(false);
    }
  };

  const handleAction = async (action: string, extra?: Record<string, number>) => {
    try {
      await apiPost(`/api/playlab/rooms/${id}/action`, { action, ...extra });
      fetchState();
    } catch (e) {
      alert((e as ApiError).message);
    }
  };

  if (loading) return <div className="flex justify-center py-12"><Loader2 className="h-8 w-8 animate-spin text-muted-foreground" /></div>;
  if (!state) return <p className="text-red-500">房间不存在</p>;

  const status = String(state.status || '');
  const gameType = String(state.game_type || '');
  const players = (state.players as Record<string, unknown>[]) || [];

  return (
    <div className="space-y-6">
      <button type="button" onClick={onBack} className="text-sm text-muted-foreground hover:text-foreground">&larr; 返回大厅</button>

      {/* Room info */}
      <div className="flex items-center justify-between rounded-lg border border-border/40 bg-card/60 p-4">
        <div>
          <h2 className="font-serif text-xl font-bold">房间 #{id}</h2>
          <p className="text-sm text-muted-foreground">
            {gameType} · {status === 'waiting' ? '等待中' : status === 'playing' ? '游戏中' : '已结束'}
          </p>
        </div>
        {status === 'waiting' && (
          <button type="button" onClick={handleStart} disabled={starting}
            className="flex items-center gap-2 rounded-lg bg-primary px-4 py-2 font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50">
            <Play className="h-4 w-4" />{starting ? '...' : '开始游戏'}
          </button>
        )}
      </div>

      {/* Players */}
      <div className="rounded-lg border border-border/40 bg-card/60 p-4">
        <h3 className="font-semibold mb-3">玩家 ({players.length})</h3>
        <div className="flex flex-wrap gap-2">
          {players.map((p, i) => (
            <span key={i} className="rounded-full bg-accent px-3 py-1 text-sm">
              {String(p.nickname || p.username || `Player ${i}`)}
            </span>
          ))}
        </div>
      </div>

      {/* Game-specific views */}
      {status === 'playing' && gameType === 'gomoku' && (
        <GomokuBoard state={state} onAction={handleAction} />
      )}
      {status === 'playing' && gameType === 'poker' && (
        <PokerView state={state} onAction={handleAction} />
      )}
      {status === 'playing' && gameType === 'werewolf' && (
        <WerewolfView state={state} onAction={handleAction} />
      )}
      {status === 'finished' && (
        <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-6 text-center">
          <Trophy className="mx-auto h-10 w-10 text-amber-500" />
          <p className="mt-4 font-serif text-xl font-bold">游戏结束</p>
          {state.winner ? <p className="mt-2 text-muted-foreground">{"获胜者：" + String(state.winner)}</p> : null}
        </div>
      )}
    </div>
  );
}

function Trophy(props: { className?: string }) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className={props.className}>
      <path d="M6 9H4.5a2.5 2.5 0 0 1 0-5H6"/><path d="M18 9h1.5a2.5 2.5 0 0 0 0-5H18"/><path d="M4 22h16"/><path d="M10 14.66V17c0 .55-.47.98-.97 1.21C7.85 18.75 7 20.24 7 22"/><path d="M14 14.66V17c0 .55.47.98.97 1.21C16.15 18.75 17 20.24 17 22"/><path d="M18 2H6v7a6 6 0 0 0 12 0V2Z"/>
    </svg>
  );
}

/* ─── Gomoku Board ─── */
function GomokuBoard({ state, onAction }: { state: Record<string, unknown>; onAction: (action: string, extra?: Record<string, number>) => void }) {
  const board = (state.board as number[][]) || Array(15).fill(null).map(() => Array(15).fill(0));
  const myTurn = Boolean(state.my_turn);

  return (
    <div>
      <p className="mb-3 text-sm text-muted-foreground">{myTurn ? '轮到你了（黑子）' : '等待对方落子...'}</p>
      <div className="inline-grid gap-0 border border-border/40 bg-accent/30 p-1" style={{ gridTemplateColumns: `repeat(15, 1fr)` }}>
        {board.map((row, r) =>
          row.map((cell, c) => (
            <button key={`${r}-${c}`} type="button" disabled={!myTurn || cell !== 0}
              onClick={() => onAction('place', { row: r, col: c })}
              className={`flex h-6 w-6 items-center justify-center border border-border/20 text-xs transition-colors hover:bg-accent/50 disabled:cursor-default sm:h-8 sm:w-8 ${
                cell === 1 ? 'bg-gray-800 text-white' : cell === 2 ? 'bg-white text-gray-800' : ''
              }`}>
            </button>
          ))
        )}
      </div>
    </div>
  );
}

/* ─── Poker View ─── */
function PokerView({ state, onAction }: { state: Record<string, unknown>; onAction: (action: string, extra?: Record<string, number>) => void }) {
  const communityCards = (state.community_cards as string[]) || [];
  const myHand = (state.my_hand as string[]) || [];
  const pot = Number(state.pot || 0);
  const phase = String(state.phase || '');
  const myTurn = Boolean(state.my_turn);
  const myChips = Number(state.my_chips || 0);
  const currentBet = Number(state.current_bet || 0);
  const [raiseAmount, setRaiseAmount] = useState('');

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-border/40 bg-card/60 p-4">
        <p className="text-sm text-muted-foreground">阶段：{phase} · 底池：<span className="font-bold text-foreground">{pot}</span></p>
      </div>

      {/* Community cards */}
      <div className="flex gap-2 justify-center">
        {communityCards.map((card, i) => (
          <span key={i} className="flex h-12 w-8 items-center justify-center rounded border bg-card text-xs font-mono sm:h-16 sm:w-10">
            {card}
          </span>
        ))}
        {Array(5 - communityCards.length).fill(null).map((_, i) => (
          <span key={`empty-${i}`} className="flex h-12 w-8 items-center justify-center rounded border border-dashed border-border/40 text-xs text-muted-foreground sm:h-16 sm:w-10">
            ?
          </span>
        ))}
      </div>

      {/* My hand */}
      <div className="text-center">
        <p className="text-sm text-muted-foreground mb-2">我的底牌 (筹码: {myChips})</p>
        <div className="flex gap-2 justify-center">
          {myHand.map((card, i) => (
            <span key={i} className="flex h-16 w-10 items-center justify-center rounded border border-primary/30 bg-primary/5 text-sm font-mono font-bold">
              {card}
            </span>
          ))}
        </div>
      </div>

      {/* Actions */}
      {myTurn && (
        <div className="flex flex-wrap gap-2 justify-center">
          <button type="button" onClick={() => onAction('call')}
            className="rounded-lg bg-primary px-4 py-2 text-sm text-primary-foreground hover:bg-primary/90">
            跟注 {currentBet}
          </button>
          <div className="flex gap-1">
            <input type="number" value={raiseAmount} onChange={(e) => setRaiseAmount(e.target.value)} placeholder="加注额"
              className="w-24 rounded-lg border border-border/40 bg-background px-2 py-2 text-sm" />
            <button type="button" onClick={() => { if (raiseAmount) onAction('raise', { amount: Number(raiseAmount) }); }}
              className="rounded-lg bg-amber-500 px-4 py-2 text-sm text-white hover:bg-amber-600">
              加注
            </button>
          </div>
          <button type="button" onClick={() => onAction('fold')}
            className="rounded-lg border border-border/40 px-4 py-2 text-sm hover:bg-accent">
            弃牌
          </button>
          <button type="button" onClick={() => onAction('allin')}
            className="rounded-lg bg-red-500 px-4 py-2 text-sm text-white hover:bg-red-600">
            全押
          </button>
        </div>
      )}
    </div>
  );
}

/* ─── Werewolf View ─── */
function WerewolfView({ state, onAction }: { state: Record<string, unknown>; onAction: (action: string, extra?: Record<string, number>) => void }) {
  const phase = String(state.phase || '');
  const myWord = String(state.my_word || '');
  const isMyTurn = Boolean(state.is_my_turn);
  const alivePlayers = (state.alive_players as Record<string, unknown>[]) || [];
  const [description, setDescription] = useState('');
  const [voteTarget, setVoteTarget] = useState('');

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-border/40 bg-card/60 p-4">
        <p className="text-sm text-muted-foreground">阶段：{phase === 'describe' ? '描述' : '投票'}</p>
        <p className="mt-2">你的词：<span className="font-bold text-primary">{myWord}</span></p>
      </div>

      {/* Alive players */}
      <div>
        <h3 className="text-sm font-medium mb-2">存活玩家</h3>
        <div className="flex flex-wrap gap-2">
          {alivePlayers.map((p, i) => (
            <span key={i} className="rounded-full bg-accent px-3 py-1 text-sm">
              {String(p.nickname || p.username || `P${i}`)}
            </span>
          ))}
        </div>
      </div>

      {/* Describe phase */}
      {phase === 'describe' && isMyTurn && (
        <div className="flex gap-3">
          <input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="描述你的词..."
            className="flex-1 rounded-lg border border-border/40 bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30" />
          <button type="button" onClick={() => { if (description.trim()) { onAction('describe'); setDescription(''); } }}
            className="rounded-lg bg-primary px-4 py-2 text-sm text-primary-foreground hover:bg-primary/90">
            描述
          </button>
        </div>
      )}

      {/* Vote phase */}
      {phase === 'vote' && (
        <div className="space-y-3">
          <p className="text-sm">投票选择淘汰对象：</p>
          <div className="flex flex-wrap gap-2">
            {alivePlayers.map((p, i) => (
              <button key={i} type="button"
                onClick={() => setVoteTarget(String(i))}
                className={`rounded-lg border px-3 py-1.5 text-sm ${
                  voteTarget === String(i) ? 'border-red-500 bg-red-500/10' : 'border-border/40 hover:bg-accent'
                }`}>
                {String(p.nickname || p.username || `P${i}`)}
              </button>
            ))}
          </div>
          <button type="button" disabled={!voteTarget}
            onClick={() => { if (voteTarget) onAction('vote', { row: Number(voteTarget) }); }}
            className="rounded-lg bg-red-500 px-4 py-2 text-sm text-white hover:bg-red-600 disabled:opacity-50">
            投票淘汰
          </button>
        </div>
      )}
    </div>
  );
}
