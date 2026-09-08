import {
  ArrowRight,
  Bookmark,
  Building2,
  Check,
  ChevronDown,
  CircleUserRound,
  ClipboardList,
  Copy,
  ExternalLink,
  History,
  Link2,
  LockKeyhole,
  MapPin,
  Menu,
  Minus,
  Phone,
  Plus,
  Search,
  Sparkles,
  Target,
  UserRound,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import fallbackOmega from "@/assets/omega-office.jpg";
import {
  type Company,
  type HuntPayload,
  type KpItem,
  type MetaPayload,
  type Role,
  authStatus,
  clearSession,
  fetchMeta,
  listKp,
  login,
  pollHunt,
  shareCreate,
  shareEnter,
  startHunt,
  takeToKp,
} from "@/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

type Screen = "setup" | "search" | "results" | "saved";

type LeadView = {
  key: string;
  inn: string;
  name: string;
  address: string;
  company: string;
  person: string;
  role: string;
  phone: string;
  revenue: string;
  profit: string;
  expense: string;
  image: string;
  status: string;
  tone: "good" | "warn" | "bad";
  site?: string;
  vkLpr?: string;
  maps?: string;
  hint?: string;
};

function presenceValue(c: Company, key: string): string {
  const item = c.presence?.[key];
  return String(item?.value || "").trim();
}

function normalizePhoto(url: string): string {
  return String(url || "").replace(/\/(%s?|\{s\}|\{size\})$/i, "/orig");
}

export function companyToLead(c: Company, index: number): LeadView {
  const obj = c.object || {};
  const stampRaw = String(c.stamp || c.stamp_label || "").toLowerCase();
  const tone: LeadView["tone"] = /стоп|отказ|плох/.test(stampRaw)
    ? "bad"
    : /осторож|слаб/.test(stampRaw)
      ? "warn"
      : "good";
  const photos = (c.photos?.length
    ? c.photos
    : Array.isArray(c.presence?.photos?.value)
      ? (c.presence?.photos?.value as string[])
      : []
  )
    .map(normalizePhoto)
    .filter((u) => /^https?:\/\//i.test(u));
  const phone =
    presenceValue(c, "phone") ||
    String(c.presence?.recommend?.value || "").replace(/^.*?(\+?\d[\d\s\-()]{8,}).*$/, "$1").trim();
  const recPhone = /^\+?\d/.test(phone) ? phone : presenceValue(c, "phone");
  return {
    key: c.inn || `lead-${index}`,
    inn: c.inn || "",
    name: obj.title || c.name || "Объект",
    address: obj.address || c.object_address || c.address || "Адрес уточняется",
    company: c.name || "—",
    person: c.management_label || c.management || "Директор не найден",
    role: c.management_post || "ЛПР / директор",
    phone: recPhone || "нет телефона",
    revenue: c.revenue_text || "—",
    profit: c.profit_text || "—",
    expense: c.expense_text || "—",
    image: photos[0] || fallbackOmega,
    status: c.stamp_label || `${c.stamp || "лид"} · ${c.score ?? "—"}/99`,
    tone,
    site: presenceValue(c, "site") || undefined,
    vkLpr: presenceValue(c, "vk_lpr") || undefined,
    maps: obj.maps_yandex,
    hint: c.stamp_hint,
  };
}

function kpToLead(it: KpItem, index: number): LeadView {
  return {
    key: it.inn || `kp-${index}`,
    inn: it.inn || "",
    name: it.object_title || it.name || "Объект",
    address: it.object_address || it.address || "",
    company: it.name || "—",
    person: it.management || "—",
    role: "В КП",
    phone: it.phone || "—",
    revenue: "—",
    profit: "—",
    expense: "—",
    image: (it.photos || [])[0] || fallbackOmega,
    status: "В КП",
    tone: "good",
  };
}

function Brand() {
  return (
    <div className="flex items-center gap-2.5" aria-label="ОХОТА">
      <span className="relative grid size-7 place-items-center rounded-full border border-primary text-primary">
        <Target className="size-4" />
      </span>
      <span className="font-display text-lg font-bold">ОХОТА</span>
    </div>
  );
}

export default function App() {
  const [boot, setBoot] = useState(true);
  const [loggedIn, setLoggedIn] = useState(false);
  const [role, setRole] = useState<Role>(null);
  const [screen, setScreen] = useState<Screen>("setup");
  const [linkOpen, setLinkOpen] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [meta, setMeta] = useState<MetaPayload | null>(null);
  const [hunt, setHunt] = useState<HuntPayload | null>(null);
  const [kpItems, setKpItems] = useState<KpItem[]>([]);
  const [authError, setAuthError] = useState("");

  const reloadKp = useCallback(async () => {
    try {
      const data = await listKp();
      setKpItems(data.items || []);
    } catch {
      /* ignore for guests without access */
    }
  }, []);

  const enterApp = useCallback(async (nextRole: Role) => {
    setRole(nextRole);
    setLoggedIn(true);
    const m = await fetchMeta();
    setMeta(m);
    await reloadKp();
  }, [reloadKp]);

  useEffect(() => {
    const tg = window.Telegram?.WebApp;
    tg?.ready?.();
    tg?.expand?.();

    (async () => {
      try {
        const params = new URLSearchParams(location.search);
        const share = params.get("s") || "";
        if (share) {
          await shareEnter(share);
          const u = new URL(location.href);
          u.searchParams.delete("s");
          history.replaceState({}, "", u.pathname + u.search);
        }
        const auth = await authStatus();
        if (auth.ok) {
          await enterApp(auth.role);
        } else {
          setLoggedIn(false);
        }
      } catch (err) {
        setAuthError(err instanceof Error ? err.message : String(err));
        setLoggedIn(false);
      } finally {
        setBoot(false);
      }
    })();
  }, [enterApp]);

  const go = (next: Screen) => {
    setScreen(next);
    setMobileOpen(false);
    if (next === "saved") reloadKp().catch(() => undefined);
  };

  if (boot) {
    return (
      <div className="grid min-h-screen place-items-center bg-background text-muted-foreground">
        Загрузка…
      </div>
    );
  }

  if (!loggedIn) {
    return (
      <LoginScreen
        error={authError}
        onLogin={async (password) => {
          setAuthError("");
          try {
            const data = await login(password);
            await enterApp(data.role || "staff");
          } catch (err) {
            setAuthError(err instanceof Error ? err.message : String(err));
          }
        }}
      />
    );
  }

  return (
    <div className="min-h-screen bg-background text-foreground">
      <AppHeader
        screen={screen}
        go={go}
        onLink={() => setLinkOpen(true)}
        onMenu={() => setMobileOpen(true)}
        canShare={role === "staff" || role === "telegram"}
      />
      <main className="mx-auto w-full max-w-[1440px] px-4 pb-24 pt-8 sm:px-6 lg:px-10 lg:pb-10 lg:pt-12">
        {role === "guest" && (
          <div className="mb-5 rounded-lg border border-primary/30 bg-accent p-3 text-sm text-primary">
            Гостевой доступ по одноразовой ссылке. Ссылка привязана к этому устройству.
          </div>
        )}
        {screen === "setup" && meta && (
          <SetupScreen
            meta={meta}
            role={role}
            onStart={async (payload) => {
              setScreen("search");
              setHunt({ status: "queued", progress: "В очереди…", companies: [], target_count: Number(payload.count) || 10 });
              try {
                const started = await startHunt(payload);
                const id = started.id;
                const tick = async () => {
                  const data = await pollHunt(id);
                  setHunt(data);
                  if (data.status === "done" || data.status === "error") {
                    setScreen("results");
                    return;
                  }
                  window.setTimeout(() => {
                    tick().catch((err) => {
                      setHunt({ status: "error", errors: [String(err)], companies: [] });
                      setScreen("results");
                    });
                  }, 2500);
                };
                await tick();
              } catch (err) {
                setHunt({
                  status: "error",
                  errors: [err instanceof Error ? err.message : String(err)],
                  companies: [],
                });
                setScreen("results");
              }
            }}
          />
        )}
        {screen === "search" && <SearchScreen hunt={hunt} />}
        {screen === "results" && (
          <ResultsScreen
            hunt={hunt}
            onTakeKp={async (inn) => {
              await takeToKp(inn);
              setHunt((prev) =>
                prev
                  ? {
                      ...prev,
                      companies: (prev.companies || []).filter((c) => c.inn !== inn),
                    }
                  : prev,
              );
              await reloadKp();
            }}
          />
        )}
        {screen === "saved" && <SavedScreen items={kpItems} onRefresh={reloadKp} />}
      </main>
      <MobileNav screen={screen} go={go} onLink={() => setLinkOpen(true)} canShare={role === "staff" || role === "telegram"} />
      {mobileOpen && (
        <MobileMenu
          screen={screen}
          go={go}
          onClose={() => setMobileOpen(false)}
          onLink={() => setLinkOpen(true)}
          canShare={role === "staff" || role === "telegram"}
          onLogout={() => {
            clearSession();
            setLoggedIn(false);
          }}
        />
      )}
      {linkOpen && <CreateLinkModal onClose={() => setLinkOpen(false)} />}
    </div>
  );
}

function LoginScreen({ onLogin, error }: { onLogin: (password: string) => Promise<void>; error?: string }) {
  const [tab, setTab] = useState<"team" | "guest">("team");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <main className="login-grid min-h-screen bg-background">
      <section className="flex min-h-[52vh] flex-col justify-between px-6 py-7 sm:px-10 lg:min-h-screen lg:px-16 lg:py-10">
        <Brand />
        <div className="max-w-xl py-14 lg:py-10">
          <p className="mb-8 max-w-40 text-sm text-muted-foreground">Больше клиентов в реальном мире</p>
          <h1 className="font-display text-4xl font-semibold leading-[1.02] sm:text-6xl lg:text-7xl">
            Находим <span className="block text-primary">реальных клиентов</span> по зданиям
          </h1>
          <p className="mt-6 max-w-lg text-base leading-7 text-muted-foreground sm:text-lg">
            Собственники, операторы, ЛПР и контакты — готовые к работе.
          </p>
        </div>
        <p className="text-xs text-muted-foreground">NITEOS · Lead Radar</p>
      </section>
      <section className="relative flex items-center justify-center overflow-hidden border-l border-border px-5 py-10 lg:min-h-screen">
        <img src={fallbackOmega} alt="" className="absolute inset-0 h-full w-full object-cover opacity-25 grayscale" width={960} height={640} />
        <div className="absolute inset-0 bg-login-overlay" />
        <div className="relative w-full max-w-md rounded-lg border border-border bg-card/95 p-5 shadow-2xl backdrop-blur sm:p-7">
          <div className="mb-6 grid grid-cols-2 rounded-md border border-border bg-secondary p-1">
            <Button variant="ghost" onClick={() => setTab("team")} className={cn("h-10", tab === "team" && "bg-accent text-primary")}>Вход для команды</Button>
            <Button variant="ghost" onClick={() => setTab("guest")} className={cn("h-10", tab === "guest" && "bg-accent text-primary")}>Гостевой доступ</Button>
          </div>
          {tab === "team" ? (
            <>
              <label className="mb-2 block text-xs font-medium text-muted-foreground">Пароль команды</label>
              <div className="relative">
                <LockKeyhole className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && password && !busy) {
                      setBusy(true);
                      onLogin(password).finally(() => setBusy(false));
                    }
                  }}
                  placeholder="Введите пароль"
                  className="h-12 pl-10"
                />
              </div>
              {error ? <p className="mt-3 text-sm text-destructive">{error}</p> : null}
              <Button
                disabled={!password || busy}
                onClick={() => {
                  setBusy(true);
                  onLogin(password).finally(() => setBusy(false));
                }}
                className="mt-5 h-12 w-full font-semibold"
              >
                Войти <ArrowRight />
              </Button>
            </>
          ) : (
            <div className="space-y-3 text-sm leading-6 text-muted-foreground">
              <p>Гостевой вход — только по одноразовой ссылке от менеджера.</p>
              <p>Откройте ссылку вида <code className="text-primary">/?s=…</code> — пароль не нужен.</p>
              {error ? <p className="text-destructive">{error}</p> : null}
            </div>
          )}
        </div>
      </section>
    </main>
  );
}

