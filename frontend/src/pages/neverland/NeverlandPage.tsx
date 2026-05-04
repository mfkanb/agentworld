import { useState, useEffect, useCallback } from 'react';
import {
  Droplets, Scissors, Coins, Star, Trophy, Sprout,
  Loader2, Home, Gift, Swords, Plus
} from 'lucide-react';
import { apiGet, apiPost } from '../../lib/api';
import type { ApiError } from '../../lib/api';

export default function NeverlandPage() {
  const [farm, setFarm] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);
  const [needsRegister, setNeedsRegister] = useState(false);
  const [regName, setRegName] = useState('');
  const [regDesc, setRegDesc] = useState('');
  const [regLoading, setRegLoading] = useState(false);
  const [tab, setTab] = useState<'farm' | 'crops' | 'buildings' | 'achievements' | 'social'>('farm');

  const fetchFarm = useCallback(async () => {
    try {
      const data = await apiGet('/api/neverland/farm');
      setFarm(data as Record<string, unknown>);
    } catch {
      setNeedsRegister(true);
    }
    setLoading(false);
  }, []);

  useEffect(() => { fetchFarm(); }, [fetchFarm]);

  const handleRegister = async () => {
    if (!regName.trim()) return;
    setRegLoading(true);
    try {
      await apiPost('/api/neverland/farm/register', { name: regName.trim(), description: regDesc.trim() });
      setNeedsRegister(false);
      fetchFarm();
    } catch (e) {
      alert((e as ApiError).message);
    } finally {
      setRegLoading(false);
    }
  };

  if (loading) return <div className="flex justify-center py-12"><Loader2 className="h-8 w-8 animate-spin text-muted-foreground" /></div>;

  if (needsRegister) {
    return (
      <div className="mx-auto max-w-6xl px-6 py-8">
        <h1 className="font-serif text-3xl font-bold">NeverLand</h1>
        <div className="mt-8 max-w-md rounded-lg border border-border/40 bg-card/60 p-6">
          <h2 className="font-serif text-xl font-bold">注册农场</h2>
          <div className="mt-4 space-y-4">
            <div>
              <label className="mb-1 block text-sm font-medium">农场名称 *</label>
              <input value={regName} onChange={(e) => setRegName(e.target.value)} placeholder="给你的农场起个名字"
                className="w-full rounded-lg border border-border/40 bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30" />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">描述</label>
              <textarea value={regDesc} onChange={(e) => setRegDesc(e.target.value)} rows={2}
                className="w-full rounded-lg border border-border/40 bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30" />
            </div>
            <button type="button" onClick={handleRegister} disabled={regLoading}
              className="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50">
              {regLoading ? '注册中...' : '注册'}
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (!farm) return null;

  const plots = (farm.plots as Record<string, unknown>[]) || [];
  const level = Number(farm.level || 1);
  const gold = Number(farm.gold || 0);
  const xp = Number(farm.xp || 0);
  const reputation = Number(farm.reputation || 0);

  return (
    <div className="mx-auto max-w-6xl px-6 py-8">
      <h1 className="font-serif text-3xl font-bold">NeverLand</h1>
      <p className="mt-2 text-muted-foreground">农场养成 — 种植、建造、社交</p>

      {/* Farm stats */}
      <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className="rounded-lg border border-border/40 bg-card/60 p-4 text-center">
          <Star className="mx-auto h-5 w-5 text-amber-500" /><p className="mt-1 text-xl font-bold">{level}</p><p className="text-xs text-muted-foreground">等级</p>
        </div>
        <div className="rounded-lg border border-border/40 bg-card/60 p-4 text-center">
          <Coins className="mx-auto h-5 w-5 text-yellow-500" /><p className="mt-1 text-xl font-bold">{gold}</p><p className="text-xs text-muted-foreground">金币</p>
        </div>
        <div className="rounded-lg border border-border/40 bg-card/60 p-4 text-center">
          <Sprout className="mx-auto h-5 w-5 text-green-500" /><p className="mt-1 text-xl font-bold">{xp}</p><p className="text-xs text-muted-foreground">XP</p>
        </div>
        <div className="rounded-lg border border-border/40 bg-card/60 p-4 text-center">
          <Trophy className="mx-auto h-5 w-5 text-purple-500" /><p className="mt-1 text-xl font-bold">{reputation}</p><p className="text-xs text-muted-foreground">声誉</p>
        </div>
      </div>

      {/* Tabs */}
      <div className="mt-6 flex flex-wrap gap-2">
        {[
          { key: 'farm' as const, label: '农田' },
          { key: 'crops' as const, label: '作物' },
          { key: 'buildings' as const, label: '建筑' },
          { key: 'achievements' as const, label: '成就' },
          { key: 'social' as const, label: '社交' },
        ].map(({ key, label }) => (
          <button key={key} type="button" onClick={() => setTab(key)}
            className={`rounded-lg px-4 py-1.5 text-sm font-medium ${tab === key ? 'bg-primary text-primary-foreground' : 'bg-accent text-muted-foreground hover:text-foreground'}`}>
            {label}
          </button>
        ))}
      </div>

      <div className="mt-6">
        {tab === 'farm' && <PlotGrid plots={plots} onAction={fetchFarm} />}
        {tab === 'crops' && <CropList />}
        {tab === 'buildings' && <BuildingList gold={gold} onAction={fetchFarm} />}
        {tab === 'achievements' && <AchievementList />}
        {tab === 'social' && <SocialPanel onAction={fetchFarm} />}
      </div>
    </div>
  );
}

/* ─── Plot Grid ─── */
function PlotGrid({ plots, onAction }: { plots: Record<string, unknown>[]; onAction: () => void }) {
  const [acting, setActing] = useState<number | null>(null);
  const [plantCrop, setPlantCrop] = useState('');
  const [selectedPlot, setSelectedPlot] = useState<number | null>(null);
  const [crops, setCrops] = useState<Record<string, unknown>[]>([]);

  useEffect(() => {
    apiGet<Record<string, unknown>[]>('/api/neverland/farm/crops').then((d) => setCrops(d || [])).catch(() => {});
  }, []);

  const handleAction = async (index: number, action: 'plant' | 'water' | 'harvest') => {
    setActing(index);
    try {
      if (action === 'plant') {
        if (!plantCrop) return;
        await apiPost(`/api/neverland/farm/plots/${index}/plant`, { crop_type: plantCrop });
      } else {
        await apiPost(`/api/neverland/farm/plots/${index}/${action === 'water' ? 'water' : 'harvest'}`);
      }
      onAction();
    } catch (e) {
      alert((e as ApiError).message);
    } finally {
      setActing(null);
      setSelectedPlot(null);
    }
  };

  const statusColors: Record<string, string> = {
    empty: 'bg-accent border-dashed',
    planted: 'bg-green-500/10 border-green-500/30',
    grown: 'bg-amber-500/10 border-amber-500/30',
    ready: 'bg-yellow-500/10 border-yellow-500/30',
  };

  return (
    <div className="space-y-4">
      <h2 className="font-serif text-lg font-semibold">农田 ({plots.length} 块)</h2>
      <div className="grid grid-cols-3 gap-3 sm:grid-cols-6">
        {plots.map((plot, i) => {
          const status = String(plot.status || 'empty');
          return (
            <div key={i} className={`rounded-lg border p-3 text-center ${statusColors[status] || statusColors.empty}`}>
              <p className="text-xs font-medium">{status === 'empty' ? '空闲' : String(plot.crop_type || '?')}</p>
              <p className="text-[10px] text-muted-foreground">#{i + 1}</p>
              <div className="mt-2 space-y-1">
                {status === 'empty' && (
                  <button type="button" onClick={() => setSelectedPlot(i)} className="w-full rounded bg-primary/80 px-1 py-0.5 text-[10px] text-primary-foreground">
                    <Sprout className="inline h-3 w-3" />
                  </button>
                )}
                {status === 'planted' && (
                  <button type="button" onClick={() => handleAction(i, 'water')} disabled={acting === i}
                    className="w-full rounded bg-blue-500/80 px-1 py-0.5 text-[10px] text-white">
                    <Droplets className="inline h-3 w-3" />
                  </button>
                )}
                {(status === 'grown' || status === 'ready') && (
                  <button type="button" onClick={() => handleAction(i, 'harvest')} disabled={acting === i}
                    className="w-full rounded bg-amber-500/80 px-1 py-0.5 text-[10px] text-white">
                    <Scissors className="inline h-3 w-3" />
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Plant selection modal */}
      {selectedPlot !== null && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={() => setSelectedPlot(null)}>
          <div className="w-full max-w-sm rounded-xl border border-border/40 bg-card p-6" onClick={(e) => e.stopPropagation()}>
            <h3 className="font-serif text-lg font-bold">选择作物 - 农田 #{selectedPlot + 1}</h3>
            <div className="mt-4 space-y-2">
              {crops.map((crop) => (
                <button key={String(crop.name)} type="button"
                  onClick={() => { setPlantCrop(String(crop.name)); handleAction(selectedPlot, 'plant'); }}
                  className="w-full rounded-lg border border-border/40 p-3 text-left hover:bg-accent">
                  <p className="font-medium">{String(crop.name)}</p>
                  <p className="text-xs text-muted-foreground">种子 {String(crop.seed_price)}金 · {String(crop.growth_days)}天成熟 · 收益 {String(crop.harvest_value)}金</p>
                </button>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ─── Crop List ─── */
function CropList() {
  const [crops, setCrops] = useState<Record<string, unknown>[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiGet<Record<string, unknown>[]>('/api/neverland/farm/crops').then((d) => setCrops(d || [])).catch(() => {}).finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="flex justify-center py-8"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>;

  return (
    <div>
      <h2 className="font-serif text-lg font-semibold mb-4">作物列表</h2>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {crops.map((crop) => (
          <div key={String(crop.name)} className="rounded-lg border border-border/40 bg-card/60 p-4">
            <h3 className="font-medium">{String(crop.name)}</h3>
            <p className="mt-1 text-sm text-muted-foreground">种子 {String(crop.seed_price)}金 · {String(crop.growth_days)}天 · 收益 {String(crop.harvest_value)}金</p>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ─── Building List ─── */
function BuildingList({ gold, onAction }: { gold: number; onAction: () => void }) {
  const [buildings, setBuildings] = useState<Record<string, unknown>[]>([]);
  const [loading, setLoading] = useState(true);
  const [building, setBuilding] = useState(false);

  useEffect(() => {
    apiGet<Record<string, unknown>[]>('/api/neverland/farm/buildings').then((d) => setBuildings(d || [])).catch(() => {}).finally(() => setLoading(false));
  }, []);

  const handleBuild = async (type: string) => {
    setBuilding(true);
    try {
      await apiPost('/api/neverland/farm/buildings', { building_type: type });
      alert('建造成功！');
      onAction();
    } catch (e) {
      alert((e as ApiError).message);
    } finally {
      setBuilding(false);
    }
  };

  const BUILDING_DEFS = [
    { type: 'chicken_coop', name: '鸡舍', price: 100 },
    { type: 'barn', name: '畜棚', price: 200 },
    { type: 'warehouse', name: '仓库', price: 150 },
    { type: 'greenhouse', name: '温室', price: 300 },
  ];

  if (loading) return <div className="flex justify-center py-8"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>;

  const builtTypes = new Set(buildings.map((b) => String(b.building_type || b.type || '')));

  return (
    <div className="space-y-6">
      <div>
        <h2 className="font-serif text-lg font-semibold mb-4">已建建筑</h2>
        {buildings.length === 0 ? <p className="text-muted-foreground">暂无建筑</p> : (
          <div className="grid gap-3 sm:grid-cols-2">
            {buildings.map((b, i) => (
              <div key={i} className="flex items-center gap-3 rounded-lg border border-border/40 bg-card/60 p-4">
                <Home className="h-6 w-6 text-emerald-500" />
                <div>
                  <p className="font-medium">{String(b.building_type || b.type || '建筑')}</p>
                  <p className="text-xs text-muted-foreground">等级 {String(b.level || 1)}</p>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
      <div>
        <h2 className="font-serif text-lg font-semibold mb-4">可建造</h2>
        <div className="grid gap-3 sm:grid-cols-2">
          {BUILDING_DEFS.filter((d) => !builtTypes.has(d.type)).map((d) => (
            <div key={d.type} className="flex items-center justify-between rounded-lg border border-border/40 bg-card/60 p-4">
              <div>
                <p className="font-medium">{d.name}</p>
                <p className="text-sm text-muted-foreground">{d.price} 金币</p>
              </div>
              <button type="button" onClick={() => handleBuild(d.type)} disabled={building || gold < d.price}
                className="flex items-center gap-1 rounded-lg bg-primary px-3 py-1.5 text-sm text-primary-foreground hover:bg-primary/90 disabled:opacity-50">
                <Plus className="h-4 w-4" />建造
              </button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ─── Achievement List ─── */
function AchievementList() {
  const [achievements, setAchievements] = useState<Record<string, unknown>[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiGet<Record<string, unknown>[]>('/api/neverland/farm/achievements').then((d) => setAchievements(d || [])).catch(() => {}).finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="flex justify-center py-8"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>;

  return (
    <div>
      <h2 className="font-serif text-lg font-semibold mb-4 flex items-center gap-2"><Trophy className="h-5 w-5" />成就</h2>
      <div className="grid gap-3 sm:grid-cols-2">
        {achievements.map((a, i) => {
          const unlocked = Boolean(a.unlocked);
          return (
            <div key={i} className={`rounded-lg border p-4 ${unlocked ? 'border-amber-500/30 bg-amber-500/5' : 'border-border/40 bg-card/60'}`}>
              <h3 className="font-medium">{String(a.name || '成就')}</h3>
              <p className="mt-1 text-sm text-muted-foreground">{String(a.description || '')}</p>
              {unlocked && <p className="mt-2 text-xs text-amber-500">已解锁! +{String(a.gold_reward || 0)}金 +{String(a.xp_reward || 0)}XP</p>}
            </div>
          );
        })}
      </div>
      {achievements.length === 0 && <p className="text-muted-foreground">暂无成就数据</p>}
    </div>
  );
}

/* ─── Social Panel ─── */
function SocialPanel({ onAction }: { onAction: () => void }) {
  const [target, setTarget] = useState('');
  const [amount, setAmount] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSteal = async () => {
    if (!target.trim()) return;
    setLoading(true);
    try {
      await apiPost('/api/neverland/farm/steal', { target_username: target.trim() });
      alert('偷窃操作完成！');
      onAction();
    } catch (e) { alert((e as ApiError).message); }
    finally { setLoading(false); }
  };

  const handleGift = async () => {
    if (!target.trim() || !amount) return;
    setLoading(true);
    try {
      await apiPost('/api/neverland/farm/gift', { target_username: target.trim(), amount: Number(amount) });
      alert('赠送成功！+2 声誉');
      onAction();
    } catch (e) { alert((e as ApiError).message); }
    finally { setLoading(false); }
  };

  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <div className="rounded-lg border border-border/40 bg-card/60 p-6">
        <h3 className="font-serif text-lg font-semibold flex items-center gap-2"><Swords className="h-5 w-5 text-red-500" />偷窃</h3>
        <p className="mt-2 text-sm text-muted-foreground">偷取目标成熟作物（每日3次）</p>
        <input value={target} onChange={(e) => setTarget(e.target.value)} placeholder="目标用户名"
          className="mt-3 w-full rounded-lg border border-border/40 bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30" />
        <button type="button" onClick={handleSteal} disabled={loading}
          className="mt-3 rounded-lg bg-red-500 px-4 py-2 text-sm font-medium text-white hover:bg-red-600 disabled:opacity-50">
          偷窃
        </button>
      </div>
      <div className="rounded-lg border border-border/40 bg-card/60 p-6">
        <h3 className="font-serif text-lg font-semibold flex items-center gap-2"><Gift className="h-5 w-5 text-green-500" />赠送</h3>
        <p className="mt-2 text-sm text-muted-foreground">赠送金币给好友（+2 声誉）</p>
        <input value={target} onChange={(e) => setTarget(e.target.value)} placeholder="目标用户名"
          className="mt-3 w-full rounded-lg border border-border/40 bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30" />
        <input value={amount} onChange={(e) => setAmount(e.target.value)} type="number" placeholder="金额"
          className="mt-2 w-full rounded-lg border border-border/40 bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary/30" />
        <button type="button" onClick={handleGift} disabled={loading}
          className="mt-3 rounded-lg bg-green-500 px-4 py-2 text-sm font-medium text-white hover:bg-green-600 disabled:opacity-50">
          赠送
        </button>
      </div>
    </div>
  );
}
