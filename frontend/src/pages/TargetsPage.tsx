import { useEffect, useState } from "react";
import { api } from "../api";
import type { Target, TargetCreate, Reservation } from "../api";
import { StatusBadge } from "../components/StatusBadge";

const EMPTY_FORM: TargetCreate = {
  venue_id: "", venue_name: "", date: "", party_size: 2,
  opening_time: "", preferred_time: "", window_start: "", window_end: "",
};

function StatCard({ label, value, color, pulse }: { label: string; value: number; color?: string; pulse?: boolean }) {
  return (
    <div className="bg-[#1a1a23] border border-[#2a2a35] rounded-xl p-4">
      <p className="text-sm text-gray-500">{label}</p>
      <p className={`text-3xl font-bold mt-1 ${color ?? "text-white"} ${pulse ? "animate-pulse" : ""}`}>{value}</p>
    </div>
  );
}

export function TargetsPage() {
  const [targets, setTargets] = useState<Target[]>([]);
  const [reservations, setReservations] = useState<Reservation[]>([]);
  const [form, setForm] = useState<TargetCreate>(EMPTY_FORM);
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState("");
  const [resLoading, setResLoading] = useState(false);

  async function loadTargets() {
    try { setTargets(await api.targets.list()); } catch { setError("Failed to load targets"); }
  }

  async function loadReservations() {
    setResLoading(true);
    try { setReservations(await api.reservations.list()); } catch { /* ignore */ }
    finally { setResLoading(false); }
  }

  useEffect(() => { loadTargets(); loadReservations(); }, []);

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault();
    setAdding(true);
    setError("");
    try {
      await api.targets.add(form);
      setForm(EMPTY_FORM);
      await loadTargets();
    } catch {
      setError("Failed to add target");
    } finally {
      setAdding(false);
    }
  }

  async function handleDelete(id: string) {
    try { await api.targets.delete(id); await loadTargets(); }
    catch { setError("Failed to delete target (may not be pending)"); }
  }

  const activeTargets = targets.filter(t => t.status !== "completed");
  const completedTargets = targets.filter(t => t.status === "completed");

  const field = (label: string, key: keyof TargetCreate, type = "text", extra?: object) => (
    <div className="flex flex-col gap-1.5">
      <label className="text-sm text-gray-400">{label}</label>
      <input
        type={type}
        className="bg-[#141419] border border-[#2a2a35] rounded-md px-3 py-2 text-sm text-white placeholder-gray-600 focus:border-green-500 focus:outline-none focus:ring-1 focus:ring-green-500"
        value={String(form[key] ?? "")}
        onChange={e => setForm(f => ({ ...f, [key]: type === "number" ? Number(e.target.value) : e.target.value }))}
        {...extra}
      />
    </div>
  );

  return (
    <div className="max-w-5xl mx-auto p-8 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Snipe Targets</h1>
        <p className="text-sm text-gray-500 mt-1">Manage your snipe targets and view upcoming reservations.</p>
      </div>

      {error && <p className="text-red-400 text-sm">{error}</p>}

      <div className="grid grid-cols-4 gap-4">
        <StatCard label="Total" value={activeTargets.length} />
        <StatCard label="Pending" value={activeTargets.filter(t => t.status === "pending").length} color="text-yellow-400" />
        <StatCard label="Sniping" value={activeTargets.filter(t => t.status === "sniping").length} color="text-blue-400" pulse={activeTargets.some(t => t.status === "sniping")} />
        <StatCard label="Booked" value={activeTargets.filter(t => t.status === "booked").length} color="text-green-400" />
      </div>

      <form onSubmit={handleAdd} className="bg-[#1a1a23] border border-[#2a2a35] rounded-xl p-6 grid grid-cols-2 gap-4">
        <h2 className="col-span-2 font-semibold text-white">Add Target</h2>
        {field("Venue ID", "venue_id", "text", { required: true })}
        {field("Venue Name", "venue_name", "text", { required: true })}
        {field("Date", "date", "date", { required: true })}
        {field("Party Size", "party_size", "number", { min: 1, max: 20, required: true })}
        {field("Opening Time (UTC)", "opening_time", "datetime-local", { required: true })}
        {field("Preferred Time (optional)", "preferred_time", "time")}
        {field("Window Start (optional)", "window_start", "time")}
        {field("Window End (optional)", "window_end", "time")}
        <div className="col-span-2">
          <button type="submit" disabled={adding}
            className="bg-green-600 text-white px-5 py-2 rounded-md text-sm font-medium hover:bg-green-500 disabled:opacity-50 transition-colors">
            {adding ? "Adding..." : "Add Target"}
          </button>
        </div>
      </form>

      <div className="space-y-3">
        <h2 className="font-semibold text-white">Active Targets</h2>
        {activeTargets.length === 0 && <p className="text-gray-500 text-sm">No active targets.</p>}
        {activeTargets.map(t => (
          <div key={t.id} className="bg-[#1a1a23] border border-[#2a2a35] rounded-xl p-4 flex items-center justify-between">
            <div>
              <p className="font-medium text-white">{t.venue_name}</p>
              <p className="text-sm text-gray-500">
                {t.date} · Party of {t.party_size} · Opens {t.opening_time}
              </p>
              {t.preferred_time && <p className="text-xs text-gray-400">Preferred: {t.preferred_time}</p>}
              {(t.window_start || t.window_end) && (
                <p className="text-xs text-gray-400">
                  Window: {t.window_start || "any"} – {t.window_end || "any"}
                </p>
              )}
              {t.booked_at && <p className="text-xs text-green-400 mt-1">Booked at {t.booked_at}</p>}
            </div>
            <div className="flex items-center gap-3">
              <StatusBadge status={t.status} />
              {t.status === "pending" && (
                <button onClick={() => handleDelete(t.id)}
                  className="text-gray-500 hover:text-red-400 text-sm transition-colors">Delete</button>
              )}
            </div>
          </div>
        ))}
      </div>

      {completedTargets.length > 0 && (
        <div className="space-y-3">
          <h2 className="font-semibold text-gray-500">Completed</h2>
          {completedTargets.map(t => (
            <div key={t.id} className="bg-[#141419] border border-[#2a2a35] rounded-xl p-4 flex items-center justify-between opacity-60">
              <div>
                <p className="font-medium text-gray-400">{t.venue_name}</p>
                <p className="text-sm text-gray-500">{t.date} · Party of {t.party_size}</p>
              </div>
              <StatusBadge status={t.status} />
            </div>
          ))}
        </div>
      )}

      <div className="space-y-3">
        <div className="flex items-center gap-3">
          <h2 className="font-semibold text-white">Upcoming Reservations</h2>
          <button onClick={loadReservations} disabled={resLoading}
            className="text-xs text-gray-500 hover:text-white transition-colors disabled:opacity-50">
            {resLoading ? "Loading..." : "Refresh"}
          </button>
        </div>
        {reservations.length === 0 && <p className="text-gray-500 text-sm">No upcoming reservations.</p>}
        {reservations.map((r, i) => (
          <div key={i} className="bg-[#1a1a23] border border-[#2a2a35] rounded-xl p-4">
            <p className="font-medium text-white">{r.venue?.name}</p>
            <p className="text-sm text-gray-500">{r.date} · {r.time_slot} · Party of {r.party_size}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
