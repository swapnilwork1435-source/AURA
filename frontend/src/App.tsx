import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { Activity, ArrowDownRight, ArrowUpRight, BarChart3, Bell, Check, ChevronLeft, ChevronRight, CircleHelp, ClipboardList, Droplets, Dumbbell, Flame, Heart, Home, LogOut, Moon, Pencil, Plus, Search, Settings, ShieldCheck, Sparkles, Trash2, TrendingUp, UserRound, Utensils, Weight, X } from "lucide-react";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

const API = "http://127.0.0.1:8000/api";
type Profile = { goal: string; onboarding_complete: boolean; birth_date?: string; gender?: string; activity_level: string; avoid_weight_recommendations?: boolean; targets_customized?: boolean; calculation_method?: string; calculation_inputs?: string; calculated_at?: string; surplus_kcal?: number; deficit_kcal?: number; training_days_per_week?: number; body_fat_percent?: number; current_weight_kg?: number; target_weight_kg?: number; calorie_target?: number; protein_target_g?: number; carbs_target_g?: number; fat_target_g?: number; water_target_ml?: number; height_cm?: number; units: string };
type User = { id: number; full_name: string; username: string; email: string; profile: Profile };
type Dashboard = { date: string; goal: string; weight_kg?: number; target_weight_kg?: number; calories: number; calorie_target?: number; protein_g: number; protein_target_g?: number; carbs_g: number; carbs_target_g?: number; fat_g: number; fat_target_g?: number; water_ml: number; water_target_ml: number; sleep_hours?: number; habits_done: number; habits_total: number };
type Food = { id: number; name: string; serving: string; calories: number; protein_g: number; carbs_g: number; fat_g: number; estimated: boolean };
type FoodEntry = { id: number; food_name: string; quantity: number; serving_unit: string; calories: number; protein_g: number; carbs_g: number; fat_g: number; meal: string };
type Plan = { id: number; name: string; exercises: string[] };
type WorkoutSession = { id: number; name: string; started_at: string; completed_at?: string; sets?: { exercise: string; set_number: number; weight_kg: number; reps: number; completed: boolean }[] };
type Measurement = { id: number; measured_on: string; weight_kg?: number; waist_cm?: number; chest_cm?: number };
type Habit = { id: number; name: string; category: string; completed: boolean };
type Routine = { id: number; name: string; routine_time: string; steps: string[]; completed: boolean };
type Reminder = { id: number; meal: string; local_date: string; status: string; snooze_minutes: number };
type ParsedMeal = { food_id: number; food_name: string; quantity: number; serving_unit: string; calories: number; protein_g: number; carbs_g: number; fat_g: number; assumption: string; estimated: boolean };
type AssistantResult = { kind: string; text: string; parsed?: { items: ParsedMeal[]; totals?: { calories: number; protein_g: number; carbs_g: number; fat_g: number }; clarification?: string } };
type Page = "Dashboard" | "Nutrition" | "Workouts" | "Body Progress" | "Looksmaxing" | "Daily Habits" | "Sleep & Recovery" | "Analytics" | "Automation" | "Profile" | "Settings";

