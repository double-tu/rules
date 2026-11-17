#!/usr/bin/env python3
"""多元采集：按 upstreams.yml 拉取上游 → 自动识别格式 → 归一化 → 去重 → sources/auto/<name>.txt

三道保险（参考 VPSDance/ai-proxy-rules）：
  1. 缓存：data/cache/ 存上次成功内容；本次失败时回退缓存（并标记 stale 天数）
  2. 镜像：raw.githubusercontent.com 失败时自动改用 cdn.jsdelivr.net 重试
  3. 并发 + 重试：8 线程，单 URL 最多 3 次
结果：data/fetch-report.json（每源状态，供 STATUS.md 使用）
"""
import hashlib
import json
import pathlib
import re
import sys
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = pathlib.Path(__file__).resolve().parent.parent
AUTO = ROOT / "sources" / "auto"
CACHE = ROOT / "data" / "cache"
CFG = ROOT / "upstreams.yml"
REPORT = ROOT / "data" / "fetch-report.json"
UA = {"User-Agent": "double-tu-rules/1.0 (+https://github.com/double-tu/rules)"}
STALE_DAYS = 30
_lock = threading.Lock()


# ---------- 格式解析 ----------

def norm_surge(text):
    out = []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith(("//", ";", "[")):
            continue
        parts = [p.strip() for p in line.split(",")]
        if parts[0].upper() not in ("DOMAIN", "DOMAIN-SUFFIX", "DOMAIN-KEYWORD",
                                    "IP-CIDR", "IP-CIDR6", "HOST", "HOST-SUFFIX", "HOST-KEYWORD"):
            continue
        kind = parts[0].upper().replace("HOST", "DOMAIN")
        out.append((kind, parts[1], parts[2:]))
    return out


def norm_clash(text):
    out = []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        m = re.match(r"^-\s*([A-Z0-9-]+)\s*,\s*([^,]+)\s*(?:,\s*(.+))?$", line)
        if not m:
            continue
        kind, val, opt = m.group(1), m.group(2).strip(), m.group(3)
        if kind not in ("DOMAIN", "DOMAIN-SUFFIX", "DOMAIN-KEYWORD", "IP-CIDR", "IP-CIDR6"):
            continue
        out.append((kind, val, [opt] if opt else []))
    return out


def norm_egern(text):
    mapping = {"domain_suffix_set": "DOMAIN-SUFFIX", "domain_set": "DOMAIN",
               "domain_keyword_set": "DOMAIN-KEYWORD", "ip_cidr_set": "IP-CIDR",
               "ip_cidr6_set": "IP-CIDR6"}
    out, cur = [], None
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        m = re.match(r"^([a-z0-9_]+):\s*$", line)
        if m:
            cur = mapping.get(m.group(1))
            continue
        m = re.match(r"^\s*-\s*(.+)$", line)
        if m and cur:
            out.append((cur, m.group(1).strip().strip('"\''), []))
    return out


PARSERS = {"surge": norm_surge, "clash": norm_clash, "egern": norm_egern}


def detect(text):
    if re.search(r"(?m)^payload:\s*$", text):
        return "clash"
    if re.search(r"(?m)^[a-z0-9_]+_set:\s*$", text) or re.search(r"(?m)^no_resolve:", text):
        return "egern"
    return "surge"


# ---------- 缓存 + 镜像 + 重试 ----------

def mirror(url):
    m = re.match(r"https://raw\.githubusercontent\.com/([^/]+)/([^/]+)/([^/]+)/(.+)$", url)
    if m:
        return f"https://cdn.jsdelivr.net/gh/{m.group(1)}/{m.group(2)}@{m.group(3)}/{m.group(4)}"
    m = re.match(r"https://github\.com/([^/]+)/([^/]+)/raw/([^/]+)/(.+)$", url)
    if m:
        return f"https://cdn.jsdelivr.net/gh/{m.group(1)}/{m.group(2)}@{m.group(3)}/{m.group(4)}"
    return None


def cache_path(url):
    return CACHE / f"{hashlib.sha1(url.encode()).hexdigest()}.txt"


def http_get(url, timeout=30, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.5 * (i + 1))
    raise last


