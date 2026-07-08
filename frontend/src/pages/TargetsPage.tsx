import { useEffect, useState } from "react";
import { api } from "../api";
import type { Target, Reservation } from "../api";
import { StatusBadge } from "../components/StatusBadge";

export function TargetsPage() {
  const [targets, setTargets] = useState<Target[]>([]);
  const [reservations, setReservations] = useState<Reservation[]>([]);
  const [error, setError] = useState("");
  const [resLoading, setResLoading] = useState(true);

  async function loadTargets() {
    try { setTargets(await api.targets.list()); } catch { setError("Failed to load targets"); }
  }

  async function loadReservations() {
    setResLoading(true);
    try { setReservations(await api.reservations.list()); } catch { /* silent */ }
    finally { setResLoading(false); }
  }

  useEffect(() => {
    loadTargets();
    loadReservations();
  }, []);

  async function handleDelete(id: number) {
    try { await api.targets.delete(id); await loadTargets(); }
    catch { setError("Cannot delete — target may be booked"); }
  }

  const pending = targets.filter(t => t.status === "pending").length;
  const sniping = targets.filter(t => t.status === "sniping").length;
  const booked = targets.filter(t => t.status === "booked").length;
  const failed = targets.filter(t => t.status === "failed").length;

  return (
    <div className="max-w-5xl mx-auto p-8 space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">Dashboard</h1>
        <p className="text-sm text-gray-500 mt-1">Overview of your snipe targets and upcoming reservations.</p>
      </div>

      {error && <p className="text-red-400 text-sm">{error}</p>}

      {/* Stat cards */}
      <div className="grid grid-cols-4 gap-4">
        <StatCard label="Total Targets" value={targets.length} />
        <StatCard label="Pending" value={pending} color="text-yellow-400" />
        <StatCard label="Sniping" value={sniping} color="text-blue-400" pulse={sniping > 0} />
        <StatCard label="Booked" value={booked} color="text-green-400" />
      </div>

      {/* Two-column layout */}
      <div className="grid grid-cols-2 gap-4">
        {/* Upcoming Reservations */}
        <div className="bg-[#1a1a23] border border-[#2a2a35] rounded-xl p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-semibold text-white">Upcoming Reservations</h2>
            <button type="button" onClick={loadReservations}
              className="text-xs text-gray-500 hover:text-white transition-colors">
              Refresh
            </button>
          </div>
          {resLoading ? (
            <p className="text-sm text-gray-500">Loading…</p>
          ) : reservations.length === 0 ? (
            <p className="text-sm text-gray-500">No upcoming reservations.</p>
          ) : (
            <div className="space-y-3">
              {reservations.map((r, i) => (
                <div key={i} className="bg-[#141419] border border-[#2a2a35] rounded-lg p-3">
                  <p className="font-medium text-white text-sm">{r.venue?.name ?? "Unknown venue"}</p>
                  <p className="text-xs text-gray-500 mt-0.5">
                    {r.date ?? "—"} · {r.time_slot ?? ""} · Party of {r.party_size ?? "—"}
                  </p>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* All Targets */}
        <div className="bg-[#1a1a23] border border-[#2a2a35] rounded-xl p-5">
          <h2 className="font-semibold text-white mb-4">All Targets</h2>
          {targets.length === 0 ? (
            <p className="text-sm text-gray-500">No targets yet.</p>
          ) : (
            <div className="space-y-2">
              {targets.map(t => (
                <div key={t.id} className="bg-[#141419] border border-[#2a2a35] rounded-lg p-3 flex items-center justify-between">
                  <div className="min-w-0">
                    <p className="font-medium text-white text-sm truncate">{t.venue_name}</p>
                    <p className="text-xs text-gray-500 mt-0.5">{t.date} · Party of {t.party_size}</p>
                    {t.booked_at && <p className="text-xs text-green-400 mt-0.5">Booked {t.booked_at}</p>}
                  </div>
                  <div className="flex items-center gap-2 ml-3 shrink-0">
                    <StatusBadge status={t.status} />
                    {t.status !== "booked" && (
                      <button type="button" onClick={() => handleDelete(t.id)}
                        className="text-gray-500 hover:text-red-400 text-xs transition-colors">Delete</button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {failed > 0 && (
        <p className="text-xs text-gray-500">
          {failed} target{failed > 1 ? "s" : ""} failed — you can delete and re-add them from the Add Target page.
        </p>
      )}
    </div>
  );
}

function StatCard({ label, value, color, pulse }: { label: string; value: number; color?: string; pulse?: boolean }) {
  return (
    <div className="bg-[#1a1a23] border border-[#2a2a35] rounded-xl p-4">
      <p className="text-sm text-gray-500">{label}</p>
      <p className={`text-3xl font-bold mt-1 ${color ?? "text-white"} ${pulse ? "animate-pulse" : ""}`}>{value}</p>
    </div>
  );
}
