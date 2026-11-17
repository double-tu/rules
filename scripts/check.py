#!/usr/bin/env python3
"""产物校验：每个类目在 6 种客户端格式下都必须
  - 非空
  - 无重复
  - 分组内有序（Surge/Loon/QX/Clash）
  - 条目数一致（surge / loon / quantumultx / clash / egern / sing-box）
"""
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
LINE = re.compile(r"^([A-Z0-9-]+,[^,]+(?:,no-resolve)?)$")


def list_entries(path):
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = LINE.match(line.strip()) if not line.startswith(" ") else None
        m = m or (LINE.match(line.strip().lstrip("- ")) if line.strip().startswith("-") else None)
        if m:
            out.append(m.group(1))
    return out


def sorted_groups(items):
    groups = {}
    for it in items:
        groups.setdefault(it.split(",", 1)[0], []).append(it)
    return groups


def check(name, errs):
    surge = list_entries(DIST / "surge" / f"{name}.list")
    loon = list_entries(DIST / "loon" / f"{name}.list")
    qx = list_entries(DIST / "quantumultx" / f"{name}.list")
    clash = list_entries(DIST / "clash" / f"{name}.yaml")

    for label, got in (("surge", surge), ("loon", loon), ("quantumultx", qx), ("clash", clash)):
        if not got:
            errs.append(f"{name}/{label}: 空的")
        if len(got) != len(set(got)):
            errs.append(f"{name}/{label}: 有重复行")
        for k, vals in sorted_groups(got).items():
            if vals != sorted(vals):
                errs.append(f"{name}/{label}: {k} 段未排序")

    # Egern
    eg = (DIST / "egern" / f"{name}.yaml")
    n_eg = 0
    if not eg.exists():
        errs.append(f"{name}/egern: 文件缺失")
    else:
        txt = eg.read_text(encoding="utf-8")
        if not re.search(r"(?m)^[a-z0-9_]+_set:$", txt):
            errs.append(f"{name}/egern: 没有 *_set: 键")
        n_eg = len([l for l in txt.splitlines() if l.startswith("  - ")])

    # sing-box
    sb = DIST / "sing-box" / f"{name}.json"
    n_sb = 0
    if not sb.exists():
        errs.append(f"{name}/sing-box: 文件缺失")
    else:
        try:
            doc = json.loads(sb.read_text(encoding="utf-8"))
            if doc.get("version") != 1:
                errs.append(f"{name}/sing-box: version != 1")
            rules = doc.get("rules") or [{}]
            for key in ("domain_suffix", "domain", "domain_keyword", "ip_cidr"):
                vals = rules[0].get(key, [])
                if vals != sorted(vals):
                    errs.append(f"{name}/sing-box: {key} 未排序")
                if len(vals) != len(set(vals)):
                    errs.append(f"{name}/sing-box: {key} 有重复")
                n_sb += len(vals)
        except Exception as e:  # noqa: BLE001
            errs.append(f"{name}/sing-box: JSON 解析失败 {e}")

    counts = {"surge": len(surge), "loon": len(loon), "qx": len(qx), "clash": len(clash),
              "egern": n_eg, "sing-box": n_sb}
    if len(set(counts.values())) != 1:
        errs.append(f"{name}: 六端条目数不一致 {counts}")
    return counts["surge"]


def main():
    if not DIST.exists():
        sys.exit("dist/ 不存在，先跑 build.py")
    names = sorted(p.stem for p in (DIST / "surge").glob("*.list"))
    errs, total = [], 0
    for n in names:
        total += check(n, errs)
    if errs:
        print("产物校验失败：", file=sys.stderr)
        for e in errs[:40]:
            print("  ✗", e, file=sys.stderr)
        sys.exit(1)
    print(f"产物校验通过：{len(names)} 个类目 / {total} 条规则 / 6 种格式一致")


if __name__ == "__main__":
    main()
