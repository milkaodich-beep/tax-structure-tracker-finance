import React from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

const api = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api/v1";

function App() {
  const [health,setHealth]=React.useState<string>("Checking API…");
  const [flags,setFlags]=React.useState<any[]>([]);
  React.useEffect(()=>{ fetch(api.replace("/api/v1","")+"/health").then(r=>r.json()).then(x=>setHealth(x.status)).catch(()=>setHealth("offline"));
    fetch(api+"/risk-flags").then(r=>r.json()).then(setFlags).catch(()=>setFlags([])); },[]);
  return <main><header><div><p className="eyebrow">FINANCE CONTROL</p><h1>International Tax Structure Tracker</h1><p className="muted">Evidence, transaction lifecycle and invoice control dashboard.</p></div><span className={"status "+health}>{health}</span></header>
    <section className="grid"><article><h2>Finance lifecycle</h2><p>DRAFT → PENDING APPROVAL → APPROVED → ISSUED → POSTED → SETTLED</p><p className="muted">Posted financial values are immutable at the service boundary. Corrections use controlled adjustment documents.</p></article>
    <article><h2>Risk flags</h2>{flags.length ? <ul>{flags.map((f,i)=><li key={i}><b>{f.severity}</b> — {f.message}</li>)}</ul>:<p className="muted">No current flags returned.</p>}</article></section>
  </main>;
}
createRoot(document.getElementById("root")!).render(<React.StrictMode><App/></React.StrictMode>);
