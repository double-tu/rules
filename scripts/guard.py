#!/usr/bin/env python3
"""Guard：和上一个 git 提交的 data/counts.json 对比，防止上游挂掉导致规则静默缩水。

参考 VPSDance/ai-proxy-rules 的 guard：单个类目丢失超过阈值（默认 30%）即失败。
用法：python3 scripts/guard.py [--threshold 30] [--ref HEAD]
"""
import argparse
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
COUNTS = ROOT / "data" / "counts.json"


def counts_at(ref):
    try:
        raw = subprocess.run(["git", "show", f"{ref}:data/counts.json"], cwd=ROOT,
                             capture_output=True, text=True, check=True).stdout
        return json.loads(raw)["categories"]
    except Exception:  # noqa: BLE001
        return {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold", type=float, default=30.0)
    ap.add_argument("--ref", default="HEAD")
    a = ap.parse_args()

    if not COUNTS.exists():
        print("没有 data/counts.json，跳过 guard")
        return
    now = json.loads(COUNTS.read_text(encoding="utf-8"))["categories"]
    old = counts_at(a.ref)
    if not old:
        print(f"[guard] 拿不到 {a.ref} 的历史计数（首次运行），跳过")
        return

    fails, warned = [], 0
    for name, cur in sorted(now.items()):
        prev = old.get(name)
        if not prev:
            print(f"[guard] {name:<16} 新增类目 {cur['entries']} 条")
            continue
        o, n = prev["entries"], cur["entries"]
        delta = n - o
        pct = (o - n) / o * 100 if o else 0
        sign = "+" if delta >= 0 else ""
        print(f"[guard] {name:<16} {o} → {n} ({sign}{delta})")
        if pct > a.threshold:
            fails.append(f"{name}: {o} → {n} 条（-{pct:.1f}%，阈值 {a.threshold}%）")
        elif pct > 5:
            warned += 1

    for name in old:
        if name not in now:
            fails.append(f"{name}: 类目消失（上次 {old[name]['entries']} 条）")

    if fails:
        print("\n[guard] 失败：", file=sys.stderr)
        for f in fails:
            print("  ✗", f, file=sys.stderr)
        print("\n规则集大量缩水通常是上游挂了/改了路径，而不是真的该删。"
              "确认无误可用 --threshold 调高或手动更新 data/counts.json。", file=sys.stderr)
        sys.exit(1)
    print(f"[guard] 通过（{len(now)} 个类目，{warned} 个轻微下降 <{a.threshold}%）")


if __name__ == "__main__":
    main()