def fetch(url):
    """返回 (text, meta)。成功则写缓存；失败则回退缓存。"""
    CACHE.mkdir(parents=True, exist_ok=True)
    start = time.time()
    for attempt, candidate in enumerate([url, mirror(url)]):
        if not candidate:
            continue
        try:
            text = http_get(candidate)
            with _lock:
                cache_path(url).write_text(text, encoding="utf-8")
            return text, {"status": "ok", "via": "direct" if attempt == 0 else "mirror",
                          "bytes": len(text), "ms": int((time.time() - start) * 1000)}
        except Exception as e:  # noqa: BLE001
            err = f"{type(e).__name__}: {e}"
    cp = cache_path(url)
    if cp.exists():
        age_days = int((time.time() - cp.stat().st_mtime) / 86400)
        return cp.read_text(encoding="utf-8"), {"status": "stale-cache", "via": "cache",
                                                "age_days": age_days, "error": err}
    return None, {"status": "failed", "error": err}


def collect_one(task):
    name, cfg, src = task
    url = src["url"]
    text, meta = fetch(url)
    if text is None:
        return name, url, None, meta
    fmt = src.get("format", "auto")
    if fmt == "auto":
        fmt = detect(text)
    try:
        items = PARSERS[fmt](text)
        meta["format"] = fmt
        meta["parsed"] = len(items)
        return name, url, items, meta
    except Exception as e:  # noqa: BLE001
        meta.update({"status": "parse-failed", "error": f"{type(e).__name__}: {e}", "format": fmt})
        return name, url, None, meta


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["all", "light", "heavy"], default="all")
    args = ap.parse_args()
    if not CFG.exists():
        sys.exit("没有 upstreams.yml")
    try:
        import yaml
    except ImportError:
        sys.exit("需要 PyYAML（Action 里 pip install pyyaml）")
    cfgs = yaml.safe_load(CFG.read_text(encoding="utf-8")) or {}
    if args.only == "light":
        cfgs = {n: c for n, c in cfgs.items() if not (c or {}).get("heavy")}
    elif args.only == "heavy":
        cfgs = {n: c for n, c in cfgs.items() if (c or {}).get("heavy")}

    tasks = [(name, cfg, src) for name, cfg in cfgs.items() for src in cfg.get("sources", [])]
    print(f"并发拉取 {len(tasks)} 个上游（8 线程，raw 失败自动走 jsdelivr）...")
    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(collect_one, tasks))

    by_cat, report = {}, {}
    for name, url, items, meta in results:
        report.setdefault(name, []).append({"url": url, **meta})
        if items:
            bucket = by_cat.setdefault(name, {})
            for kind, val, opts in items:
                item = val if kind.startswith("IP-") else val.lower()
                if kind.startswith("IP-") and "no-resolve" in opts:
                    item += ",no-resolve"
                bucket.setdefault(kind, set()).add(item)

    AUTO.mkdir(parents=True, exist_ok=True)
    for name, cfg in cfgs.items():
        rules = by_cat.get(name)
        entries = report.get(name, [])
        ok = [r for r in entries if r["status"] == "ok"]
        stale = [r for r in entries if r["status"] == "stale-cache"]
        bad = [r for r in entries if r["status"] not in ("ok", "stale-cache")]
        if not rules:
            print(f"  !! {name}: 全部源失败且无缓存，保留上次产物")
            continue
        lines = [f"# {cfg.get('title', name)}",
                 f"# auto: {len(ok)} 成功 / {len(stale)} 走缓存 / {len(bad)} 失败，去重后如下",
                 f"# 由 scripts/collect.py 生成，勿手改（改 upstreams.yml）", ""]
        for kind in ("DOMAIN-SUFFIX", "DOMAIN", "DOMAIN-KEYWORD", "IP-CIDR", "IP-CIDR6"):
            lines += [f"{kind},{v}" for v in sorted(rules.get(kind, ()))]
        (AUTO / f"{name}.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
        total = sum(len(v) for v in rules.values())
        flag = "⚠" if bad or stale else " "
        print(f"  {flag} {name:<14} {total:>7} 条  (ok {len(ok)} / cache {len(stale)} / fail {len(bad)})")

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    merged = {}
    if REPORT.exists():
        try:
            merged = json.loads(REPORT.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            merged = {}
    merged.update(report)
    REPORT.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
