#!/usr/bin/env python3
"""make_icon_json.py — 生成图标引用清单（Surge / 代理工具用的 icons JSON）。

输出格式（每个图标一行，name + url）：

  {
    "name": "Tasks-Icons",
    "description": "By Q",
    "icons": [
      { "name": "Anthropic", "url": "https://raw.githubusercontent.com/kakbga/Icon-backup/main/Oasisic/icons/AI/Anthropic/Anthropic.png" },
      ...
    ]
  }

扫描规则：--dir 下**所有** PNG 都算图标，名字取文件名（不含扩展名），
不要求分类目录、也不要求文件名和文件夹同名。三种结构都支持：

  icons/Anthropic.png                     扁平：一张图一个文件
  icons/Anthropic/Anthropic.png           只有品牌层
  icons/AI/Anthropic/Anthropic.png        分类 + 品牌

URL 由 <base> + <--path-prefix> + 相对路径 拼成，--path-prefix 默认取 --dir 的
文件夹名（所以 icons/Anthropic.png -> <base>/icons/Anthropic.png）。

用法:
  py make_icon_json.py                                 生成 icons.json
  py make_icon_json.py --dir icons --out icons.json    指定目录和输出
  py make_icon_json.py --out my-icons.json             指定输出文件名
  py make_icon_json.py --base https://raw.githubusercontent.com/你/仓库/main/Oasisic
  py make_icon_json.py --path-prefix icons             URL 第一段固定成 icons
  py make_icon_json.py --path-prefix ""                URL 里不带这一层
  py make_icon_json.py --name "Tasks-Icons" --description "By Q"
  py make_icon_json.py --brands config/brands.json     顺带和 SSOT 双向核对
  py make_icon_json.py --check                         只核对，不写文件（不一致则 exit 1）

依赖: 无（纯标准库）
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DEFAULT_BASE = "https://raw.githubusercontent.com/kakbga/Icon-backup/main/Lige"

try:  # Windows 控制台默认 GBK，中文可能编码失败；统一改成 UTF-8
    stdout_reconfigure = getattr(sys.stdout, "reconfigure", None)
    stderr_reconfigure = getattr(sys.stderr, "reconfigure", None)
    if callable(stdout_reconfigure):
        stdout_reconfigure(encoding="utf-8")
    if callable(stderr_reconfigure):
        stderr_reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass


def scan_icons(root: Path) -> tuple[list[dict], list[str]]:
    """收集 --dir 下全部 PNG（任意层级），返回 (条目, 警告)。"""
    entries, warnings, seen = [], [], {}
    for p in sorted(root.rglob("*.png")):
        rel_root = p.relative_to(root)
        rel_top = p.relative_to(root.parent).as_posix()  # icons/Anthropic.png
        name = p.stem
        if name in seen:
            warnings.append("同名图标，已跳过后者: %s（保留 %s）" % (rel_top, seen[name]))
            continue
        seen[name] = rel_top
        entries.append({
            "name": name,
            "category": rel_root.parts[0] if len(rel_root.parts) > 1 else "",
            "rel": rel_root.as_posix(),
            "icon_path": rel_top,
        })
    entries.sort(key=lambda e: (e["category"].lower(), e["name"].lower(), e["name"]))
    return entries, warnings


def render(entries: list[dict], base: str, prefix: str, name: str, description: str) -> str:
    """按示例格式拼 JSON 文本（每个图标一行）。"""
    base = base.rstrip("/")

    def q(s: str) -> str:
        return json.dumps(s, ensure_ascii=False)

    lines = [
        "{",
        '  "name": %s,' % q(name),
        '  "description": %s,' % q(description),
        '  "icons": [',
    ]
    last = len(entries) - 1
    for i, e in enumerate(entries):
        path = "%s/%s" % (prefix, e["rel"]) if prefix else e["rel"]
        url = "%s/%s" % (base, path.lstrip("/"))
        comma = "," if i < last else ""
        lines.append('    { "name": %s, "url": %s }%s' % (q(e["name"]), q(url), comma))
    lines += ["  ]", "}"]
    return "\n".join(lines) + "\n"


def check_against_brands(entries: list[dict], brands_path: Path) -> list[str]:
    """和 brands.json（SSOT）双向核对，返回问题列表。"""
    doc = json.loads(brands_path.read_text(encoding="utf-8"))
    brands = doc.get("brands", []) if isinstance(doc, dict) else []
    ssot = {b["id"]: b for b in brands if b.get("id")}
    have = {e["name"]: e["icon_path"] for e in entries}
    problems = []
    for bid, b in ssot.items():
        want = b.get("icon_path")
        if not want:
            continue  # pending 无实物资产的条目跳过
        if bid not in have:
            problems.append("brands.json 有、磁盘缺图标: %s (%s)" % (bid, want))
        elif have[bid] != want:
            problems.append("路径不一致: %s 磁盘=%s SSOT=%s" % (bid, have[bid], want))
    for name, path in have.items():
        if name not in ssot:
            problems.append("磁盘有、brands.json 无登记: %s (%s)" % (name, path))
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description="生成图标引用 JSON（name + url 每行一条）")
    ap.add_argument("--dir", default="icons", help="图标根目录（默认 icons）")
    ap.add_argument("--out", default="icons.json", help="输出文件（默认 icons.json）")
    ap.add_argument("--base", default=DEFAULT_BASE, help="url 前缀（默认 %s）" % DEFAULT_BASE)
    ap.add_argument("--path-prefix", default=None,
                    help="URL 里的第一段目录名（默认取 --dir 的文件夹名；传空字符串则不带这一层）")
    ap.add_argument("--name", default="Tasks-Icons", help='顶层 name 字段（默认 "Tasks-Icons"）')
    ap.add_argument("--description", default="By Q", help='顶部 description 字段（默认 "By Q"）')
    ap.add_argument("--brands", default=None, help="可选：config/brands.json，用于双向核对")
    ap.add_argument("--check", action="store_true", help="只核对不写文件（不一致 exit 1）")
    args = ap.parse_args()

    root = Path(args.dir)
    if not root.is_dir():
        ap.error("图标目录不存在: %s" % root)

    entries, warnings = scan_icons(root)
    if not entries:
        print("没有找到 PNG: %s" % root)
        return 1
    for w in warnings:
        print("  ! " + w)

    cats = sorted({e["category"] for e in entries if e["category"]})
    prefix = root.name if args.path_prefix is None else args.path_prefix
    print("扫描到 %d 个图标 | %s | URL 前缀: %s"
          % (len(entries),
             "扁平结构" if not cats else "%d 个分类" % len(cats),
             "(无)" if not prefix else prefix))

    problems = []
    if args.brands:
        bp = Path(args.brands)
        if not bp.is_file():
            ap.error("brands.json 不存在: %s" % bp)
        problems = check_against_brands(entries, bp)
        if problems:
            print("与 %s 核对发现 %d 处问题:" % (bp, len(problems)))
            for msg in problems:
                print("   - %s" % msg)
        else:
            print("与 %s 核对一致" % bp)

    if args.check:
        return 1 if problems else 0

    text = render(entries, args.base, prefix, args.name, args.description)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print("已生成 %s（%d 条，%.1f KB）" % (out, len(entries), len(text.encode("utf-8")) / 1024))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
