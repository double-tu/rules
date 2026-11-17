#!/usr/bin/env python3
"""产物校验：每个类目 4 个客户端格式都必须
  - 非空
  - 无重复行
  - 已排序
  - 三端条目数一致（surge / quantumultx / clash 是同一批规则的不同写法）
"""
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
sys.path.insert(0, str(ROOT / "scripts"))


def entries(path, pattern):
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(pattern, line)
        if m:
            out.append(m.group(1))
    return out


def check(name, errs):
    surge = entries(DIST / "surge" / f"{name}.list", r"^([A-Z0-9-]+,[^,]+(?:,no-resolve)?)$")
    qx = entries(DIST / "quantumultx" / f"{name}.list", r"^([A-Z0-9-]+,[^,]+(?:,no-resolve)?)$")
    clash = entries(DIST / "clash" / f"{name}.yaml", r"^\s+-\s+([A-Z0-9-]+,[^,]+(?:,no-resolve)?)$")
    egern = (DIST / "egern" / f"{name}.yaml").read_text(encoding="utf-8")

    for label, got in (("surge", surge), ("quantumultx", qx), ("clash", clash)):
        if not got:
            errs.append(f"{name}/{label}: 空的")
        if len(got) != len(set(got)):
            errs.append(f"{name}/{label}: 有重复行")
        by_kind = {}
        for item in got:
            by_kind.setdefault(item.split(",", 1)[0], []).append(item)
        for k, vals in by_kind.items():
            if vals != sorted(vals):
                errs.append(f"{name}/{label}: {k} 段未排序")
    if not (len(surge) == len(qx) == len(clash)):
        errs.append(f"{name}: 三端条目数不一致 surge={len(surge)} qx={len(qx)} clash={len(clash)}")
    if not re.search(r"(?m)^[a-z0-9_]+_set:$", egern):
        errs.append(f"{name}/egern: 没有 *_set: 键")


def main():
    if not DIST.exists():
        sys.exit("dist/ 不存在，先跑 build.py")
    names = sorted(p.stem for p in (DIST / "surge").glob("*.list"))
    errs = []
    for n in names:
        check(n, errs)
    if errs:
        print("产物校验失败：", file=sys.stderr)
        for e in errs:
            print("  ✗", e, file=sys.stderr)
        sys.exit(1)
    total = sum(len(entries(DIST / "surge" / f"{n}.list", r"^([A-Z0-9-]+,[^,]+(?:,no-resolve)?)$"))
                for n in names)
    print(f"产物校验通过：{len(names)} 个类目 / {total} 条规则 / 4 种格式一致")


if __name__ == "__main__":
    main()
