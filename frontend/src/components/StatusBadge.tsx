const COLORS: Record<string, string> = {
  pending: "bg-yellow-500/15 text-yellow-400",
  sniping: "bg-blue-500/15 text-blue-400 animate-pulse",
  booked: "bg-green-500/15 text-green-400",
  failed: "bg-red-500/15 text-red-400",
  completed: "bg-gray-500/15 text-gray-500",
};

export function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`inline-block px-2.5 py-1 rounded-full text-xs font-semibold ${COLORS[status] ?? "bg-gray-500/15 text-gray-400"}`}>
      {status}
    </span>
  );
}
