const COLORS: Record<string, string> = {
  pending: "bg-yellow-100 text-yellow-800",
  sniping: "bg-blue-100 text-blue-800 animate-pulse",
  booked: "bg-green-100 text-green-800",
  failed: "bg-red-100 text-red-800",
};

export function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`inline-block px-2 py-0.5 rounded text-xs font-semibold ${COLORS[status] ?? "bg-gray-100 text-gray-800"}`}>
      {status}
    </span>
  );
}