function csrfToken() {
  return document.cookie.split("; ").find((part) => part.startsWith("aura_csrf="))?.split("=").slice(1).join("=") ?? "";
}
async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body) headers.set("Content-Type", "application/json");
  const token = csrfToken();
  if (token && options.method && options.method !== "GET") headers.set("X-CSRF-Token", decodeURIComponent(token));
  const response = await fetch(`${API}${path}`, { ...options, headers, credentials: "include" });
  if (!response.ok) {
    let message = `${response.status} ${response.statusText}`;
    try { message = (await response.json()).detail ?? message; } catch { /* Keep the HTTP message. */ }
    throw new Error(typeof message === "string" ? message : "Please check the fields and try again.");
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
const localDate = (date: Date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
const today = () => localDate(new Date());
const thisMonday = () => {
  const monday = new Date();
  monday.setDate(monday.getDate() - ((monday.getDay() + 6) % 7));
  return localDate(monday);
};
const entryDateTime = (day: string) => {
  const now = new Date();
  const hour = day === today() ? String(now.getHours()).padStart(2, "0") : "12";
  const minute = day === today() ? String(now.getMinutes()).padStart(2, "0") : "00";
  return `${day}T${hour}:${minute}:00`;
};
const displayDate = (date: Date) => date.toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" });
const navItems: { name: Page; icon: typeof Home }[] = [
  { name: "Dashboard", icon: Home }, { name: "Nutrition", icon: Utensils }, { name: "Workouts", icon: Dumbbell },
  { name: "Body Progress", icon: Weight }, { name: "Looksmaxing", icon: Sparkles }, { name: "Daily Habits", icon: ClipboardList },
  { name: "Sleep & Recovery", icon: Moon }, { name: "Analytics", icon: BarChart3 }, { name: "Automation", icon: Bell },
];
function Button({ children, onClick, variant = "primary", type = "button", disabled = false }: { children: React.ReactNode; onClick?: () => void; variant?: "primary" | "secondary" | "quiet" | "danger"; type?: "button" | "submit"; disabled?: boolean }) {
  return <button className={`button ${variant}`} onClick={onClick} type={type} disabled={disabled}>{children}</button>;
}
function Field({ label, ...props }: React.InputHTMLAttributes<HTMLInputElement> & { label: string }) {
  return <label className="field"><span>{label}</span><input {...props} /></label>;
}
function SelectField({ label, children, ...props }: React.SelectHTMLAttributes<HTMLSelectElement> & { label: string; children: React.ReactNode }) {
  return <label className="field"><span>{label}</span><select {...props}>{children}</select></label>;
}
function Panel({ title, action, children, className = "" }: { title: string; action?: React.ReactNode; children: React.ReactNode; className?: string }) {
  return <section className={`panel ${className}`}><div className="panel-head"><h2>{title}</h2>{action}</div>{children}</section>;
}
function Progress({ value, target, color = "lime" }: { value: number; target?: number; color?: string }) {
  const pct = target ? Math.min(value / target * 100, 100) : 0;
  return <div className={`progress ${color}`}><span style={{ width: `${pct}%` }} /></div>;
}

export default function App() {
  const [user, setUser] = useState<User | null>(null);
  const [page, setPage] = useState<Page>("Dashboard");
  const [dash, setDash] = useState<Dashboard | null>(null);
  const [selectedDay, setSelectedDay] = useState(today());
  const [foods, setFoods] = useState<Food[]>([]);
  const [entries, setEntries] = useState<FoodEntry[]>([]);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [sessions, setSessions] = useState<WorkoutSession[]>([]);
  const [activeWorkout, setActiveWorkout] = useState<WorkoutSession | null>(null);
  const [measurements, setMeasurements] = useState<Measurement[]>([]);
  const [habits, setHabits] = useState<Habit[]>([]);
  const [routines, setRoutines] = useState<Routine[]>([]);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [showFoodForm, setShowFoodForm] = useState(false);
  const [editingFoodId, setEditingFoodId] = useState<number | null>(null);
  const [foodForm, setFoodForm] = useState({ food_name: "", quantity: "1", serving_unit: "serving", calories: "0", protein_g: "0", carbs_g: "0", fat_g: "0", meal: "Breakfast", notes: "" });
  const [showPlanForm, setShowPlanForm] = useState(false);
  const [showHabitForm, setShowHabitForm] = useState(false);
  const [showRoutineForm, setShowRoutineForm] = useState(false);
  const [showWeightForm, setShowWeightForm] = useState(false);
  const [showSleepForm, setShowSleepForm] = useState(false);
  const [reminder, setReminder] = useState<Reminder | null>(null);
  const [assistantText, setAssistantText] = useState("");
  const [assistantResult, setAssistantResult] = useState<AssistantResult | null>(null);
  const [assistantMeal, setAssistantMeal] = useState("Breakfast");
  const [assistantBusy, setAssistantBusy] = useState(false);
  const [mealRequestKey, setMealRequestKey] = useState(() => crypto.randomUUID());

  const reloadData = useCallback(async (activeUser: User, day: string) => {
    const requests = await Promise.all([
      api<Dashboard>(`/dashboard?day=${day}`), api<{ totals: Record<string, number>; entries: FoodEntry[] }>(`/nutrition?day=${day}`),
      api<{ plans: Plan[]; sessions: WorkoutSession[] }>("/workouts"), api<Measurement[]>("/body"),
      api<Habit[]>(`/habits?day=${day}`), api<Routine[]>(`/skincare?day=${day}`), api<Food[]>("/foods"),
    ]);
    setDash(requests[0]); setEntries(requests[1].entries); setPlans(requests[2].plans); setSessions(requests[2].sessions);
    setMeasurements(requests[3]); setHabits(requests[4]); setRoutines(requests[5]); setFoods(requests[6]);
    setUser(activeUser);
  }, []);
  const refresh = useCallback(async () => {
    if (!user) return;
    try { await reloadData(user, selectedDay); } catch (err) { setError(err instanceof Error ? err.message : "Could not load your data."); }
  }, [user, selectedDay, reloadData]);
  useEffect(() => {
    api<User>("/auth/me").then(async (activeUser) => {
      setUser(activeUser);
      await reloadData(activeUser, selectedDay);
    }).catch(() => setUser(null));
  }, [reloadData, selectedDay]);
  useEffect(() => {
    if (!user?.profile?.onboarding_complete) return;
    let active = true;
    const poll = async () => {
      try {
        const result = await api<{ reminders: Reminder[]; notifications_enabled: boolean }>("/reminders/due");
        if (!active || !result.reminders.length) return;
        setReminder((current) => current ?? result.reminders[0]);
        if (result.notifications_enabled && "Notification" in window && Notification.permission === "granted" && document.visibilityState === "visible") {
          new Notification("AURA meal reminder", { body: `Time to check in: ${result.reminders[0].meal}.` });
        }
      } catch (pollError) {
        if (active) setError(pollError instanceof Error ? pollError.message : "Could not check reminders.");
      }
    };
    void poll();
    const timer = window.setInterval(() => void poll(), 30_000);
    return () => { active = false; window.clearInterval(timer); };
  }, [user?.id, user?.profile?.onboarding_complete]);
  useEffect(() => {
    if (!notice && !error) return;
    const timer = window.setTimeout(() => { setNotice(""); setError(""); }, 4500);
    return () => window.clearTimeout(timer);
  }, [notice, error]);
  const run = async (action: () => Promise<unknown>, success = "Saved") => {
    setBusy(true); setError("");
    try { await action(); setNotice(success); await refresh(); }
    catch (err) { setError(err instanceof Error ? err.message : "Something went wrong."); }
    finally { setBusy(false); }
  };
  const selectFood = (food: Food) => setFoodForm({ food_name: food.name, quantity: "1", serving_unit: food.serving, calories: String(food.calories), protein_g: String(food.protein_g), carbs_g: String(food.carbs_g), fat_g: String(food.fat_g), meal: "Breakfast", notes: "" });
  const dateLabel = useMemo(() => displayDate(new Date(`${selectedDay}T12:00:00`)), [selectedDay]);

  if (!user) return <Auth onUser={(u) => { setUser(u); if (u.profile?.onboarding_complete) reloadData(u, selectedDay).catch((e) => setError(e.message)); }} />;
  if (!user.profile?.onboarding_complete) return <Onboarding user={user} onDone={async (u) => { setUser(u); await reloadData(u, selectedDay); }} />;

  async function saveFood(event: FormEvent) {
    event.preventDefault();
    await run(async () => {
      const path = editingFoodId ? `/nutrition/${editingFoodId}` : "/nutrition";
      const method = editingFoodId ? "PUT" : "POST";
      await api(path, { method, body: JSON.stringify({ ...foodForm, quantity: Number(foodForm.quantity), calories: Number(foodForm.calories), protein_g: Number(foodForm.protein_g), carbs_g: Number(foodForm.carbs_g), fat_g: Number(foodForm.fat_g), consumed_at: entryDateTime(selectedDay) }) });
      setEditingFoodId(null);
      setShowFoodForm(false); setFoodForm({ food_name: "", quantity: "1", serving_unit: "serving", calories: "0", protein_g: "0", carbs_g: "0", fat_g: "0", meal: "Breakfast", notes: "" });
    }, "Food logged");
  }
  async function savePlan(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = new FormData(event.currentTarget);
    await run(async () => { await api("/workouts/plans", { method: "POST", body: JSON.stringify({ name: form.get("name"), exercises: String(form.get("exercises")).split(",").map((x) => x.trim()).filter(Boolean) }) }); setShowPlanForm(false); }, "Workout plan created");
  }
  async function saveHabit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = new FormData(event.currentTarget);
    await run(async () => { await api("/habits", { method: "POST", body: JSON.stringify({ name: form.get("name"), category: form.get("category") }) }); setShowHabitForm(false); }, "Habit added");
  }
  async function saveRoutine(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = new FormData(event.currentTarget);
    await run(async () => { await api("/skincare", { method: "POST", body: JSON.stringify({ name: form.get("name"), routine_time: form.get("routine_time"), steps: String(form.get("steps")).split("\n").map((x) => x.trim()).filter(Boolean) }) }); setShowRoutineForm(false); }, "Routine saved");
  }
  async function saveMeasurement(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = new FormData(event.currentTarget);
    await run(async () => { await api("/body", { method: "POST", body: JSON.stringify({ measured_on: selectedDay, weight_kg: form.get("weight_kg") ? Number(form.get("weight_kg")) : null, waist_cm: form.get("waist_cm") ? Number(form.get("waist_cm")) : null, chest_cm: form.get("chest_cm") ? Number(form.get("chest_cm")) : null }) }); setShowWeightForm(false); }, "Progress recorded");
  }
  async function saveSleep(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = new FormData(event.currentTarget);
    await run(async () => { await api("/sleep", { method: "POST", body: JSON.stringify({ bedtime: `${form.get("bedtime_date")}T${form.get("bedtime")}:00`, wake_time: `${form.get("wake_date")}T${form.get("wake_time")}:00`, quality: Number(form.get("quality")) || null }) }); setShowSleepForm(false); }, "Sleep saved");
  }
  async function askAssistant(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAssistantBusy(true);
    setError("");
    try {
      const result = await api<AssistantResult>("/assistant/command", { method: "POST", body: JSON.stringify({ command_id: crypto.randomUUID(), text: assistantText }) });
      setAssistantResult(result);
      if (result.kind === "saved") {
        setNotice(result.text);
        setAssistantText("");
        await refresh();
      } else if (result.kind === "food" && result.parsed?.items.length) {
        setMealRequestKey(crypto.randomUUID());
      }
    } catch (err) { setError(err instanceof Error ? err.message : "The assistant could not process that request."); }
    finally { setAssistantBusy(false); }
  }
  async function confirmAssistantMeal() {
    if (!assistantResult?.parsed?.items.length) return;
    setAssistantBusy(true);
    try {
      const result = await api<{ entries: FoodEntry[]; duplicate: boolean }>("/assistant/confirm-meal", {
        method: "POST",
        body: JSON.stringify({
          idempotency_key: mealRequestKey,
          meal: assistantMeal,
          reminder_id: reminder?.id ?? null,
          consumed_at: entryDateTime(today()),
          items: assistantResult.parsed.items.map((item) => ({ food_id: item.food_id, quantity: item.quantity })),
        }),
      });
      setAssistantResult({ kind: "saved", text: result.duplicate ? "This meal was already saved." : `Saved ${result.entries.length} food item${result.entries.length === 1 ? "" : "s"} to ${assistantMeal}.` });
      setReminder(null);
      setAssistantText("");
      setMealRequestKey(crypto.randomUUID());
      setNotice(result.duplicate ? "Meal was already saved" : "Meal confirmed and saved");
      await refresh();
    } catch (err) { setError(err instanceof Error ? err.message : "Could not save this meal."); }
    finally { setAssistantBusy(false); }
  }
  async function respondToReminder(action: "open_log" | "not_yet" | "skip" | "dismiss") {
    if (!reminder) return;
    try {
      const response = await api<{ status: string; meal: string }>(`/reminders/${reminder.id}/action`, { method: "POST", body: JSON.stringify({ action }) });
      if (action === "open_log") {
        setAssistantMeal(response.meal);
        setAssistantResult(null);
        setAssistantText("");
        setPage("Dashboard");
      } else if (action === "not_yet") setNotice(`We'll remind you in ${reminder.snooze_minutes} minutes.`);
      setReminder(null);
    } catch (err) { setError(err instanceof Error ? err.message : "Could not update this reminder."); }
  }
  async function startWorkout(plan?: Plan) {
    await run(async () => { const session = await api<WorkoutSession>("/workouts/start", { method: "POST", body: JSON.stringify({ plan_id: plan?.id ?? null, name: plan?.name ?? "Quick session" }) }); setActiveWorkout(session); }, "Workout started");
  }
  async function logSet(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!activeWorkout) return;
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    await run(async () => { await api(`/workouts/${activeWorkout.id}/sets`, { method: "POST", body: JSON.stringify({ exercise: form.get("exercise"), set_number: Number(form.get("set_number")), weight_kg: Number(form.get("weight_kg")), reps: Number(form.get("reps")), completed: true }) }); formElement.reset(); }, "Set logged");
  }
  async function finishWorkout() {
    if (!activeWorkout) return;
    await run(async () => { await api(`/workouts/${activeWorkout.id}/finish`, { method: "POST" }); setActiveWorkout(null); }, "Workout completed");
  }
  const deleteAccount = async () => {
    if (!window.confirm("Delete your AURA account and all associated data? This cannot be undone.")) return;
    await run(async () => { await api("/account", { method: "DELETE" }); setUser(null); }, "Account deleted");
  };
  const signOut = async () => { try { await api("/auth/logout", { method: "POST" }); } finally { setUser(null); } };
  const calorieProgress = dash?.calorie_target ? dash.calories / dash.calorie_target * 100 : 0;
  const parsedMeal = assistantResult?.parsed;

  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><span className="brand-mark"><Sparkles size={18} /></span><span>AURA</span></div>
      <div className="side-caption">YOUR SPACE</div>
      <nav>{navItems.map(({ name, icon: Icon }) => <button className={`nav-item ${page === name ? "selected" : ""}`} key={name} onClick={() => setPage(name)}><Icon size={17} /><span>{name}</span>{page === name && <i />}</button>)}</nav>
      <div className="side-caption lower">ACCOUNT</div>
      <nav>{([{ name: "Profile", icon: UserRound }, { name: "Settings", icon: Settings }] as const).map(({ name, icon: Icon }) => <button className={`nav-item ${page === name ? "selected" : ""}`} key={name} onClick={() => setPage(name)}><Icon size={17} /><span>{name}</span></button>)}</nav>
      <div className="sidebar-bottom"><div className="avatar">{user.full_name.slice(0, 1).toUpperCase()}</div><div className="person"><b>{user.full_name}</b><span>{user.profile.goal}</span></div><button className="icon-button" aria-label="Sign out" onClick={signOut}><LogOut size={16} /></button></div>
    </aside>
    <main className="main-content">
      <header className="topbar">
        <div className="breadcrumb"><span>Workspace</span><span className="crumb-sep">/</span><b>{page}</b></div>
        <div className="top-actions"><span className="today-chip"><span className="live-dot" />{dateLabel}</span><button className="icon-button" title="Open reminder settings" aria-label="Open reminder settings" onClick={() => setPage("Settings")}><Bell size={17} /></button><button className="top-avatar" onClick={() => setPage("Profile")}>{user.full_name.slice(0, 1).toUpperCase()}</button></div>
      </header>
      {(notice || error) && <div className={`toast ${error ? "toast-error" : ""}`}>{error || notice}<button onClick={() => { setError(""); setNotice(""); }} aria-label="Dismiss"><X size={15} /></button></div>}
      <div className="page-wrap">
        {page === "Dashboard" && <section>
          <div className="welcome-row"><div><div className="eyebrow">YOUR PERSONAL WELLNESS SPACE</div><h1>Good {new Date().getHours() < 12 ? "morning" : new Date().getHours() < 18 ? "afternoon" : "evening"}, {user.full_name.split(" ")[0]} <span className="wave">✳</span></h1><p>A little progress each day adds up to remarkable results.</p></div>
            <div className="date-switch"><button className="icon-button" onClick={() => setSelectedDay(localDate(new Date(new Date(`${selectedDay}T12:00:00`).getTime() - 86400000)))}><ChevronLeft size={18} /></button><span>{selectedDay === today() ? "Today" : dateLabel}</span><button className="icon-button" disabled={selectedDay >= today()} onClick={() => setSelectedDay(localDate(new Date(new Date(`${selectedDay}T12:00:00`).getTime() + 86400000)))}><ChevronRight size={18} /></button></div>
          </div>
          <div className="hero-panel"><div className="hero-glow" /><div className="hero-copy"><span className="hero-kicker"><Sparkles size={14} /> YOUR FOCUS THIS SEASON</span><h2>{dash?.goal ?? user.profile.goal}</h2><p>Small, consistent choices build a stronger you. Keep showing up.</p><button className="hero-link" onClick={() => setPage("Profile")}>View your goals <ArrowUpRight size={15} /></button></div><div className="hero-stat"><div className="hero-stat-label">CURRENT WEIGHT</div><strong>{dash?.weight_kg ? `${dash.weight_kg.toFixed(1)}` : "—"} <small>kg</small></strong><span>{dash?.target_weight_kg ? `Target ${dash.target_weight_kg} kg` : "Add a target weight in your profile"}</span></div><div className="hero-symbol">◌</div></div>
          <div className="metrics-grid">
            <Metric icon={<Flame size={17} />} title="Calories" value={dash?.calories ?? 0} unit="kcal" target={dash?.calorie_target} color="orange" note={dash?.calorie_target ? `${Math.max(0, dash.calorie_target - (dash.calories ?? 0))} left today` : "Set a daily target"} />
            <Metric icon={<Activity size={17} />} title="Protein" value={dash?.protein_g ?? 0} unit="g" target={dash?.protein_target_g} color="lime" note={dash?.protein_target_g ? `${Math.max(0, dash.protein_target_g - (dash.protein_g ?? 0))} g to go` : "Personalize your target"} />
            <Metric icon={<Droplets size={17} />} title="Water" value={dash?.water_ml ?? 0} unit="ml" target={dash?.water_target_ml} color="blue" note={`${Math.max(0, (dash?.water_target_ml ?? 2500) - (dash?.water_ml ?? 0))} ml remaining`} />
            <Metric icon={<Moon size={17} />} title="Sleep" value={dash?.sleep_hours ?? "—"} unit={dash?.sleep_hours ? "hrs" : ""} target={8} color="violet" note={dash?.sleep_hours ? "Last night's rest" : "No sleep logged yet"} />
          </div>
          <div className="dashboard-grid">
            <Panel title="Your nutrition" action={<button className="text-action" onClick={() => setPage("Nutrition")}>View journal <ArrowUpRight size={14} /></button>}>
              <div className="nutrition-overview"><div className="calorie-ring" style={{ "--pct": `${Math.min(calorieProgress, 100)}%` } as React.CSSProperties}><div><b>{dash?.calories ?? 0}</b><span>of {dash?.calorie_target ?? "—"} kcal</span></div></div><div className="macro-list"><MacroLine label="Protein" value={dash?.protein_g ?? 0} target={dash?.protein_target_g} color="lime" /><MacroLine label="Carbs" value={dash?.carbs_g ?? 0} target={dash?.carbs_target_g} color="orange" /><MacroLine label="Fat" value={dash?.fat_g ?? 0} target={dash?.fat_target_g} color="blue" /></div></div>
            </Panel>
            <Panel title="Today's rhythm" action={<span className="tiny-label">{dash?.habits_done ?? 0}/{dash?.habits_total ?? 0} DONE</span>}>
              {habits.length ? <div className="check-list">{habits.slice(0, 4).map((h) => <button key={h.id} className="check-row" onClick={() => run(() => api(`/habits/${h.id}/complete?day=${selectedDay}`, { method: "PUT" }), h.completed ? "Habit unchecked" : "Habit completed")}><span className={`checkmark ${h.completed ? "checked" : ""}`}>{h.completed && <Check size={13} />}</span><span>{h.name}</span><small>{h.completed ? "Done" : "Tap to complete"}</small></button>)}</div> : <Empty icon={<ClipboardList size={18} />} title="A fresh start" detail="Add a daily habit to build your rhythm." action="Create habit" onClick={() => { setPage("Daily Habits"); setShowHabitForm(true); }} />}
            </Panel>
            <Panel title="Weight trend" action={<button className="text-action" onClick={() => setPage("Body Progress")}>View progress <ArrowUpRight size={14} /></button>} className="span-two">
              {measurements.some((m) => m.weight_kg) ? <div className="chart-wrap"><ResponsiveContainer width="100%" height={205}><AreaChart data={[...measurements].reverse().filter((m) => m.weight_kg).map((m) => ({ date: m.measured_on.slice(5), weight: m.weight_kg }))}><defs><linearGradient id="weightFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#b9db83" stopOpacity={0.24} /><stop offset="95%" stopColor="#b9db83" stopOpacity={0} /></linearGradient></defs><CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#292d28" /><XAxis dataKey="date" tickLine={false} axisLine={false} tick={{ fill: "#747b70", fontSize: 11 }} /><YAxis domain={["auto", "auto"]} tickLine={false} axisLine={false} tick={{ fill: "#747b70", fontSize: 11 }} width={35} /><Tooltip contentStyle={{ background: "#1a1d19", border: "1px solid #343a31", borderRadius: 12 }} /><Area dataKey="weight" type="monotone" stroke="#b9db83" strokeWidth={2.5} fill="url(#weightFill)" /></AreaChart></ResponsiveContainer></div> : <Empty icon={<TrendingUp size={18} />} title="Your journey starts here" detail="Record your first weigh-in to see your trend." action="Record weight" onClick={() => { setPage("Body Progress"); setShowWeightForm(true); }} />}
            </Panel>
            <Panel title="Quick actions"><div className="quick-grid"><Quick icon={<Utensils size={16} />} label="Log food" onClick={() => { setPage("Nutrition"); setShowFoodForm(true); }} /><Quick icon={<Droplets size={16} />} label="Add water" onClick={() => run(() => api("/water", { method: "POST", body: JSON.stringify({ amount_ml: 250 }) }), "250 ml water added")} /><Quick icon={<Dumbbell size={16} />} label="Start workout" onClick={() => setPage("Workouts")} /><Quick icon={<Weight size={16} />} label="Record weight" onClick={() => { setPage("Body Progress"); setShowWeightForm(true); }} /><Quick icon={<Moon size={16} />} label="Log sleep" onClick={() => { setPage("Sleep & Recovery"); setShowSleepForm(true); }} /><Quick icon={<Check size={16} />} label="Complete habit" onClick={() => setPage("Daily Habits")} /></div></Panel>
          </div>
          <Panel title="AURA daily assistant" action={<span className="tiny-label">PRIVATE · NO AI SERVICE</span>}>
            <p className="assistant-hint">Try “I ate two bananas and 250 ml milk”, “I drank 500 ml water”, “I slept for 7 hours”, or ask about today's remaining calories.</p>
            <form className="assistant-input" onSubmit={askAssistant}><input aria-label="Ask AURA assistant" value={assistantText} onChange={(event) => setAssistantText(event.target.value)} placeholder="Tell AURA what you did, or ask a question…" /><Button type="submit" disabled={assistantBusy || !assistantText.trim()}>{assistantBusy ? "Checking…" : "Ask"}</Button></form>
            {assistantResult && <div className="assistant-result"><p>{assistantResult.text}</p>{assistantResult.kind === "food" && parsedMeal && parsedMeal.items.length > 0 && <>
              <SelectField label="Meal" value={assistantMeal} onChange={(event) => setAssistantMeal(event.target.value)}>{["Breakfast", "Morning snack", "Lunch", "Evening snack", "Dinner", "Other"].map((meal) => <option key={meal}>{meal}</option>)}</SelectField>
              <div className="assistant-foods">{parsedMeal.items.map((item, index) => <div className="assistant-food" key={`${item.food_id}-${index}`}><span><b>{item.quantity} × {item.food_name}</b><small>{item.serving_unit} · {item.assumption}</small></span><span>{Math.round(item.calories * item.quantity)} kcal</span></div>)}</div>
              {parsedMeal.totals && <div className="assistant-totals">Estimated total: {parsedMeal.totals.calories} kcal · {parsedMeal.totals.protein_g} g protein · {parsedMeal.totals.carbs_g} g carbs · {parsedMeal.totals.fat_g} g fat</div>}
              <div className="assistant-actions"><Button onClick={confirmAssistantMeal} disabled={assistantBusy}>{assistantBusy ? "Saving…" : "Confirm and save meal"}</Button><Button variant="quiet" onClick={() => { setAssistantResult(null); setReminder(null); }}>Cancel</Button></div>
            </>}</div>}
          </Panel>
          <div className="disclaimer"><ShieldCheck size={14} /> Wellness estimates are informational only, not medical advice. Your data stays on this device.</div>
        </section>}

        {page === "Nutrition" && <section>
          <PageHeading eyebrow="NOURISH WITH INTENTION" title="Nutrition journal" description="A clear picture of what fuels you, one meal at a time." action={<Button onClick={() => setShowFoodForm(!showFoodForm)}><Plus size={16} /> Log food</Button>} />
          <div className="metrics-grid nutrition-stats"><Metric icon={<Flame size={17} />} title="Energy" value={dash?.calories ?? 0} unit="kcal" target={dash?.calorie_target} color="orange" note={dash?.calorie_target ? `Target ${dash.calorie_target}` : "No target set"} /><Metric icon={<Activity size={17} />} title="Protein" value={dash?.protein_g ?? 0} unit="g" target={dash?.protein_target_g} color="lime" note="Daily total" /><Metric icon={<TrendingUp size={17} />} title="Carbohydrates" value={dash?.carbs_g ?? 0} unit="g" target={dash?.carbs_target_g} color="blue" note="Daily total" /><Metric icon={<Heart size={17} />} title="Fat" value={dash?.fat_g ?? 0} unit="g" target={dash?.fat_target_g} color="violet" note="Daily total" /></div>
          {showFoodForm && <Panel title={editingFoodId ? "Edit food entry" : "Add to your food journal"} className="form-panel"><form onSubmit={saveFood} className="form-grid">
            <div className="search-wrap"><Search size={16} /><input placeholder="Search local foods..." value={search} onChange={(e) => setSearch(e.target.value)} /></div>
            <div className="food-search-results">{foods.filter((f) => f.name.toLowerCase().includes(search.toLowerCase())).slice(0, 5).map((food) => <button type="button" key={food.id} className="food-result" onClick={() => selectFood(food)}><span><b>{food.name}</b><small>{food.serving} · estimate</small></span><span>{food.calories} kcal</span></button>)}</div>
            <Field label="Food name" value={foodForm.food_name} onChange={(e) => setFoodForm({ ...foodForm, food_name: e.target.value })} required />
            <Field label="Quantity" type="number" min="0.01" step="0.01" value={foodForm.quantity} onChange={(e) => setFoodForm({ ...foodForm, quantity: e.target.value })} required />
            <Field label="Serving unit" value={foodForm.serving_unit} onChange={(e) => setFoodForm({ ...foodForm, serving_unit: e.target.value })} required />
            <SelectField label="Meal" value={foodForm.meal} onChange={(e) => setFoodForm({ ...foodForm, meal: e.target.value })}>{["Breakfast", "Morning snack", "Lunch", "Evening snack", "Dinner", "Other"].map((v) => <option key={v}>{v}</option>)}</SelectField>
            <Field label="Calories / serving" type="number" min="0" step=".1" value={foodForm.calories} onChange={(e) => setFoodForm({ ...foodForm, calories: e.target.value })} required />
            <Field label="Protein (g)" type="number" min="0" step=".1" value={foodForm.protein_g} onChange={(e) => setFoodForm({ ...foodForm, protein_g: e.target.value })} required />
            <Field label="Carbs (g)" type="number" min="0" step=".1" value={foodForm.carbs_g} onChange={(e) => setFoodForm({ ...foodForm, carbs_g: e.target.value })} required />
            <Field label="Fat (g)" type="number" min="0" step=".1" value={foodForm.fat_g} onChange={(e) => setFoodForm({ ...foodForm, fat_g: e.target.value })} required />
            <div className="form-actions"><Button type="submit" disabled={busy}>{editingFoodId ? "Update entry" : "Save food entry"}</Button><Button variant="quiet" onClick={() => { setShowFoodForm(false); setEditingFoodId(null); }}>Cancel</Button></div>
          </form></Panel>}
          <Panel title="Today's food" action={<span className="tiny-label">{entries.length} ENTRIES</span>}>
            {entries.length ? <div className="table-wrap"><table><thead><tr><th>FOOD</th><th>MEAL</th><th>AMOUNT</th><th>CALORIES</th><th>PROTEIN</th><th /></tr></thead><tbody>{entries.map((entry) => <tr key={entry.id}><td><b>{entry.food_name}</b></td><td>{entry.meal}</td><td>{entry.quantity} × {entry.serving_unit}</td><td>{Math.round(entry.calories * entry.quantity)} kcal</td><td>{(entry.protein_g * entry.quantity).toFixed(1)} g</td><td><div className="row-actions"><button className="icon-button" title="Edit entry" onClick={() => { setFoodForm({ food_name: entry.food_name, quantity: String(entry.quantity), serving_unit: entry.serving_unit, calories: String(entry.calories), protein_g: String(entry.protein_g), carbs_g: String(entry.carbs_g), fat_g: String(entry.fat_g), meal: entry.meal, notes: "" }); setEditingFoodId(entry.id); setShowFoodForm(true); }}><Pencil size={14} /></button><button className="icon-button delete-icon" title="Delete entry" onClick={() => run(() => api(`/nutrition/${entry.id}`, { method: "DELETE" }), "Entry removed")}><Trash2 size={15} /></button></div></td></tr>)}</tbody></table></div> : <Empty icon={<Utensils size={18} />} title="No meals logged yet" detail="Your food journal will fill with real data as you log." action="Log your first meal" onClick={() => setShowFoodForm(true)} />}
          </Panel>
        </section>}

        {page === "Workouts" && <section>
          <PageHeading eyebrow="TRAIN WITH PURPOSE" title="Workout studio" description="Build a plan, log your sets, and celebrate showing up." action={<Button onClick={() => setShowPlanForm(!showPlanForm)}><Plus size={16} /> New plan</Button>} />
          {activeWorkout && <Panel title={`In progress · ${activeWorkout.name}`} className="active-workout"><div className="active-title"><span className="live-dot" /> Session started {new Date(activeWorkout.started_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}<Button variant="secondary" onClick={finishWorkout}>Finish workout</Button></div><form className="inline-log" onSubmit={logSet}><Field label="Exercise" name="exercise" placeholder="e.g. Goblet squat" required /><Field label="Set #" name="set_number" type="number" min="1" defaultValue="1" required /><Field label="Weight (kg)" name="weight_kg" type="number" min="0" step=".5" defaultValue="0" required /><Field label="Reps" name="reps" type="number" min="0" defaultValue="8" required /><Button type="submit" disabled={busy}><Plus size={15} /> Log set</Button></form>{sessions.find((session) => session.id === activeWorkout.id)?.sets?.map((set, index) => <div className="logged-set" key={`${set.exercise}-${set.set_number}-${index}`}><Check size={13} /> {set.exercise} · Set {set.set_number} · {set.weight_kg} kg × {set.reps}</div>)}</Panel>}
          {showPlanForm && <Panel title="Create a workout plan"><form className="form-grid" onSubmit={savePlan}><Field label="Plan name" name="name" placeholder="e.g. Upper body strength" required /><label className="field full"><span>Exercises (comma-separated)</span><input name="exercises" placeholder="Bench press, Row, Shoulder press" /></label><div className="form-actions"><Button type="submit">Save plan</Button><Button variant="quiet" onClick={() => setShowPlanForm(false)}>Cancel</Button></div></form></Panel>}
          <div className="section-label">YOUR PLANS</div><div className="plan-grid">{plans.map((plan) => <article key={plan.id} className="plan-card"><div className="plan-icon"><Dumbbell size={19} /></div><h3>{plan.name}</h3><p>{plan.exercises.length ? plan.exercises.join(" · ") : "Add exercises as you train"}</p><Button onClick={() => startWorkout(plan)}><Dumbbell size={15} /> Start workout</Button></article>)}<button className="new-plan-card" onClick={() => setShowPlanForm(true)}><span><Plus size={20} /></span><b>Create a workout plan</b><small>Make it yours, one exercise at a time.</small></button></div>
          <Panel title="Recent sessions" className="session-panel">{sessions.length ? <div className="session-list">{sessions.map((s) => <details className="session-detail" key={s.id}><summary className="session-row"><span className={`session-icon ${s.completed_at ? "completed" : ""}`}><Dumbbell size={16} /></span><span className="session-description"><b>{s.name}</b><small>{new Date(s.started_at).toLocaleString()}</small></span><span className={`status-pill ${s.completed_at ? "done" : "active"}`}>{s.completed_at ? "Completed" : "In progress"}</span><ChevronRight size={14} className="session-chevron" /></summary>{s.sets?.length ? <div className="session-sets">{s.sets.map((set, index) => <span key={`${set.exercise}-${set.set_number}-${index}`}>{set.exercise} · {set.weight_kg} kg × {set.reps} reps</span>)}</div> : <div className="session-sets muted">No sets recorded.</div>}</details>)}</div> : <Empty icon={<Dumbbell size={18} />} title="Ready when you are" detail="Start a workout to begin your training history." action="Start a quick workout" onClick={() => startWorkout()} />}</Panel>
        </section>}

        {page === "Body Progress" && <section>
          <PageHeading eyebrow="NOTICE THE CHANGE" title="Body progress" description="Track your measurements over time. Trends matter more than a single day." action={<Button onClick={() => setShowWeightForm(!showWeightForm)}><Plus size={16} /> Record progress</Button>} />
          <div className="metrics-grid">{[["Current weight", dash?.weight_kg ? `${dash.weight_kg} kg` : "—", "Latest recorded"], ["Target weight", dash?.target_weight_kg ? `${dash.target_weight_kg} kg` : "—", "Your personal goal"], ["Entries", String(measurements.length), "Progress check-ins"], ["Consistency", measurements.length ? "In motion" : "Begin today", "One day at a time"]].map(([title, value, note]) => <div key={title} className="metric-card"><div className="metric-heading"><span className="metric-icon violet"><Weight size={17} /></span><span>{title}</span></div><div className="metric-main">{value}</div><small className="metric-note">{note}</small></div>)}</div>
          {showWeightForm && <Panel title="Record a progress check-in"><form className="form-grid" onSubmit={saveMeasurement}><Field label="Weight (kg)" name="weight_kg" type="number" step=".1" min="20" max="500" placeholder="e.g. 68.4" /><Field label="Waist (cm)" name="waist_cm" type="number" step=".1" min="20" max="300" placeholder="Optional" /><Field label="Chest (cm)" name="chest_cm" type="number" step=".1" min="20" max="300" placeholder="Optional" /><div className="form-actions"><Button type="submit">Save check-in</Button><Button variant="quiet" onClick={() => setShowWeightForm(false)}>Cancel</Button></div></form></Panel>}
          <Panel title="Weight over time">{measurements.some((m) => m.weight_kg) ? <div className="chart-wrap tall"><ResponsiveContainer width="100%" height={290}><AreaChart data={[...measurements].reverse().filter((m) => m.weight_kg).map((m) => ({ date: m.measured_on, weight: m.weight_kg }))}><defs><linearGradient id="bodyFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#b9db83" stopOpacity={0.22} /><stop offset="100%" stopColor="#b9db83" stopOpacity={0} /></linearGradient></defs><CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#292d28" /><XAxis dataKey="date" tickLine={false} axisLine={false} tick={{ fill: "#747b70", fontSize: 11 }} /><YAxis domain={["auto", "auto"]} tickLine={false} axisLine={false} tick={{ fill: "#747b70", fontSize: 11 }} /><Tooltip contentStyle={{ background: "#1a1d19", border: "1px solid #343a31", borderRadius: 12 }} /><Area dataKey="weight" type="monotone" stroke="#b9db83" strokeWidth={2.5} fill="url(#bodyFill)" /></AreaChart></ResponsiveContainer></div> : <Empty icon={<TrendingUp size={18} />} title="No measurements yet" detail="Log a weight or measurement to start your progress story." action="Add measurement" onClick={() => setShowWeightForm(true)} />}</Panel>
          <Panel title="Measurement history">{measurements.length ? <div className="table-wrap"><table><thead><tr><th>DATE</th><th>WEIGHT</th><th>WAIST</th><th>CHEST</th></tr></thead><tbody>{measurements.map((m) => <tr key={m.id}><td>{m.measured_on}</td><td>{m.weight_kg ? `${m.weight_kg} kg` : "—"}</td><td>{m.waist_cm ? `${m.waist_cm} cm` : "—"}</td><td>{m.chest_cm ? `${m.chest_cm} cm` : "—"}</td></tr>)}</tbody></table></div> : <p className="muted">Measurements you log will appear here.</p>}</Panel>
        </section>}

        {page === "Daily Habits" && <section><PageHeading eyebrow="SMALL PROMISES, KEPT" title="Daily habits" description="Build the routines that make your best days feel natural." action={<Button onClick={() => setShowHabitForm(!showHabitForm)}><Plus size={16} /> Add habit</Button>} />
          <div className="habit-summary"><div><span>DAILY MOMENTUM</span><b>{habits.length ? Math.round(habits.filter((h) => h.completed).length / habits.length * 100) : 0}%</b><small>{habits.filter((h) => h.completed).length} of {habits.length} habits complete</small></div><div className="momentum-bar"><Progress value={habits.filter((h) => h.completed).length} target={habits.length || 1} /></div><div className="streak-mark"><Sparkles size={19} /><span>Consistency beats intensity.</span></div></div>
          {showHabitForm && <Panel title="Create a daily habit"><form className="form-grid" onSubmit={saveHabit}><Field label="Habit name" name="name" placeholder="e.g. Evening stretch" required /><Field label="Category" name="category" placeholder="Wellness" /><div className="form-actions"><Button type="submit">Add habit</Button><Button variant="quiet" onClick={() => setShowHabitForm(false)}>Cancel</Button></div></form></Panel>}
          <Panel title={selectedDay === today() ? "Today's checklist" : `Checklist · ${dateLabel}`} action={<span className="tiny-label">{habits.filter((h) => h.completed).length} COMPLETED</span>}>{habits.length ? <div className="habit-list">{habits.map((habit) => <div className="habit-item" key={habit.id}><button className={`habit-check ${habit.completed ? "completed" : ""}`} onClick={() => run(() => api(`/habits/${habit.id}/complete?day=${selectedDay}`, { method: "PUT" }), habit.completed ? "Habit unchecked" : "Habit completed")} aria-label={habit.completed ? "Mark incomplete" : "Mark complete"}>{habit.completed && <Check size={16} />}</button><div><b className={habit.completed ? "strike" : ""}>{habit.name}</b><small>{habit.category}</small></div><span className={`status-pill ${habit.completed ? "done" : "pending"}`}>{habit.completed ? "Done for today" : "Your next small win"}</span></div>)}</div> : <Empty icon={<ClipboardList size={18} />} title="Create your first habit" detail="Water, walking, reading—start with one that matters to you." action="Add a habit" onClick={() => setShowHabitForm(true)} />}</Panel>
        </section>}

        {page === "Looksmaxing" && <section><PageHeading eyebrow="CARE THAT FEELS LIKE YOU" title="Looksmaxing studio" description="Supportive self-care rituals for skin, hair, and everyday grooming." action={<Button onClick={() => setShowRoutineForm(!showRoutineForm)}><Plus size={16} /> New routine</Button>} />
          <div className="routine-intro"><div className="routine-art"><Sparkles size={26} /></div><div><b>Healthy habits, your way.</b><p>Build a personal routine with products and steps that work for you. This is a space for care, not comparison.</p></div><Heart size={20} className="routine-heart" /></div>
          {showRoutineForm && <Panel title="Create your routine"><form className="form-grid" onSubmit={saveRoutine}><Field label="Routine name" name="name" placeholder="e.g. Gentle morning skincare" required /><SelectField label="When" name="routine_time"><option>Morning</option><option>Evening</option><option>Anytime</option></SelectField><label className="field full"><span>Steps (one per line)</span><textarea name="steps" rows={3} placeholder={"Cleanser\nMoisturizer\nSunscreen"} /></label><div className="form-actions"><Button type="submit">Save routine</Button><Button variant="quiet" onClick={() => setShowRoutineForm(false)}>Cancel</Button></div></form></Panel>}
          <div className="routine-grid">{routines.map((routine) => <article className="routine-card" key={routine.id}><div className="routine-card-top"><span className="routine-time">{routine.routine_time === "Morning" ? "☀" : "☾"} {routine.routine_time}</span><span className={`routine-status ${routine.completed ? "done" : ""}`}>{routine.completed ? "Completed" : "Not yet"}</span></div><h3>{routine.name}</h3><ul>{routine.steps.map((step, idx) => <li key={`${step}-${idx}`}><span>{idx + 1}</span>{step}</li>)}</ul><Button variant={routine.completed ? "secondary" : "primary"} onClick={() => run(() => api(`/skincare/${routine.id}/complete?day=${selectedDay}`, { method: "PUT" }), routine.completed ? "Routine unchecked" : "Routine completed")}>{routine.completed ? <><Check size={15} /> Done today</> : "Complete routine"}</Button></article>)}<button className="new-plan-card" onClick={() => setShowRoutineForm(true)}><span><Plus size={20} /></span><b>Add a routine</b><small>Morning, evening, or whenever feels right.</small></button></div>
        </section>}

        {page === "Sleep & Recovery" && <section><PageHeading eyebrow="REST IS PART OF THE PLAN" title="Sleep & recovery" description="Notice your sleep patterns and how you feel, without judgment." action={<Button onClick={() => setShowSleepForm(!showSleepForm)}><Plus size={16} /> Log sleep</Button>} />
          <div className="sleep-hero"><div className="sleep-moon"><Moon size={25} /></div><div><span>LAST NIGHT</span><strong>{dash?.sleep_hours ? `${dash.sleep_hours} hours` : "No sleep logged"}</strong><p>Sleep duration is a personal tracking aid, not a medical score.</p></div></div>
          {showSleepForm && <Panel title="Log your sleep"><form className="form-grid" onSubmit={saveSleep}><Field label="Bedtime date" name="bedtime_date" type="date" defaultValue={new Date(Date.now() - 86400000).toLocaleDateString("en-CA")} required /><Field label="Bedtime" name="bedtime" type="time" defaultValue="22:30" required /><Field label="Wake-up date" name="wake_date" type="date" defaultValue={today()} required /><Field label="Wake-up time" name="wake_time" type="time" defaultValue="06:30" required /><SelectField label="Sleep quality (optional)" name="quality"><option value="">Skip</option><option value="1">1 — Restless</option><option value="2">2</option><option value="3">3 — Okay</option><option value="4">4</option><option value="5">5 — Restful</option></SelectField><div className="form-actions"><Button type="submit">Save sleep</Button><Button variant="quiet" onClick={() => setShowSleepForm(false)}>Cancel</Button></div></form></Panel>}
          <Panel title="Water check-in"><p className="muted">You have logged <b>{dash?.water_ml ?? 0} ml</b> of your {dash?.water_target_ml ?? 2500} ml daily water goal.</p><div className="water-actions">{[150, 250, 500].map((ml) => <Button key={ml} variant="secondary" onClick={() => run(() => api("/water", { method: "POST", body: JSON.stringify({ amount_ml: ml }) }), `${ml} ml water added`)}><Droplets size={15} /> +{ml} ml</Button>)}</div></Panel>
        </section>}

        {page === "Automation" && <AutomationCenter onError={setError} onNotice={setNotice} />}

        {page === "Analytics" && <section><PageHeading eyebrow="YOUR DATA, YOUR STORY" title="Progress insights" description="Export your logged measurements and nutrition for a closer look." action={<button className="button primary link-button" onClick={async () => { try { const response = await fetch(`${API}/analytics/export`, { credentials: "include" }); if (!response.ok) throw new Error("Could not export your data."); const blob = await response.blob(); const url = URL.createObjectURL(blob); const a = document.createElement("a"); a.href = url; a.download = "aura-progress.csv"; a.click(); URL.revokeObjectURL(url); } catch (e) { setError(e instanceof Error ? e.message : "Could not export your data."); } }}><ArrowDownRight size={16} /> Export CSV</button>} />
          <div className="analytics-grid"><Panel title="Weight history">{measurements.some((m) => m.weight_kg) ? <div className="chart-wrap"><ResponsiveContainer width="100%" height={235}><AreaChart data={[...measurements].reverse().filter((m) => m.weight_kg).map((m) => ({ date: m.measured_on.slice(5), weight: m.weight_kg }))}><CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#292d28" /><XAxis dataKey="date" tickLine={false} axisLine={false} tick={{ fill: "#747b70", fontSize: 11 }} /><YAxis domain={["auto", "auto"]} tickLine={false} axisLine={false} tick={{ fill: "#747b70", fontSize: 11 }} /><Tooltip contentStyle={{ background: "#1a1d19", border: "1px solid #343a31", borderRadius: 12 }} /><Area dataKey="weight" type="monotone" stroke="#b9db83" fill="#b9db8325" /></AreaChart></ResponsiveContainer></div> : <Empty icon={<TrendingUp size={18} />} title="Waiting for your first data point" detail="Your charts update when you log progress." />}</Panel><Panel title="Daily nutrition"><div className="insight-number">{dash?.calories ?? 0}<small> kcal today</small></div><p className="muted">Protein {dash?.protein_g ?? 0} g · Carbs {dash?.carbs_g ?? 0} g · Fat {dash?.fat_g ?? 0} g</p><Button variant="secondary" onClick={() => setPage("Nutrition")}>Open nutrition journal <ArrowUpRight size={15} /></Button></Panel></div>
          <WeeklyReport />
          <div className="privacy-note"><CircleHelp size={17} /><div><b>About your insights</b><p>Charts only show recorded data. Missing days are left blank rather than filled with estimates.</p></div></div>
        </section>}

        {(page === "Profile" || page === "Settings") && <section><PageHeading eyebrow={page === "Profile" ? "YOUR PROFILE" : "MAKE IT YOURS"} title={page === "Profile" ? "A little about you" : "Personal settings"} description={page === "Profile" ? "Your goals and preferences, all in one place." : "Adjust your personal targets whenever you need."} />
          <ProfileSettings user={user} onSave={(data) => run(async () => { await api("/profile/onboarding", { method: "PUT", body: JSON.stringify(data) }); const updated = await api<User>("/auth/me"); setUser(updated); }, "Preferences updated")} onDelete={deleteAccount} />
          {page === "Settings" && <><GoalCalculator onSaved={async () => { const updated = await api<User>("/auth/me"); setUser(updated); await reloadData(updated, selectedDay); setNotice("Nutrition targets updated"); }} /><ReminderSettings onError={setError} onSaved={() => setNotice("Reminder settings saved")} /></>}
          {page === "Profile" && <Panel title="Your personal focus"><div className="profile-goal"><span className="goal-spark"><Sparkles size={19} /></span><div><small>PRIMARY GOAL</small><b>{user.profile.goal}</b></div><button className="text-action" onClick={() => setPage("Settings")}>Edit <ArrowUpRight size={14} /></button></div><div className="profile-facts"><span>Height <b>{user.profile.height_cm ? `${user.profile.height_cm} cm` : "Not set"}</b></span><span>Starting weight <b>{user.profile.current_weight_kg ? `${user.profile.current_weight_kg} kg` : "Not set"}</b></span><span>Measurement units <b>{user.profile.units === "imperial" ? "Imperial" : "Metric"}</b></span></div></Panel>}
          <Panel title="Privacy and data"><p className="muted">Your records are stored in the local AURA database on this computer. Keep a private backup of the database file if you want to preserve your history.</p><Button variant="danger" onClick={deleteAccount}><Trash2 size={15} /> Delete account and data</Button></Panel>
        </section>}
      </div>
    </main>
    {reminder && <div className="modal-backdrop" role="presentation"><section className="reminder-modal" role="dialog" aria-modal="true" aria-labelledby="reminder-title"><button className="icon-button modal-close" aria-label="Dismiss reminder" onClick={() => respondToReminder("dismiss")}><X size={17} /></button><span className="reminder-icon"><Utensils size={21} /></span><div className="eyebrow">A GENTLE CHECK-IN</div><h2 id="reminder-title">{reminder.meal === "Breakfast" ? "Good morning! Have you had breakfast?" : `Time for a ${reminder.meal.toLowerCase()} check-in?`}</h2><p>Your reminder is saved for today. Logging a meal is always your choice.</p><div className="reminder-actions"><Button onClick={() => respondToReminder("open_log")}>Yes, I've eaten</Button><Button variant="secondary" onClick={() => respondToReminder("not_yet")}>Not yet · snooze {reminder.snooze_minutes} min</Button><button className="text-action" onClick={() => respondToReminder("skip")}>Skip this reminder</button></div></section></div>}
    <footer className="mobile-nav">{navItems.slice(0, 5).map(({ name, icon: Icon }) => <button key={name} className={page === name ? "selected" : ""} onClick={() => setPage(name)}><Icon size={18} /><span>{name === "Body Progress" ? "Body" : name}</span></button>)}</footer>
  </div>;
}

function Metric({ icon, title, value, unit, target, color, note }: { icon: React.ReactNode; title: string; value: number | string; unit: string; target?: number; color: string; note: string }) {
  return <article className="metric-card"><div className="metric-heading"><span className={`metric-icon ${color}`}>{icon}</span><span>{title}</span></div><div className="metric-main">{typeof value === "number" ? (Number.isInteger(value) ? value : value.toFixed(1)) : value}<small>{unit}</small></div><Progress value={Number(value) || 0} target={target} color={color} /><small className="metric-note">{note}</small></article>;
}
function MacroLine({ label, value, target, color }: { label: string; value: number; target?: number; color: string }) {
  return <div className="macro-line"><div><span>{label}</span><b>{value} <small>/ {target ?? "—"} g</small></b></div><Progress value={value} target={target} color={color} /></div>;
}
function Quick({ icon, label, onClick }: { icon: React.ReactNode; label: string; onClick: () => void }) {
  return <button className="quick-button" onClick={onClick}><span>{icon}</span><b>{label}</b><ArrowUpRight size={13} className="quick-arrow" /></button>;
}
function Empty({ icon, title, detail, action, onClick }: { icon: React.ReactNode; title: string; detail: string; action?: string; onClick?: () => void }) {
  return <div className="empty-state"><span className="empty-icon">{icon}</span><b>{title}</b><p>{detail}</p>{action && onClick && <Button variant="secondary" onClick={onClick}>{action}</Button>}</div>;
}
function PageHeading({ eyebrow, title, description, action }: { eyebrow: string; title: string; description: string; action?: React.ReactNode }) {
  return <div className="page-heading"><div><div className="eyebrow">{eyebrow}</div><h1>{title}</h1><p>{description}</p></div>{action}</div>;
}

function Auth({ onUser }: { onUser: (user: User) => void }) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = new FormData(event.currentTarget);
    setBusy(true); setError("");
    try {
      const body = mode === "login" ? { username: form.get("username"), password: form.get("password") } : { full_name: form.get("full_name"), username: form.get("username"), email: form.get("email"), password: form.get("password") };
      const user = await api<User>(`/auth/${mode}`, { method: "POST", body: JSON.stringify(body) });
      onUser(user);
    } catch (e) { setError(e instanceof Error ? e.message : "Unable to sign in."); }
    finally { setBusy(false); }
  }
  return <div className="auth-screen"><div className="auth-art"><div className="auth-logo"><span className="brand-mark"><Sparkles size={19} /></span>AURA</div><div className="auth-message"><div className="eyebrow">YOUR WELLNESS, IN SYNC</div><h1>Become your<br /><em>best self.</em></h1><p>One calm, considered space for the habits that help you feel good.</p><div className="auth-stats"><span><Activity size={16} /> Move with purpose</span><span><Heart size={16} /> Care for yourself</span></div></div><div className="auth-orbit orbit-one" /><div className="auth-orbit orbit-two" /><div className="auth-bottom">BUILD YOUR BODY. UPGRADE YOUR MIND.</div></div><div className="auth-form-side"><div className="auth-form-box"><span className="eyebrow">{mode === "login" ? "WELCOME BACK" : "START YOUR JOURNEY"}</span><h2>{mode === "login" ? "Sign in to AURA" : "Create your account"}</h2><p>{mode === "login" ? "Pick up where your best self left off." : "Your wellness space, built around you."}</p>{error && <div className="inline-error">{error}</div>}<form onSubmit={submit} className="auth-fields">{mode === "register" && <Field label="Full name" name="full_name" placeholder="Your name" autoComplete="name" required />}<Field label="Username or email" name="username" placeholder="you@example.com" autoComplete="username" required />{mode === "register" && <Field label="Email address" name="email" type="email" placeholder="you@example.com" autoComplete="email" required />}<Field label="Password" name="password" type="password" placeholder={mode === "register" ? "At least 10 characters" : "Your password"} autoComplete={mode === "login" ? "current-password" : "new-password"} minLength={mode === "register" ? 10 : 1} required /><Button type="submit" disabled={busy}>{busy ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"} <ArrowUpRight size={16} /></Button></form><div className="auth-toggle">{mode === "login" ? "New to AURA?" : "Already have an account?"} <button onClick={() => { setMode(mode === "login" ? "register" : "login"); setError(""); }}>{mode === "login" ? "Create an account" : "Sign in"}</button></div><div className="auth-privacy"><ShieldCheck size={14} /> Your account and wellness data stay on this device.</div></div></div></div>;
}

function Onboarding({ user, onDone }: { user: User; onDone: (user: User) => void }) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = new FormData(event.currentTarget);
    const number = (key: string) => form.get(key) ? Number(form.get(key)) : null;
    const payload = { birth_date: form.get("birth_date") || null, gender: form.get("gender") || null, height_cm: number("height_cm"), current_weight_kg: number("current_weight_kg"), target_weight_kg: number("target_weight_kg"), goal: form.get("goal"), activity_level: form.get("activity_level"), units: form.get("units"), calorie_target: number("calorie_target"), protein_target_g: number("protein_target_g"), carbs_target_g: number("carbs_target_g"), fat_target_g: number("fat_target_g"), water_target_ml: number("water_target_ml") || 2500, avoid_weight_recommendations: form.get("avoid_weight_recommendations") === "on", training_days_per_week: number("training_days_per_week"), body_fat_percent: number("body_fat_percent") };
    setBusy(true); setError("");
    try { await api("/profile/onboarding", { method: "PUT", body: JSON.stringify(payload) }); const activeUser = await api<User>("/auth/me"); onDone(activeUser); }
    catch (e) { setError(e instanceof Error ? e.message : "Could not save your profile."); }
    finally { setBusy(false); }
  }
  return <div className="onboarding-screen"><div className="onboarding-card"><span className="eyebrow">LET'S MAKE THIS YOURS</span><h1>A few details, {user.full_name.split(" ")[0]}.</h1><p>These help us shape your wellness space. You can skip optional details or update everything later.</p>{error && <div className="inline-error">{error}</div>}<form className="onboard-grid" onSubmit={submit}><SelectField label="Your primary goal" name="goal" defaultValue="Improve general fitness">{["Gain weight", "Build muscle", "Lose weight", "Lose fat while maintaining muscle", "Weight maintenance", "Recomposition", "Improve general fitness", "Improve grooming and appearance"].map((g) => <option key={g}>{g}</option>)}</SelectField><SelectField label="Activity level" name="activity_level" defaultValue="moderate"><option value="sedentary">Sedentary</option><option value="light">Lightly active</option><option value="moderate">Moderately active</option><option value="active">Very active</option><option value="very_active">Extremely active</option></SelectField><SelectField label="Gender (optional, for estimates)" name="gender" defaultValue=""><option value="">Prefer not to say</option><option value="female">Female</option><option value="male">Male</option><option value="other">Another identity</option></SelectField><Field label="Height (cm)" name="height_cm" type="number" min="51" max="274" step=".1" placeholder="e.g. 170" /><Field label="Current weight (kg)" name="current_weight_kg" type="number" min="20" max="499" step=".1" placeholder="e.g. 68" /><Field label="Target weight (kg)" name="target_weight_kg" type="number" min="20" max="499" step=".1" placeholder="Optional" /><Field label="Date of birth (optional)" name="birth_date" type="date" /><Field label="Training days per week (optional)" name="training_days_per_week" type="number" min="0" max="7" placeholder="0–7" /><Field label="Body fat (optional)" name="body_fat_percent" type="number" min="2" max="75" step=".1" placeholder="Only if known" /><Field label="Daily calories (optional)" name="calorie_target" type="number" min="800" max="10000" placeholder="Set your own target" /><Field label="Protein target, grams" name="protein_target_g" type="number" min="0" max="1000" placeholder="Optional" /><Field label="Carbs target, grams" name="carbs_target_g" type="number" min="0" max="1500" placeholder="Optional" /><Field label="Fat target, grams" name="fat_target_g" type="number" min="0" max="500" placeholder="Optional" /><Field label="Water target (ml)" name="water_target_ml" type="number" min="250" max="10000" defaultValue="2500" /><label className="safety-choice"><input name="avoid_weight_recommendations" type="checkbox" /> Skip generic weight-related estimates (for example, if pregnant or managing a relevant medical concern).</label><div className="onboard-actions"><Button type="submit" disabled={busy}>{busy ? "Saving…" : "Build my dashboard"} <ArrowUpRight size={16} /></Button><span>Any generated calorie and macro targets are rough estimates, not medical advice.</span></div></form></div></div>;
}

function ProfileSettings({ user, onSave, onDelete }: { user: User; onSave: (data: Record<string, unknown>) => void; onDelete: () => void }) {
  function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = new FormData(event.currentTarget);
    const getNum = (key: string) => form.get(key) ? Number(form.get(key)) : null;
    onSave({ birth_date: form.get("birth_date") || null, gender: form.get("gender") || null, height_cm: getNum("height_cm"), current_weight_kg: getNum("current_weight_kg"), target_weight_kg: getNum("target_weight_kg"), goal: form.get("goal"), activity_level: form.get("activity_level"), units: form.get("units"), calorie_target: getNum("calorie_target"), protein_target_g: getNum("protein_target_g"), carbs_target_g: getNum("carbs_target_g"), fat_target_g: getNum("fat_target_g"), water_target_ml: Number(form.get("water_target_ml")) || 2500, avoid_weight_recommendations: form.get("avoid_weight_recommendations") === "on", surplus_kcal: Number(form.get("surplus_kcal")) || 200, deficit_kcal: Number(form.get("deficit_kcal")) || 300, training_days_per_week: getNum("training_days_per_week"), body_fat_percent: getNum("body_fat_percent") });
  }
  return <Panel title="Profile and daily targets"><div className="settings-user"><span className="settings-avatar">{user.full_name.slice(0, 1)}</span><div><b>{user.full_name}</b><small>{user.email} · @{user.username}</small></div></div><form className="form-grid" onSubmit={save}><SelectField label="Primary goal" name="goal" defaultValue={user.profile.goal}>{["Gain weight", "Build muscle", "Lose weight", "Lose fat while maintaining muscle", "Weight maintenance", "Recomposition", "Improve general fitness", "Improve grooming and appearance"].map((g) => <option key={g}>{g}</option>)}</SelectField><SelectField label="Activity level" name="activity_level" defaultValue={user.profile.activity_level}><option value="sedentary">Sedentary</option><option value="light">Lightly active</option><option value="moderate">Moderately active</option><option value="active">Very active</option><option value="very_active">Extremely active</option></SelectField><SelectField label="Gender (optional)" name="gender" defaultValue={user.profile.gender ?? ""}><option value="">Prefer not to say</option><option value="female">Female</option><option value="male">Male</option><option value="other">Another identity</option></SelectField><Field label="Date of birth" name="birth_date" type="date" defaultValue={user.profile.birth_date ?? ""} /><Field label="Height (cm)" name="height_cm" type="number" step=".1" defaultValue={user.profile.height_cm ?? ""} /><Field label="Current weight (kg)" name="current_weight_kg" type="number" step=".1" defaultValue={user.profile.current_weight_kg ?? ""} /><Field label="Target weight (kg)" name="target_weight_kg" type="number" step=".1" defaultValue={user.profile.target_weight_kg ?? ""} /><Field label="Training days per week" name="training_days_per_week" type="number" min="0" max="7" defaultValue={user.profile.training_days_per_week ?? ""} /><Field label="Body fat (optional, if known)" name="body_fat_percent" type="number" min="2" max="75" step=".1" defaultValue={user.profile.body_fat_percent ?? ""} /><Field label="Daily calorie target" name="calorie_target" type="number" min="800" max="10000" defaultValue={user.profile.calorie_target ?? ""} /><Field label="Protein target (g)" name="protein_target_g" type="number" min="0" defaultValue={user.profile.protein_target_g ?? ""} /><Field label="Carbohydrate target (g)" name="carbs_target_g" type="number" min="0" defaultValue={user.profile.carbs_target_g ?? ""} /><Field label="Fat target (g)" name="fat_target_g" type="number" min="0" defaultValue={user.profile.fat_target_g ?? ""} /><Field label="Water target (ml)" name="water_target_ml" type="number" min="250" defaultValue={user.profile.water_target_ml ?? 2500} /><Field label="Muscle-gain surplus (kcal)" name="surplus_kcal" type="number" min="0" max="500" defaultValue={user.profile.surplus_kcal ?? 200} /><Field label="Fat-loss deficit (kcal)" name="deficit_kcal" type="number" min="0" max="750" defaultValue={user.profile.deficit_kcal ?? 300} /><label className="safety-choice"><input name="avoid_weight_recommendations" type="checkbox" defaultChecked={user.profile.avoid_weight_recommendations} /> Skip generic weight-related estimates (for example, if pregnant or managing a relevant medical concern).</label><div className="form-actions"><Button type="submit"><Check size={15} /> Save preferences</Button></div></form>{onDelete && <div className="danger-zone"><b>Danger zone</b><p>Delete your account, logs, and all associated local data permanently.</p><Button variant="danger" onClick={onDelete}><Trash2 size={15} /> Delete account</Button></div>}</Panel>;
}

type TargetEstimate = { bmr: number; maintenance_calories: number; calorie_target: number; protein_target_g: number; carbs_target_g: number; fat_target_g: number; activity_factor: number; method: string; inputs: Record<string, unknown> };
type GoalPreview = { estimate: TargetEstimate | null; targets_customized: boolean; current_targets: Record<string, number | null>; message: string };
type WeeklyReportData = {
  week_start: string; week_end: string;
  nutrition: { logged_days: number; average_calories: number | null; average_protein_g: number | null; message: string };
  workouts_completed: number;
  weight: { measurement_count: number; average_kg: number | null; trend_delta_kg: number | null; message: string };
  sleep: { logged_nights: number; average_hours: number | null };
  water: { total_ml: number | null; message: string };
  habits: { completed: number; possible: number; completion_percent: number | null };
};
function WeeklyReport() {
  const [start, setStart] = useState(() => {
    const d = new Date(); d.setDate(d.getDate() - ((d.getDay() + 6) % 7) - 7); return localDate(d);
  });
  const [report, setReport] = useState<WeeklyReportData | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    api<WeeklyReportData>(`/reports/weekly?week_start=${start}`).then(setReport).catch((err) => setError(err instanceof Error ? err.message : "Could not load weekly report."));
  }, [start]);
  const shiftWeek = (days: number) => setStart((current) => localDate(new Date(new Date(`${current}T12:00:00`).getTime() + days * 86400000)));
  const thisWeekStart = new Date(`${thisMonday()}T12:00:00`);
  return <Panel title="Weekly review" action={<div className="date-switch"><button className="icon-button" aria-label="Previous week" onClick={() => shiftWeek(-7)}><ChevronLeft size={15} /></button><span>{report ? `${report.week_start} — ${report.week_end}` : start}</span><button className="icon-button" aria-label="Next week" disabled={new Date(`${start}T12:00:00`) >= thisWeekStart} onClick={() => shiftWeek(7)}><ChevronRight size={15} /></button></div>}>
    {error && <p className="inline-error">{error}</p>}
    {report ? <><div className="weekly-grid">
      <div><small>AVERAGE INTAKE</small><b>{report.nutrition.average_calories === null ? "—" : `${report.nutrition.average_calories} kcal`}</b><span>{report.nutrition.average_protein_g === null ? "No protein log" : `${report.nutrition.average_protein_g} g protein`} · {report.nutrition.logged_days} logged days</span></div>
      <div><small>COMPLETED WORKOUTS</small><b>{report.workouts_completed}</b><span>Sessions completed this week</span></div>
      <div><small>WEIGHT TREND</small><b>{report.weight.trend_delta_kg === null ? "—" : `${report.weight.trend_delta_kg > 0 ? "+" : ""}${report.weight.trend_delta_kg} kg`}</b><span>{report.weight.message}</span></div>
      <div><small>AVERAGE SLEEP</small><b>{report.sleep.average_hours === null ? "—" : `${report.sleep.average_hours} hrs`}</b><span>{report.sleep.logged_nights} logged nights</span></div>
      <div><small>HABITS</small><b>{report.habits.completion_percent === null ? "—" : `${report.habits.completion_percent}%`}</b><span>{report.habits.completed} of {report.habits.possible} possible completions</span></div>
      <div><small>WATER</small><b>{report.water.total_ml === null ? "—" : `${Math.round(report.water.total_ml / 1000)} L`}</b><span>{report.water.message}</span></div>
    </div><p className="muted">{report.nutrition.message} No logs are counted as zero consumption.</p></> : !error && <p className="muted">Loading your saved weekly activity…</p>}
  </Panel>;
}

