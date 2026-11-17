#!/usr/bin/env python3
"""产物校验（6 端）。

核心规则（域名/IP）在 6 种格式里必须完全一致；regex/通配符类规则各客户端能力不同，
只校验「有序、无重复」并单独汇报数量。
"""
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
CORE = {"DOMAIN", "DOMAIN-SUFFIX", "DOMAIN-KEYWORD", "IP-CIDR", "IP-CIDR6"}
EXTRA = {"DOMAIN-REGEX", "DOMAIN-WILDCARD", "URL-REGEX", "USER-AGENT",
         "HOST-REGEX", "HOST-WILDCARD", "IP6-CIDR"}
LINE = re.compile(r"^(?:-\s+)?([A-Z0-9-]+),(.+)$")


def scan(path, extra_map=None):
    core, extra = [], []
    if not path.exists():
        return core, extra
    for raw in path.read_text(encoding="utf-8").splitlines():
        if raw.lstrip().startswith("#"):
            continue
        m = LINE.match(raw.strip())
        if not m:
            continue
        kind = m.group(1)
        if extra_map:
            kind = extra_map.get(kind, kind)
        if kind in CORE or (kind == "IP6-CIDR" and "IP-CIDR6" in CORE):
            core.append(f"{'IP-CIDR6' if kind == 'IP6-CIDR' else kind},{m.group(2)}")
        elif kind in EXTRA:
            extra.append(f"{kind},{m.group(2)}")
    return core, extra


def egern_counts(path):
    core = extra = 0
    if not path.exists():
        return core, extra
    cur = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^([a-z0-9_]+_set):\s*$", raw)
        if m:
            cur = m.group(1)
            continue
        if raw.startswith("  - ") and cur:
            if cur in ("domain_regex_set", "domain_wildcard_set", "url_regex_set", "user_agent_set"):
                extra += 1
            else:
                core += 1
    return core, extra


def singbox_counts(path):
    if not path.exists():
        return 0, 0
    doc = json.loads(path.read_text(encoding="utf-8"))
    if doc.get("version") != 1:
        raise ValueError("version != 1")
    r = (doc.get("rules") or [{}])[0]
    core = sum(len(r.get(k, [])) for k in ("domain", "domain_suffix", "domain_keyword", "ip_cidr"))
    for k in ("domain", "domain_suffix", "domain_keyword", "ip_cidr", "domain_regex"):
        vals = r.get(k, [])
        if vals != sorted(vals):
            raise ValueError(f"{k} 未排序")
        if len(vals) != len(set(vals)):
            raise ValueError(f"{k} 有重复")
    return core, len(r.get("domain_regex", []))


def check(name, errs):
    sx = {"HOST-SUFFIX": "DOMAIN-SUFFIX", "HOST": "DOMAIN", "HOST-KEYWORD": "DOMAIN-KEYWORD",
          "HOST-REGEX": "DOMAIN-REGEX", "HOST-WILDCARD": "DOMAIN-WILDCARD"}
    g = {}
    for label, path, xmap in (
        ("surge", DIST / "surge" / f"{name}.list", None),
        ("loon", DIST / "loon" / f"{name}.list", None),
        ("quantumultx", DIST / "quantumultx" / f"{name}.list", sx),
        ("clash", DIST / "clash" / f"{name}.yaml", None),
    ):
        core, extra = scan(path, xmap)
        if not core:
            errs.append(f"{name}/{label}: 核心规则为空")
        for arr, what in ((core, "核心"), (extra, "regex")):
            if len(arr) != len(set(arr)):
                errs.append(f"{name}/{label}: {what}有重复")
            groups = {}
            for it in arr:
                groups.setdefault(it.split(",", 1)[0], []).append(it)
            for k, vals in groups.items():
                if vals != sorted(vals):
                    errs.append(f"{name}/{label}: {k} 未排序")
        g[label] = len(core)
    try:
        g["egern"], e_eg = egern_counts(DIST / "egern" / f"{name}.yaml")
        if g["egern"] == 0:
            errs.append(f"{name}/egern: 空")
    except Exception as e:  # noqa: BLE001
        errs.append(f"{name}/egern: {e}")
    try:
        g["sing-box"], e_sb = singbox_counts(DIST / "sing-box" / f"{name}.json")
    except Exception as e:  # noqa: BLE001
        errs.append(f"{name}/sing-box: {e}")
        e_sb = 0
    if len(set(g.values())) != 1:
        errs.append(f"{name}: 六端核心规则数不一致 {g}")
    return g.get("surge", 0), max(len(extra), e_eg, e_sb)


def main():
    if not DIST.exists():
        sys.exit("dist/ 不存在，先跑 build.py")
    names = sorted(p.stem for p in (DIST / "surge").glob("*.list"))
    errs, total, extra_total = [], 0, 0
    for n in names:
        c, e = check(n, errs)
        total += c
        extra_total += e
    if errs:
        print("产物校验失败：", file=sys.stderr)
        for e in errs[:40]:
            print("  ✗", e, file=sys.stderr)
        sys.exit(1)
    print(f"产物校验通过：{len(names)} 个类目 / {total} 条核心规则 / "
          f"{extra_total} 条 regex·通配符 / 6 种格式一致")


if __name__ == "__main__":
    main()