function AppHeader({
  screen,
  go,
  onLink,
  onMenu,
  canShare,
}: {
  screen: Screen;
  go: (s: Screen) => void;
  onLink: () => void;
  onMenu: () => void;
  canShare: boolean;
}) {
  return (
    <header className="sticky top-0 z-30 border-b border-border bg-background/90 backdrop-blur-xl">
      <div className="mx-auto grid h-16 max-w-[1440px] grid-cols-[minmax(0,1fr)_auto] items-center gap-4 px-4 sm:px-6 lg:flex lg:h-20 lg:px-10">
        <div className="min-w-0 lg:mr-auto"><Brand /></div>
        <nav className="hidden items-center gap-1 lg:flex" aria-label="Основная навигация">
          <NavButton active={screen === "setup" || screen === "search"} onClick={() => go("setup")} icon={<Target />}>Новая охота</NavButton>
          <NavButton active={screen === "saved"} onClick={() => go("saved")} icon={<Bookmark />}>Сохранённые</NavButton>
          <NavButton active={screen === "results"} onClick={() => go("results")} icon={<History />}>Результаты</NavButton>
          {canShare && <NavButton onClick={onLink} icon={<Link2 />}>Ссылка клиенту</NavButton>}
        </nav>
        <Button variant="ghost" size="icon" className="hidden rounded-full bg-secondary lg:inline-flex" aria-label="Профиль"><CircleUserRound /></Button>
        <Button variant="ghost" size="icon" className="lg:hidden" onClick={onMenu} aria-label="Открыть меню"><Menu /></Button>
      </div>
    </header>
  );
}

