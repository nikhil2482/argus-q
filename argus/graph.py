"""Graph export and interactive visualization (pyvis)."""
from __future__ import annotations

import html

import networkx as nx

from .store import Store

COLORS = {"US": "#3b82f6", "concern": "#ef4444", "review": "#f59e0b", "foreign": "#94a3b8",
          "agent": "#10b981", "person": "#cbd5e1", "unknown": "#e2e8f0"}


def to_networkx(store: Store) -> nx.MultiDiGraph:
    g = nx.MultiDiGraph()
    for e in store.all_entities():
        g.add_node(e["id"], **{k: v for k, v in e.items() if k != "attrs"}, screening=e["attrs"].get("screening"))
    for r in store.all_relationships():
        g.add_edge(r["src"], r["dst"], rel_type=r["rel_type"], evidence_id=r["evidence_id"], origin=r["origin"])
    return g


def _color(n: dict) -> str:
    hits = n.get("screening") or []
    if any(h["match"] in ("exact", "strong") for h in hits):
        return COLORS["concern"]
    if hits:
        return COLORS["review"]
    if n.get("origin") == "agent":
        return COLORS["agent"]
    if n.get("kind") == "person":
        return COLORS["person"]
    if n.get("country") == "US":
        return COLORS["US"]
    return COLORS["foreign"] if n.get("country") else COLORS["unknown"]


def to_html(store: Store, max_nodes: int = 200, height: str = "640px") -> str:
    from pyvis.network import Network

    g = to_networkx(store)
    if g.number_of_nodes() > max_nodes:
        keep = sorted(g.degree, key=lambda x: -x[1])[:max_nodes]
        g = g.subgraph([k for k, _ in keep]).copy()
    net = Network(height=height, width="100%", directed=True, bgcolor="#0b1220", font_color="#e5e7eb", cdn_resources="in_line")
    net.set_options("""{
      "physics": {"barnesHut": {"gravitationalConstant": -9000, "springLength": 150, "avoidOverlap": 0.3},
                  "stabilization": {"enabled": true, "iterations": 400, "fit": true}},
      "edges": {"smooth": {"type": "continuous"}},
      "nodes": {"font": {"size": 18, "strokeWidth": 3, "strokeColor": "#0b1220"}},
      "interaction": {"hover": true, "tooltipDelay": 120}
    }""")
    deg = dict(g.degree)
    for nid, d in g.nodes(data=True):
        org = d.get("kind") != "person"
        label = html.escape(d.get("name") or nid)
        tip = f"{label}\n{d.get('kind')} · {html.escape(str(d.get('country') or '—'))}\nid: {html.escape(nid)}"
        if d.get("screening"):
            tip += f"\nscreening: {d['screening'][0]['match']} match ({d['screening'][0]['score']})"
        net.add_node(nid, label=label if org else label.split()[-1], title=tip, color=_color(d),
                     shape="dot" if org else "triangle", size=(12 if org else 7) + min(deg.get(nid, 0), 20))
    for s, t, d in g.edges(data=True):
        net.add_edge(s, t, title=html.escape(f"{d['rel_type']} ({d['evidence_id']})"),
                     color="#10b981" if d["origin"] == "agent" else "#475569",
                     width=3 if d["origin"] == "agent" else 1, arrows="to" if d["origin"] == "agent" else "")
    page = net.generate_html(notebook=False)
    # The graph may be drawn while its tab is hidden (zero size); refit whenever it becomes visible.
    refit = """<script>
    (function () {
      function fit() { try { network.setSize("100%", "100%"); network.redraw(); network.fit(); } catch (e) {} }
      try { network.once("stabilizationIterationsDone", fit); } catch (e) {}
      var lastW = 0, lastH = 0;
      setInterval(function () {
        var el = document.getElementById("mynetwork");
        if (!el) return;
        var w = el.offsetWidth, h = el.offsetHeight;
        if (w > 0 && h > 0 && (w !== lastW || h !== lastH)) { lastW = w; lastH = h; setTimeout(fit, 80); }
      }, 300);
    })();
    </script>"""
    return page.replace("</body>", refit + "</body>")
