import { Link, useLocation } from "react-router-dom";

export function NavBar() {
  const { pathname } = useLocation();
  const link = (to: string, label: string) => (
    <Link
      to={to}
      className={`px-4 py-2 rounded text-sm font-medium ${pathname === to ? "bg-indigo-700 text-white" : "text-indigo-100 hover:bg-indigo-600"}`}
    >
      {label}
    </Link>
  );
  return (
    <nav className="bg-indigo-800 px-6 py-3 flex gap-2">
      <span className="text-white font-bold mr-4">Resy Bot</span>
      {link("/", "Targets")}
      {link("/settings", "Settings")}
    </nav>
  );
}
