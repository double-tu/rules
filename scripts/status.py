#!/usr/bin/env python3
"""生成 STATUS.md：每个类目的条目数 + 每个上游的拉取状态（成功/走缓存/失败）。"""
import json
import pathlib
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
COUNTS = ROOT / "data" / "counts.json"
REPORT = ROOT / "data" / "fetch-report.json"
OUT = ROOT / "STATUS.md"


def main():
    counts = json.loads(COUNTS.read_text(encoding="utf-8")) if COUNTS.exists() else {"categories": {}}
    report = json.loads(REPORT.read_text(encoding="utf-8")) if REPORT.exists() else {}
    cats = counts.get("categories", {})

    ok = sum(1 for v in report.values() for s in v if s["status"] == "ok")
    cache = sum(1 for v in report.values() for s in v if s["status"] == "stale-cache")
    fail = sum(1 for v in report.values() for s in v if s["status"] not in ("ok", "stale-cache"))

    lines = [
        "# STATUS", "",
        f"最后生成：{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"类目：{len(cats)} · 规则总数：{sum(c['entries'] for c in cats.values())}",
        f"上游：{ok} 成功 / {cache} 走缓存 / {fail} 失败", "",
        "| 类目 | 条目 | 来源 | 上游状态 |",
        "|---|---:|---|---|",
    ]
    for name, c in sorted(cats.items(), key=lambda kv: -kv[1]["entries"]):
        srcs = report.get(name, [])
        if not srcs:
            state = "_手写_" if c.get("origin") == "manual" else "-"
        else:
            o = sum(1 for s in srcs if s["status"] == "ok")
            st = sum(1 for s in srcs if s["status"] == "stale-cache")
            f = len(srcs) - o - st
            bits = [f"{o}/{len(srcs)} 成功"]
            if st:
                bits.append(f"{st} 缓存")
            if f:
                bits.append(f"**{f} 失败**")
            state = " · ".join(bits)
        origin = "手写+采集" if c.get("has_manual") and c.get("has_auto") else (
            "手写" if c.get("has_manual") else "采集")
        lines.append(f"| `{name}` | {c['entries']} | {origin} | {state} |")

    if fail or cache:
        lines += ["", "## 需要注意", ""]
        for name, srcs in sorted(report.items()):
            for s in srcs:
                if s["status"] == "stale-cache":
                    lines.append(f"- `{name}` 走缓存（{s.get('age_days', '?')} 天前）：{s['url']}")
                elif s["status"] not in ("ok", "stale-cache"):
                    lines.append(f"- `{name}` 失败：{s['url']} — {s.get('error', '?')}")
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"STATUS.md 已更新：{len(cats)} 类目，{ok} 上游成功 / {cache} 缓存 / {fail} 失败")


if __name__ == "__main__":
    main()