function GoalCalculator({ onSaved }: { onSaved: () => Promise<void> }) {
  const [preview, setPreview] = useState<GoalPreview | null>(null);
  const [surplus, setSurplus] = useState(200);
  const [deficit, setDeficit] = useState(300);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  async function loadPreview() {
    setLoading(true); setError("");
    try { setPreview(await api<GoalPreview>("/goals/recalculate", { method: "POST", body: JSON.stringify({ accept: false, surplus_kcal: surplus, deficit_kcal: deficit }) })); }
    catch (err) { setError(err instanceof Error ? err.message : "Could not calculate an estimate."); }
    finally { setLoading(false); }
  }
  async function acceptEstimate() {
    setLoading(true); setError(""); setMessage("");
    try {
      const result = await api<{ accepted: boolean }>("/goals/recalculate", { method: "POST", body: JSON.stringify({ accept: true, surplus_kcal: surplus, deficit_kcal: deficit }) });
      setMessage(result.accepted ? "Targets updated from the reviewed estimate." : "No targets were changed.");
      await loadPreview();
      await onSaved();
    } catch (err) { setError(err instanceof Error ? err.message : "Could not update targets."); }
    finally { setLoading(false); }
  }
  useEffect(() => { void loadPreview(); }, []);
  return <Panel title="Calorie & macro estimate" action={<span className="tiny-label">MIFflin–ST JEOR · ESTIMATE</span>}>
    <p className="muted">An estimate based on profile age, height, weight, activity, and optional sex. It is not measured metabolism or medical advice. Editing profile details never silently replaces a target.</p>
    <div className="estimate-controls"><Field label="Muscle/weight gain surplus (kcal)" type="number" min="0" max="500" value={surplus} onChange={(event) => setSurplus(Number(event.target.value))} /><Field label="Fat-loss deficit (kcal)" type="number" min="0" max="750" value={deficit} onChange={(event) => setDeficit(Number(event.target.value))} /></div>
    {preview?.estimate ? <div className="estimate-grid"><div><small>BMR ESTIMATE</small><b>{preview.estimate.bmr} kcal</b></div><div><small>MAINTENANCE</small><b>{preview.estimate.maintenance_calories} kcal</b></div><div><small>GOAL TARGET</small><b>{preview.estimate.calorie_target} kcal</b></div><div><small>MACROS · P / C / F</small><b>{preview.estimate.protein_target_g} / {preview.estimate.carbs_target_g} / {preview.estimate.fat_target_g} g</b></div><p className="estimate-assumptions">Activity factor {preview.estimate.activity_factor} · protein {String(preview.estimate.inputs.protein_g_per_kg)} g/kg · fat about 25% of calories. Food energy conversions (4/4/9 kcal/g) are approximate. Activity factors already approximate average activity; training days are recorded as context, not added again.</p></div> : <p className="muted">{preview?.message ?? "Loading your calculation inputs…"}</p>}
    {preview?.targets_customized && <p className="estimate-warning">You have manually configured nutrition targets. The estimate below will replace them only after you confirm.</p>}
    {error && <div className="inline-error">{error}</div>}{message && <div className="success-note">{message}</div>}
    <div className="assistant-actions"><Button variant="secondary" onClick={loadPreview} disabled={loading}>Refresh estimate</Button><Button onClick={acceptEstimate} disabled={!preview?.estimate || loading}>Review & apply these targets</Button></div>
  </Panel>;
}

