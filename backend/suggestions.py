import json
from typing import Dict

from backend.closepulse_agents import combo_agent, sales_assistant_agent, traffic_light_agent, database_agent


def _safe_json(s: str):
    try:
        return json.loads(s)
    except:
        return None


def make_suggestions(user_text: str) -> Dict[str, str]:
    masked = database_agent.run(user_text) if hasattr(database_agent, "run") else user_text
    out = {"s1": "", "s2": "", "s3": "", "trafficLight": "yellow"}
    c = None
    if hasattr(combo_agent, "run"):
        r = combo_agent.run(masked)
        c = _safe_json(r)
    if c and isinstance(c, dict):
        lst = c.get("suggestions") or []
        if isinstance(lst, list) and len(lst) >= 3:
            out["s1"], out["s2"], out["s3"] = lst[:3]
        tl = c.get("trafficLight")
        if tl in ("green", "yellow", "red"):
            out["trafficLight"] = tl
        if out["s1"] and out["s2"] and out["s3"]:
            return out
    r2 = sales_assistant_agent.run(masked) if hasattr(sales_assistant_agent, "run") else '[]'
    lst2 = _safe_json(r2) or []
    if isinstance(lst2, list):
        lst2 = [x for x in lst2 if isinstance(x, str)]
    while len(lst2) < 3:
        lst2.append("")
    out["s1"], out["s2"], out["s3"] = lst2[:3]
    tl2 = traffic_light_agent.run(masked) if hasattr(traffic_light_agent, "run") else "yellow"
    tl2 = (tl2 or "").strip()
    if tl2 in ("green", "yellow", "red"):
        out["trafficLight"] = tl2
    return out