function NavButton({ children, icon, active = false, onClick }: { children: React.ReactNode; icon: React.ReactNode; active?: boolean; onClick: () => void }) {
  return <Button variant="ghost" onClick={onClick} className={cn("h-10 gap-2 px-4 text-muted-foreground", active && "bg-accent text-primary")}>{icon}{children}</Button>;
}

function PageTitle({ eyebrow, title, text }: { eyebrow: string; title: string; text: string }) {
  return <header className="mb-8"><p className="mb-3 text-xs font-semibold uppercase text-primary">{eyebrow}</p><h1 className="font-display text-3xl font-semibold sm:text-4xl lg:text-5xl">{title}</h1><p className="mt-3 max-w-2xl text-sm leading-6 text-muted-foreground sm:text-base">{text}</p></header>;
}

function SetupScreen({
  meta,
  role,
  onStart,
}: {
  meta: MetaPayload;
  role: Role;
  onStart: (payload: Record<string, unknown>) => Promise<void>;
}) {
  const counts = meta.counts?.length ? meta.counts : [1, 5, 10];
  const [count, setCount] = useState(counts.includes(10) ? 10 : counts[0]);
  const [geoAll, setGeoAll] = useState(true);
  const [cities, setCities] = useState<string[]>([]);
  const [regions, setRegions] = useState<string[]>([]);
  const [geoQ, setGeoQ] = useState("");
  const [openSphere, setOpenSphere] = useState<string | null>(meta.spheres[0]?.id || null);
  const [selected, setSelected] = useState<Record<string, Set<string>>>({});
  const [phrase, setPhrase] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const flat = meta.geo?.flat || [];
  const districts = meta.geo?.districts || [];
  const suggestions = useMemo(() => {
    const q = geoQ.trim().toLowerCase();
    if (!q) return flat.slice(0, 12);
    return flat.filter((x) =>
      [x.title, x.label, x.dadata_region].filter(Boolean).some((v) => String(v).toLowerCase().includes(q)),
    ).slice(0, 16);
  }, [flat, geoQ]);

  const toggleOption = (sphereId: string, optionId: string) => {
    setSelected((prev) => {
      const next = { ...prev };
      const set = new Set(next[sphereId] || []);
      if (set.has(optionId)) set.delete(optionId);
      else set.add(optionId);
      next[sphereId] = set;
      return next;
    });
  };

  const start = async () => {
    setErr("");
    const spheres = Object.keys(selected).filter((id) => (selected[id]?.size || 0) > 0);
    const search_queries: string[] = [];
    for (const s of meta.spheres) {
      for (const opt of s.options) {
        if (selected[s.id]?.has(opt.id)) search_queries.push(opt.query);
      }
    }
    if (!phrase.trim() && !search_queries.length) {
      setErr("Выберите тип здания или укажите имя объекта.");
      return;
    }
    setBusy(true);
    try {
      await onStart({
        phrase: phrase.trim(),
        count,
        spheres,
        search_queries,
        cities: geoAll ? [] : cities,
        regions: geoAll ? [] : regions,
      });
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  };

  return (
    <div>
      <PageTitle eyebrow="Новая охота" title="Настройка поиска" text="Укажите параметры — найдём объекты, юрлица и контакты ЛПР." />
      <div className="grid gap-5 lg:grid-cols-2">
        <section className="panel p-5 sm:p-7">
          <h2 className="mb-5 font-display text-lg font-semibold">География</h2>
          <div className="mb-4 flex flex-wrap gap-2">
            <Button size="sm" variant={geoAll ? "default" : "outline"} onClick={() => { setGeoAll(true); setCities([]); setRegions([]); }}>Вся Россия</Button>
            {districts.slice(0, 6).map((d) => (
              <Button key={d.id} size="sm" variant="outline" onClick={() => {
                const regs = flat.filter((x) => x.kind === "region" && x.fo === d.title);
                setGeoAll(false);
                setRegions((prev) => {
                  const names = regs.map((r) => r.dadata_region || r.title);
                  return [...new Set([...prev, ...names])];
                });
              }}>{d.title.replace(" федеральный округ", "")}</Button>
            ))}
          </div>
          {(cities.length > 0 || regions.length > 0) && (
            <div className="mb-4 flex flex-wrap gap-2">
              {cities.map((c) => (
                <span key={c} className="tag">{c}<button type="button" onClick={() => setCities((prev) => prev.filter((x) => x !== c))}><X className="size-3" /></button></span>
              ))}
              {regions.map((r) => (
                <span key={r} className="tag">рег. {r}<button type="button" onClick={() => setRegions((prev) => prev.filter((x) => x !== r))}><X className="size-3" /></button></span>
              ))}
            </div>
          )}
          <Input value={geoQ} onChange={(e) => setGeoQ(e.target.value)} placeholder="Поиск: Казань, Самара…" className="h-11" />
          {geoQ && (
            <div className="mt-2 max-h-48 overflow-auto rounded-md border border-border">
              {suggestions.map((item) => (
                <button
                  key={`${item.kind}-${item.title}`}
                  type="button"
                  className="block w-full border-b border-border px-3 py-2 text-left text-sm last:border-0 hover:bg-accent"
                  onClick={() => {
                    setGeoAll(false);
                    if (item.kind === "region") setRegions((prev) => prev.includes(item.dadata_region || item.title) ? prev : [...prev, item.dadata_region || item.title]);
                    else setCities((prev) => prev.includes(item.title) ? prev : [...prev, item.title]);
                    setGeoQ("");
                  }}
                >
                  {item.label || item.title}
                  <span className="ml-2 text-xs text-muted-foreground">{item.kind === "region" ? "регион" : "город"}</span>
                </button>
              ))}
            </div>
          )}
        </section>
        <section className="panel p-5 sm:p-7">
          <h2 className="mb-5 font-display text-lg font-semibold">Типы зданий</h2>
          <div className="space-y-3">
            {meta.spheres.map((s) => {
              const open = openSphere === s.id;
              const picked = selected[s.id]?.size || 0;
              return (
                <div key={s.id} className="rounded-md border border-border">
                  <button type="button" className="flex w-full items-center justify-between gap-3 px-3 py-3 text-left" onClick={() => setOpenSphere(open ? null : s.id)}>
                    <span className="text-sm font-semibold">{s.title}{picked ? ` · ${picked}` : ""}</span>
                    <ChevronDown className={cn("size-4 text-muted-foreground transition", open && "rotate-180")} />
                  </button>
                  {open && (
                    <div className="flex flex-wrap gap-2 border-t border-border p-3">
                      {s.options.map((o) => (
                        <Button key={o.id} size="sm" variant={selected[s.id]?.has(o.id) ? "default" : "outline"} onClick={() => toggleOption(s.id, o.id)}>{o.label}</Button>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
          <label className="mt-5 mb-2 block text-xs text-muted-foreground">Уточнение объекта (необязательно)</label>
          <Input value={phrase} onChange={(e) => setPhrase(e.target.value)} placeholder="Например: Мега, Кольцо, Южный" className="h-11" />
        </section>
      </div>
      <section className="mt-5 grid gap-5 lg:grid-cols-[1fr_280px]">
        <div className="panel flex flex-col justify-between gap-6 p-5 sm:flex-row sm:items-center sm:p-7">
          <div>
            <h2 className="font-display text-lg font-semibold">Количество объектов</h2>
            <p className="mt-1 text-sm text-muted-foreground">{role === "guest" ? "Для гостя — до 5" : "Рекомендуем 5–20 для быстрого прогона"}</p>
          </div>
          <div className="flex items-center gap-3">
            <Button variant="outline" size="icon" onClick={() => setCount((c) => counts[Math.max(0, counts.indexOf(c) - 1)] || counts[0])}><Minus /></Button>
            <span className="w-12 text-center font-display text-xl font-semibold">{count}</span>
            <Button variant="outline" size="icon" onClick={() => setCount((c) => counts[Math.min(counts.length - 1, counts.indexOf(c) + 1)] || counts[counts.length - 1])}><Plus /></Button>
          </div>
        </div>
        <Button disabled={busy} onClick={start} className="h-auto min-h-20 text-base font-semibold">Начать охоту <ArrowRight /></Button>
      </section>
      {err ? <p className="mt-3 text-sm text-destructive">{err}</p> : null}
      <div className="mt-5 grid gap-px overflow-hidden rounded-lg border border-border bg-border sm:grid-cols-3">
        <Feature icon={<MapPin />} title="Ищем здания" text="и проверяем их" />
        <Feature icon={<Building2 />} title="Находим компании" text="и собственников" />
        <Feature icon={<UserRound />} title="Собираем контакты" text="и делаем фото" />
      </div>
    </div>
  );
}

function Feature({ icon, title, text }: { icon: React.ReactNode; title: string; text: string }) {
  return <div className="flex items-center gap-4 bg-card p-5"><span className="grid size-11 shrink-0 place-items-center rounded-full bg-accent text-primary">{icon}</span><div><p className="text-sm font-semibold">{title}</p><p className="text-xs text-muted-foreground">{text}</p></div></div>;
}

function SearchScreen({ hunt }: { hunt: HuntPayload | null }) {
  const target = Math.max(1, Number(hunt?.target_count) || 10);
  const found = (hunt?.companies || []).length;
  const status = hunt?.status || "running";
  const progressText = hunt?.progress || "Собираем данные…";
  const pct = status === "done" ? 100 : Math.min(95, Math.round((found / target) * 80) + 12);
  const stages = [
    ["Ищем объекты на карте", pct > 15],
    ["Определяем собственников и операторов", pct > 35 || found > 0],
    ["Ищем контакты и ЛПР", pct > 55 || found > 0],
    ["Собираем фото фасадов", pct > 75],
    ["Формируем результаты", status === "done"],
  ] as const;
  const etaMin = Math.max(1, Math.ceil(((target - found) * 2.5 + 1)));
  return (
    <div>
      <PageTitle eyebrow="Поиск запущен" title="Идёт сбор данных" text="Это может занять несколько минут. Можно оставить вкладку открытой." />
      <div className="grid gap-5 lg:grid-cols-[1fr_360px]">
        <section className="panel p-5 sm:p-8">
          <div className="mb-3 flex items-end justify-between">
            <span className="text-sm">Карточек <b>{found}</b> из {target}</span>
            <b className="font-display text-lg text-primary">{pct}%</b>
          </div>
          <div className="mb-2 h-2 overflow-hidden rounded-full bg-secondary">
            <div className="h-full rounded-full bg-primary transition-[width] duration-500" style={{ width: `${pct}%` }} />
          </div>
          <p className="mb-8 text-sm text-muted-foreground">{progressText} · ещё примерно ~{etaMin} мин</p>
          <div className="space-y-2">
            {stages.map(([label, done], index) => (
              <div key={label} className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-4 rounded-md border border-border p-4">
                <span className={cn("grid size-9 shrink-0 place-items-center rounded-full bg-secondary text-muted-foreground", done && "bg-accent text-primary")}>
                  {index === 0 ? <MapPin /> : index === 1 ? <Building2 /> : index === 2 ? <UserRound /> : index === 3 ? <ClipboardList /> : <Sparkles />}
                </span>
                <span className="min-w-0 text-sm font-medium">{label}</span>
                <span className={cn("text-xs text-muted-foreground", done && "text-primary")}>{done ? "Готово" : "В процессе…"}</span>
              </div>
            ))}
          </div>
        </section>
        <aside className="panel overflow-hidden">
          <img src={fallbackOmega} alt="" className="aspect-[4/3] w-full object-cover" width={960} height={640} />
          <div className="p-5">
            <p className="font-display text-lg font-semibold">Охота активна</p>
            <p className="mt-1 text-sm text-muted-foreground">Здание → юрлицо → ФИО → контакты</p>
          </div>
        </aside>
      </div>
    </div>
  );
}

function ResultsScreen({
  hunt,
  onTakeKp,
}: {
  hunt: HuntPayload | null;
  onTakeKp: (inn: string) => Promise<void>;
}) {
  const [query, setQuery] = useState("");
  const companies = hunt?.companies || [];
  const leads = useMemo(() => companies.map(companyToLead), [companies]);
  const filtered = useMemo(
    () =>
      leads.filter((lead) =>
        [lead.name, lead.company, lead.person, lead.inn, lead.address]
          .join(" ")
          .toLowerCase()
          .includes(query.toLowerCase()),
      ),
    [leads, query],
  );

  if (hunt?.status === "error") {
    return (
      <div className="panel p-8 text-center">
        <h2 className="font-display text-xl font-semibold text-destructive">Охота завершилась с ошибкой</h2>
        <p className="mt-2 text-sm text-muted-foreground">{(hunt.errors || []).join("; ") || "Попробуйте ещё раз"}</p>
      </div>
    );
  }

  if (!companies.length) {
    return (
      <div className="panel p-8 text-center">
        <h2 className="font-display text-xl font-semibold">Пока нет карточек</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          Принятых зданий с подтверждённым собственником нет. Уточните город / тип и запустите снова.
        </p>
      </div>
    );
  }

  return (
    <div>
      <div className="mb-8">
        <PageTitle
          eyebrow="Результаты охоты"
          title={`Найдено ${companies.length} объектов`}
          text={(hunt?.queries || []).slice(0, 4).join(" · ") || "Контакты и ЛПР собраны по найденным зданиям."}
        />
      </div>
      <div className="relative mb-5 max-w-md">
        <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Поиск по объектам" className="h-11 pl-10" />
      </div>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {filtered.map((lead) => (
          <LeadCard key={lead.key} lead={lead} onTakeKp={onTakeKp} />
        ))}
      </div>
    </div>
  );
}

function LeadCard({ lead, onTakeKp }: { lead: LeadView; onTakeKp: (inn: string) => Promise<void> }) {
  const [busy, setBusy] = useState(false);
  const phoneHref = lead.phone && lead.phone !== "нет телефона"
    ? `tel:${lead.phone.replace(/[^\d+]/g, "")}`
    : undefined;
  return (
    <article className="panel overflow-hidden">
      <div className="relative">
        <img src={lead.image} alt={lead.name} className="aspect-[16/9] w-full object-cover" loading="lazy" width={960} height={640} onError={(e) => { (e.currentTarget as HTMLImageElement).src = fallbackOmega; }} />
        <span className={cn("status-pill absolute left-3 top-3", `status-${lead.tone}`)}>{lead.status}</span>
      </div>
      <div className="p-5">
        <h2 className="font-display text-lg font-semibold">{lead.name}</h2>
        <p className="mt-1 flex items-center gap-1.5 text-xs text-muted-foreground">
          <MapPin className="size-3.5" />{lead.address}
          {lead.maps ? <a href={lead.maps} target="_blank" rel="noreferrer" className="text-primary">карта</a> : null}
        </p>
        <div className="my-4 border-y border-border py-4">
          <p className="text-sm font-medium">{lead.company}</p>
          <p className="mt-1 text-xs text-muted-foreground">ИНН {lead.inn || "—"}</p>
        </div>
        <p className="mb-2 text-xs text-muted-foreground">Кому звонить</p>
        <div className="flex items-center gap-3">
          <span className="grid size-10 shrink-0 place-items-center rounded-full bg-secondary"><UserRound /></span>
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold">{lead.person}</p>
            <p className="truncate text-xs text-muted-foreground">{lead.role}</p>
          </div>
        </div>
        <div className="mt-4 flex items-center justify-between gap-2">
          {phoneHref ? (
            <a href={phoneHref} className="flex items-center gap-2 text-sm"><Phone className="size-4 text-primary" />{lead.phone}</a>
          ) : (
            <span className="flex items-center gap-2 text-sm text-muted-foreground"><Phone className="size-4" />{lead.phone}</span>
          )}
          {lead.vkLpr ? <a href={lead.vkLpr} target="_blank" rel="noreferrer"><ExternalLink className="size-4 text-muted-foreground" /></a> : null}
        </div>
        <p className="mt-4 text-xs text-muted-foreground">
          Выручка: <span className="text-foreground">{lead.revenue}</span>
          {" · "}Прибыль: <span className="text-foreground">{lead.profit}</span>
          {" · "}Расходы: <span className="text-foreground">{lead.expense}</span>
        </p>
        {lead.hint ? <p className="mt-2 text-xs text-muted-foreground">{lead.hint}</p> : null}
        <div className="mt-5 grid grid-cols-[minmax(0,1fr)_auto] gap-2">
          <Button
            disabled={!lead.inn || busy}
            onClick={async () => {
              if (!lead.inn) return;
              setBusy(true);
              try {
                await onTakeKp(lead.inn);
              } finally {
                setBusy(false);
              }
            }}
          >
            {busy ? "Сохраняю…" : "Взять в КП"}
          </Button>
          {lead.site ? (
            <Button
              variant="outline"
              size="icon"
              onClick={() => {
                const href = lead.site!.startsWith("http") ? lead.site! : `https://${lead.site}`;
                window.open(href, "_blank", "noopener,noreferrer");
              }}
              aria-label="Сайт"
            >
              <ExternalLink />
            </Button>
          ) : (
            <Button variant="outline" size="icon" disabled aria-label="Нет сайта"><Bookmark /></Button>
          )}
        </div>
      </div>
    </article>
  );
}

function SavedScreen({ items, onRefresh }: { items: KpItem[]; onRefresh: () => Promise<void> }) {
  const leads = items.map(kpToLead);
  return (
    <div>
      <div className="mb-6 flex items-end justify-between gap-3">
        <PageTitle eyebrow="База контактов" title="Мои сохранённые лиды" text="Объекты, которые вы взяли в коммерческую проработку. Они больше не попадут в охоту." />
        <Button variant="outline" onClick={() => onRefresh()}>Обновить</Button>
      </div>
      {leads.length ? (
        <div className="panel overflow-hidden">
          {leads.map((lead) => (
            <div key={lead.key} className="grid grid-cols-[72px_minmax(0,1fr)_auto] items-center gap-4 border-b border-border p-3 last:border-b-0 sm:grid-cols-[90px_minmax(0,1fr)_120px_auto]">
              <img src={lead.image} alt="" className="h-14 w-[72px] rounded-md object-cover sm:w-[90px]" loading="lazy" onError={(e) => { (e.currentTarget as HTMLImageElement).src = fallbackOmega; }} />
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold">{lead.name}</p>
                <p className="mt-1 truncate text-xs text-muted-foreground">{lead.company}{lead.inn ? ` · ИНН ${lead.inn}` : ""}</p>
                {lead.person && lead.person !== "—" ? <p className="mt-1 truncate text-xs text-muted-foreground">{lead.person}{lead.phone && lead.phone !== "—" ? ` · ${lead.phone}` : ""}</p> : null}
              </div>
              <span className="status-pill status-good hidden sm:inline-flex">В КП</span>
              <Bookmark className="size-4 fill-current text-primary" />
            </div>
          ))}
        </div>
      ) : (
        <div className="panel grid min-h-72 place-items-center p-8 text-center">
          <div>
            <Bookmark className="mx-auto size-10 text-muted-foreground" />
            <h2 className="mt-4 font-display text-xl font-semibold">Сохранённых лидов пока нет</h2>
            <p className="mt-2 text-sm text-muted-foreground">Нажмите «Взять в КП» на карточке в результатах.</p>
          </div>
        </div>
      )}
    </div>
  );
}

function CreateLinkModal({ onClose }: { onClose: () => void }) {
  const [url, setUrl] = useState("");
  const [hint, setHint] = useState("Одноразовая ссылка: один вход, одно устройство.");
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState(false);
  const [hours, setHours] = useState(72);
  const create = async () => {
    setBusy(true);
    setCopied(false);
    try {
      const data = await shareCreate(hours);
      setUrl(data.url);
      setHint(data.hint || hint);
    } catch (err) {
      setHint(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-backdrop p-4" role="dialog" aria-modal="true">
      <div className="w-full max-w-lg rounded-lg border border-border bg-card p-5 shadow-2xl sm:p-7">
        <div className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-start gap-3">
          <span className="grid size-11 place-items-center rounded-full bg-accent text-primary"><Link2 /></span>
          <div>
            <h2 className="font-display text-xl font-semibold">Ссылка для клиента</h2>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">Одноразовая ссылка даст доступ без пароля. После входа сгорает.</p>
          </div>
          <Button variant="ghost" size="icon" onClick={onClose} aria-label="Закрыть"><X /></Button>
        </div>
        <div className="mt-6 grid gap-4 sm:grid-cols-2">
          <label className="text-xs text-muted-foreground">Срок
            <select className="field-button mt-2" value={hours} onChange={(e) => setHours(Number(e.target.value))}>
              <option value={24}>1 день</option>
              <option value={72}>3 дня</option>
              <option value={168}>7 дней</option>
            </select>
          </label>
          <label className="text-xs text-muted-foreground">Переходы
            <div className="field-button mt-2"><span>1 переход</span></div>
          </label>
        </div>
        <div className="mt-5 grid grid-cols-[minmax(0,1fr)_auto] gap-2">
          <Input readOnly value={url || "Сначала создайте ссылку"} />
          <Button
            disabled={!url}
            onClick={async () => {
              await navigator.clipboard?.writeText(url);
              setCopied(true);
            }}
          >
            {copied ? <Check /> : <Copy />}{copied ? "Готово" : "Копировать"}
          </Button>
        </div>
        <p className="mt-3 text-xs text-muted-foreground">{hint}</p>
        <Button className="mt-4 h-11 w-full" disabled={busy} onClick={create}>
          {busy ? "Создаю…" : url ? "Создать новую ссылку" : "Создать ссылку"}
        </Button>
      </div>
    </div>
  );
}

function MobileNav({
  screen,
  go,
  onLink,
  canShare,
}: {
  screen: Screen;
  go: (s: Screen) => void;
  onLink: () => void;
  canShare: boolean;
}) {
  return (
    <nav className="fixed inset-x-0 bottom-0 z-30 grid grid-cols-4 border-t border-border bg-card/95 px-2 pb-[max(.5rem,env(safe-area-inset-bottom))] pt-2 backdrop-blur lg:hidden">
      <MobileNavItem active={screen === "setup" || screen === "search"} onClick={() => go("setup")} icon={<Target />} label="Охота" />
      <MobileNavItem active={screen === "results"} onClick={() => go("results")} icon={<Search />} label="Результаты" />
      <MobileNavItem active={screen === "saved"} onClick={() => go("saved")} icon={<Bookmark />} label="Сохранённые" />
      <MobileNavItem onClick={canShare ? onLink : () => go("saved")} icon={<Link2 />} label={canShare ? "Ссылка" : "КП"} />
    </nav>
  );
}

function MobileNavItem({ active = false, onClick, icon, label }: { active?: boolean; onClick: () => void; icon: React.ReactNode; label: string }) {
  return <Button variant="ghost" onClick={onClick} className={cn("h-12 flex-col gap-1 px-1 text-[10px] text-muted-foreground", active && "text-primary")}>{icon}{label}</Button>;
}

function MobileMenu({
  screen,
  go,
  onClose,
  onLink,
  canShare,
  onLogout,
}: {
  screen: Screen;
  go: (s: Screen) => void;
  onClose: () => void;
  onLink: () => void;
  canShare: boolean;
  onLogout: () => void;
}) {
  return (
    <div className="fixed inset-0 z-50 bg-backdrop lg:hidden">
      <div className="ml-auto min-h-full w-[86%] max-w-sm border-l border-border bg-card p-5">
        <div className="mb-8 flex items-center justify-between"><Brand /><Button variant="ghost" size="icon" onClick={onClose}><X /></Button></div>
        <div className="space-y-2">
          <NavButton active={screen === "setup" || screen === "search"} onClick={() => go("setup")} icon={<Target />}>Новая охота</NavButton>
          <NavButton active={screen === "results"} onClick={() => go("results")} icon={<History />}>Результаты</NavButton>
          <NavButton active={screen === "saved"} onClick={() => go("saved")} icon={<Bookmark />}>Сохранённые</NavButton>
          {canShare && <NavButton onClick={() => { onLink(); onClose(); }} icon={<Link2 />}>Ссылка клиенту</NavButton>}
          <NavButton onClick={onLogout} icon={<LockKeyhole />}>Выйти</NavButton>
        </div>
      </div>
    </div>
  );
}