type ReminderSettingsValue = {
  timezone_name: string; notifications_enabled: boolean; quiet_start: string | null; quiet_end: string | null; snooze_minutes: number;
  reminders: { meal: string; reminder_time: string; enabled: boolean }[];
};
function ReminderSettings({ onError, onSaved }: { onError: (message: string) => void; onSaved: () => void }) {
  const [settings, setSettings] = useState<ReminderSettingsValue | null>(null);
  const [busy, setBusy] = useState(false);
  const [customMeal, setCustomMeal] = useState("");
  useEffect(() => { api<ReminderSettingsValue>("/reminders/settings").then(setSettings).catch((err) => onError(err instanceof Error ? err.message : "Could not load reminder settings.")); }, [onError]);
  if (!settings) return <Panel title="Meal reminders"><p className="muted">Loading your reminder settings…</p></Panel>;
  function updateReminder(index: number, changes: Partial<ReminderSettingsValue["reminders"][number]>) {
    setSettings((current) => current ? { ...current, reminders: current.reminders.map((item, i) => i === index ? { ...item, ...changes } : item) } : current);
  }
  async function enableBrowserNotifications(enabled: boolean) {
    if (enabled && "Notification" in window && Notification.permission === "default") {
      const permission = await Notification.requestPermission();
      if (permission !== "granted") { onError("Browser notifications were not enabled. In-app reminders still work while AURA is open."); return; }
    }
    if (enabled && (!("Notification" in window) || Notification.permission !== "granted")) {
      onError("This browser has not granted notification permission. In-app reminders remain available.");
      return;
    }
    setSettings((current) => current ? { ...current, notifications_enabled: enabled } : current);
  }
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true);
    try {
      await api("/reminders/settings", { method: "PUT", body: JSON.stringify(settings) });
      onSaved();
    } catch (err) { onError(err instanceof Error ? err.message : "Could not save reminder settings."); }
    finally { setBusy(false); }
  }
  function addCustomReminder() {
    if (!settings) return;
    const meal = customMeal.trim();
    if (!meal || meal.length > 30 || settings.reminders.some((item) => item.meal.toLowerCase() === meal.toLowerCase())) return;
    setSettings((current) => current ? { ...current, reminders: [...current.reminders, { meal, reminder_time: "15:00", enabled: true }] } : current);
    setCustomMeal("");
  }
  return <Panel title="Meal reminders" action={<span className="tiny-label">ONLY WHILE AURA IS OPEN</span>}>
    <p className="muted">AURA checks reminders every 30 seconds while this app is open. Browser notifications are optional; sleeping, closed, or offline computers cannot deliver reminders.</p>
    <form className="reminder-settings-form" onSubmit={save}>
      <Field label="IANA time zone" value={settings.timezone_name} onChange={(event) => setSettings({ ...settings, timezone_name: event.target.value })} placeholder="Asia/Kolkata" />
      <div className="reminder-options">
        {settings.reminders.map((item, index) => <div className="reminder-setting-row" key={item.meal}><label className="reminder-enable"><input type="checkbox" checked={item.enabled} onChange={(event) => updateReminder(index, { enabled: event.target.checked })} /> {item.meal}</label><input aria-label={`${item.meal} reminder time`} type="time" value={item.reminder_time} onChange={(event) => updateReminder(index, { reminder_time: event.target.value })} /><button className="icon-button delete-icon" type="button" aria-label={`Remove ${item.meal} reminder`} onClick={() => setSettings({ ...settings, reminders: settings.reminders.filter((_, i) => i !== index) })}><Trash2 size={14} /></button></div>)}
      </div>
      <div className="custom-reminder-add"><Field label="Custom meal" value={customMeal} onChange={(event) => setCustomMeal(event.target.value)} placeholder="e.g. Post-workout snack" /><Button variant="secondary" onClick={addCustomReminder}><Plus size={15} /> Add reminder</Button></div>
      <div className="estimate-controls"><Field label="Quiet hours start (optional)" type="time" value={settings.quiet_start ?? ""} onChange={(event) => setSettings({ ...settings, quiet_start: event.target.value || null })} /><Field label="Quiet hours end (optional)" type="time" value={settings.quiet_end ?? ""} onChange={(event) => setSettings({ ...settings, quiet_end: event.target.value || null })} /><SelectField label="Snooze (minutes)" value={settings.snooze_minutes} onChange={(event) => setSettings({ ...settings, snooze_minutes: Number(event.target.value) })}>{[5, 10, 15, 20, 30, 45, 60].map((minutes) => <option key={minutes} value={minutes}>{minutes}</option>)}</SelectField></div>
      <label className="reminder-enable browser-notification-setting"><input type="checkbox" checked={settings.notifications_enabled} onChange={(event) => void enableBrowserNotifications(event.target.checked)} /> Browser notifications (asks permission only when enabled)</label>
      <div className="form-actions"><Button type="submit" disabled={busy}>{busy ? "Saving…" : "Save reminder settings"}</Button></div>
    </form>
  </Panel>;
}


