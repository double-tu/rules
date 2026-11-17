#!/usr/bin/env python3
"""多元采集：按 upstreams.yml 拉取上游规则 → 归一化为 Surge 语法 → 去重排序 → sources/auto/<name>.txt

单个上游失败不影响其余；全部失败则保留上一次的产物（不会把文件清空）。
"""
import pathlib
import re
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
AUTO = ROOT / "sources" / "auto"
CFG = ROOT / "upstreams.yml"
UA = {"User-Agent": "rules-bot/1.0 (+https://github.com/double-tu/rules)"}


def fetch(url: str, timeout=30) -> str:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def norm_surge(text):
    """DOMAIN-SUFFIX,x 之类的纯文本"""
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
    """Egern 原生 YAML：domain_suffix_set / domain_set / ... 逐行扫，不依赖 yaml 库"""
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
    """自动识别上游格式：egern 原生 YAML / Clash rule-provider / Surge(QX) 文本"""
    if re.search(r"(?m)^payload:\s*$", text):
        return "clash"
    if re.search(r"(?m)^[a-z0-9_]+_set:\s*$", text) or re.search(r"(?m)^no_resolve:", text):
        return "egern"
    return "surge"


def collect(name, cfg):
    rules, ok = {}, []
    for src in cfg.get("sources", []):
        url, fmt = src["url"], src.get("format", "auto")
        try:
            text = fetch(url, timeout=60)
            if fmt == "auto":
                fmt = detect(text)
            items = PARSERS[fmt](text)
            for kind, val, opts in items:
                item = val if kind.startswith("IP-") else val.lower()
                if kind.startswith("IP-") and "no-resolve" in opts:
                    item += ",no-resolve"
                rules.setdefault(kind, set()).add(item)
            ok.append(url)
            print(f"    ✓ {fmt:<6} {len(items):>5} 条  {url}")
        except Exception as e:  # 单源失败继续
            print(f"    ✗ {fmt:<6} {url} -> {type(e).__name__}: {e}", file=sys.stderr)
    if not ok:
        print(f"  !! {name}: 全部上游失败，保留上次产物", file=sys.stderr)
        return None
    lines = [f"# {cfg.get('title', name)}",
             f"# auto: {len(ok)}/{len(cfg.get('sources', []))} 上游成功，去重后如下",
             "# 由 scripts/collect.py 生成，勿手改", ""]
    for kind in ("DOMAIN-SUFFIX", "DOMAIN", "DOMAIN-KEYWORD", "IP-CIDR", "IP-CIDR6"):
        lines += [f"{kind},{v}" for v in sorted(rules.get(kind, ()))]
    AUTO.mkdir(parents=True, exist_ok=True)
    path = AUTO / f"{name}.txt"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path, sum(len(v) for v in rules.values())


def main():
    if not CFG.exists():
        sys.exit("没有 upstreams.yml")
    try:
        import yaml
    except ImportError:
        sys.exit("需要 PyYAML（Action 里用 pip install pyyaml）")
    cfgs = yaml.safe_load(CFG.read_text(encoding="utf-8")) or {}
    for name, cfg in cfgs.items():
        print(f"  [{name}]")
        res = collect(name, cfg)
        if res:
            print(f"  -> sources/auto/{name}.txt  {res[1]} 条")


if __name__ == "__main__":
    main()