type AutomationSettings = {
  timezone_name: string;
  water_reminders_enabled: boolean;
  water_interval_minutes: number;
  morning_briefing_enabled: boolean;
  morning_briefing_time: string;
  evening_checkin_enabled: boolean;
  evening_checkin_time: string;
};
type AutomationEventItem = {
  id: number; kind: string; title: string; message: string; created_at: string; read: boolean;
};
type AutomationAchievement = { id: number; code: string; title: string; description: string; earned_at: string };
type AutomationOverview = {
  today: { calories: number; protein_g: number; water_ml: number; water_target_ml: number; food_entries: number; habits_done: number; habits_total: number; workouts_completed: number };
  suggestions: { title: string; detail: string }[];
  events: AutomationEventItem[];
  achievements: AutomationAchievement[];
};

function AutomationCenter({ onError, onNotice }: { onError: (message: string) => void; onNotice: (message: string) => void }) {
  const [settings, setSettings] = useState<AutomationSettings>({
    timezone_name: "Asia/Kolkata", water_reminders_enabled: true, water_interval_minutes: 90,
    morning_briefing_enabled: true, morning_briefing_time: "07:00",
    evening_checkin_enabled: true, evening_checkin_time: "21:00",
  });
  const [overview, setOverview] = useState<AutomationOverview | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);

  const reload = useCallback(async () => {
    try {
      const [saved, data] = await Promise.all([
        api<AutomationSettings>("/automations/settings"),
        api<AutomationOverview>("/automations/overview"),
      ]);
      setSettings(saved);
      setOverview(data);
    } catch (error) {
      onError(error instanceof Error ? error.message : "Could not load automation settings.");
    } finally {
      setLoading(false);
    }
  }, [onError]);

  useEffect(() => { void reload(); }, [reload]);

  const save = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    try {
      const saved = await api<AutomationSettings>("/automations/settings", { method: "PUT", body: JSON.stringify(settings) });
      setSettings(saved);
      onNotice("Automation preferences saved");
      await reload();
    } catch (error) {
      onError(error instanceof Error ? error.message : "Could not save automation preferences.");
    } finally {
      setBusy(false);
    }
  };

  const runNow = async () => {
    setBusy(true);
    try {
      const result = await api<{ created_events: number; new_achievements: { title: string }[] }>("/automations/run-now", { method: "POST", body: "{}" });
      onNotice(`Automation check complete · ${result.created_events} new event(s), ${result.new_achievements.length} achievement(s)`);
      await reload();
    } catch (error) {
      onError(error instanceof Error ? error.message : "Automation check failed.");
    } finally {
      setBusy(false);
    }
  };

  const markRead = async (id: number) => {
    try {
      await api(`/automations/events/${id}/read`, { method: "POST", body: "{}" });
      await reload();
    } catch (error) {
      onError(error instanceof Error ? error.message : "Could not mark event as read.");
    }
  };

  return <section>
    <PageHeading eyebrow="YOUR PERSONAL AUTOMATION ENGINE" title="AURA automations" description="Helpful check-ins built from your saved data, with controls you can change any time." action={<Button onClick={runNow} disabled={busy}><Activity size={16} /> {busy ? "Checking…" : "Run checks now"}</Button>} />
    <div className="metrics-grid">
      <Metric icon={<Flame size={17} />} title="Logged calories" value={overview?.today.calories ?? 0} unit="kcal" color="orange" note={`${overview?.today.food_entries ?? 0} food entries`} />
      <Metric icon={<Heart size={17} />} title="Protein logged" value={overview?.today.protein_g ?? 0} unit="g" color="lime" note="Recorded entries only" />
      <Metric icon={<Droplets size={17} />} title="Water logged" value={overview?.today.water_ml ?? 0} unit="ml" color="blue" target={overview?.today.water_target_ml} note={`Target ${overview?.today.water_target_ml ?? 2500} ml`} />
      <Metric icon={<Check size={17} />} title="Habits checked" value={`${overview?.today.habits_done ?? 0}/${overview?.today.habits_total ?? 0}`} unit="" color="violet" note={`${overview?.today.workouts_completed ?? 0} completed workouts today`} />
    </div>
    <Panel title="Automation schedule">
      <p className="muted">These settings control when AURA creates persistent reminders and daily summaries. For automatic scheduling while the browser is closed, run the local automation worker described in the README.</p>
      <form className="form-grid automation-form" onSubmit={save}>
        <Field label="Time zone (IANA)" value={settings.timezone_name} onChange={(event) => setSettings({ ...settings, timezone_name: event.target.value })} placeholder="Asia/Kolkata" required />
        <SelectField label="Hydration interval" value={settings.water_interval_minutes} onChange={(event) => setSettings({ ...settings, water_interval_minutes: Number(event.target.value) })}>{[30, 45, 60, 90, 120, 180, 240].map((n) => <option key={n} value={n}>{n} minutes</option>)}</SelectField>
        <label className="automation-toggle"><input type="checkbox" checked={settings.water_reminders_enabled} onChange={(event) => setSettings({ ...settings, water_reminders_enabled: event.target.checked })} /> Hydration check-ins</label>
        <label className="automation-toggle"><input type="checkbox" checked={settings.morning_briefing_enabled} onChange={(event) => setSettings({ ...settings, morning_briefing_enabled: event.target.checked })} /> Morning briefing</label>
        <Field label="Morning briefing time" type="time" value={settings.morning_briefing_time} onChange={(event) => setSettings({ ...settings, morning_briefing_time: event.target.value })} />
        <label className="automation-toggle"><input type="checkbox" checked={settings.evening_checkin_enabled} onChange={(event) => setSettings({ ...settings, evening_checkin_enabled: event.target.checked })} /> Evening check-in</label>
        <Field label="Evening check-in time" type="time" value={settings.evening_checkin_time} onChange={(event) => setSettings({ ...settings, evening_checkin_time: event.target.value })} />
        <div className="form-actions"><Button type="submit" disabled={busy}>{busy ? "Saving…" : "Save automations"}</Button></div>
      </form>
    </Panel>
    <div className="analytics-grid">
      <Panel title="Suggestions from your data">
        {overview?.suggestions.length ? <div className="automation-list">{overview.suggestions.map((item) => <article className="automation-item" key={item.title}><b>{item.title}</b><p>{item.detail}</p></article>)}</div> : <p className="muted">No suggestions right now. AURA only uses information you have recorded.</p>}
      </Panel>
      <Panel title="Achievements">
        {overview?.achievements.length ? <div className="automation-list">{overview.achievements.map((item) => <article className="automation-item achievement-item" key={item.code}><span className="automation-badge"><Sparkles size={16} /></span><div><b>{item.title}</b><p>{item.description}</p><small>{new Date(item.earned_at).toLocaleDateString()}</small></div></article>)}</div> : <p className="muted">Your milestones will appear here as you use AURA. No progress is awarded without matching saved records.</p>}
      </Panel>
    </div>
    <Panel title="Recent automation events" action={<span className="tiny-label">{overview?.events.filter((item) => !item.read).length ?? 0} UNREAD</span>}>
      {loading ? <p className="muted">Loading automation data…</p> : overview?.events.length ? <div className="automation-list">{overview.events.map((item) => <article className={`automation-item automation-event ${item.read ? "read" : ""}`} key={item.id}><div><span className="tiny-label">{item.kind.replaceAll("_", " ").toUpperCase()} · {new Date(item.created_at).toLocaleString()}</span><b>{item.title}</b><p>{item.message}</p></div>{!item.read && <Button variant="quiet" onClick={() => markRead(item.id)}>Mark read</Button>}</article>)}</div> : <p className="muted">No automation events yet. Run a check or start the local worker to create scheduled events.</p>}
    </Panel>
    <div className="privacy-note"><ShieldCheck size={17} /><div><b>Designed for careful tracking</b><p>Suggestions use recorded data only. AURA does not assume an unlogged meal was skipped, and automations never silently change your nutrition targets.</p></div></div>
  </section>;
}
