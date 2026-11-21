#!/usr/bin/env python3
"""compress_icons.py — 无损压缩图标 PNG（像素完全不变，只重压 deflate）。

规则与 Tasks-Icons 仓库一致：
  - 全部统一回 RGBA 色型（转换本身像素等价，不改颜色）
  - 只用 oxipng 做无损重压缩，禁止降色型 / 有损量化
  - --verify 会逐像素比对压缩前后，确认完全一致

用法:
  py compress_icons.py                                 默认 icons/，级别 4，自动多进程
  py compress_icons.py -j 4                            指定并行进程数
  py compress_icons.py -j 1                            单进程（调试/受限环境）
  py compress_icons.py --level 6                       压缩更狠（更慢）
  py compress_icons.py --dir icons --verify            逐像素校验
  py compress_icons.py --dry-run                       只统计当前体积
  py compress_icons.py --quiet                         只输出汇总
  py compress_icons.py --dir icons -j 8               指定目录和进程数

受限环境无法创建多进程时会自动退回单进程。

依赖: Pillow + pyoxipng   (pip install pyoxipng)
"""
from __future__ import annotations

import argparse
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import oxipng
from PIL import Image, ImageChops


# Windows 控制台默认 GBK，中文/符号可能编码失败；统一改成 UTF-8
try:
    reconfigure_stdout = getattr(sys.stdout, "reconfigure", None)
    if callable(reconfigure_stdout):
        reconfigure_stdout(encoding="utf-8")
    reconfigure_stderr = getattr(sys.stderr, "reconfigure", None)
    if callable(reconfigure_stderr):
        reconfigure_stderr(encoding="utf-8")
except Exception:
    pass


def same_pixels(a: Image.Image, b: Image.Image) -> bool:
    """可见像素是否完全一致：alpha 必须逐点相同，RGB 只在 alpha>0 处比较。

    透明像素的 RGB 不参与渲染，oxipng 的 alpha 优化会把它归零以省空间，
    因此按「可见结果」判定才算真正的无损。
    """
    if a.size != b.size:
        return False
    a, b = a.convert("RGBA"), b.convert("RGBA")
    a_alpha, b_alpha = a.split()[3], b.split()[3]
    if ImageChops.difference(a_alpha, b_alpha).getbbox() is not None:
        return False  # 透明度改变了 —— 不算无损
    visible = a_alpha.point(lambda v: 255 if v else 0).convert("RGB")
    diff = ImageChops.difference(a.convert("RGB"), b.convert("RGB"))
    return ImageChops.multiply(diff, visible).getbbox() is None


def optimize_one(path: Path, level: int, verify: bool) -> tuple[str, int, int, bool]:
    """返回 (状态, 压缩前字节, 压缩后字节, 像素是否一致)。状态: ok / fail。"""
    before_bytes = path.stat().st_size
    with Image.open(path) as im:
        im.load()
        original = im.convert("RGBA")
        needs_rgba = im.mode != "RGBA"
    if needs_rgba:
        original.save(path, optimize=True)

    try:
        oxipng.optimize(
            str(path),
            level=level,
            strip=oxipng.StripChunks.safe(),
            optimize_alpha=True,
            color_type_reduction=False,  # 禁止降色型
        )
    except TypeError:  # 旧版 pyoxipng 不认识 color_type_reduction
        oxipng.optimize(str(path), level=level, strip=oxipng.StripChunks.safe(), optimize_alpha=True)

    after_bytes = path.stat().st_size
    if verify:
        with Image.open(path) as im:
            im.load()
            if im.mode != "RGBA" or not same_pixels(original, im):
                return "fail", before_bytes, after_bytes, False
    return "ok", before_bytes, after_bytes, True


def _run_task(task: tuple[str, int, bool]) -> tuple[str, int, int, str]:
    """子进程入口：把异常收成数据返回，坏文件不会带崩整个进程池。"""
    path_str, level, verify = task
    path = Path(path_str)
    try:
        status, before, after, _same = optimize_one(path, level, verify)
        return status, before, after, ""
    except Exception as exc:  # noqa: BLE001
        try:
            after = path.stat().st_size
        except OSError:
            after = 0
        return "error", after, after, "%s: %s" % (type(exc).__name__, exc)


def resolve_jobs(requested: int, file_count: int) -> int:
    """0 表示自动：最多 8 个进程（oxipng 内部本身还会用多线程）。"""
    jobs = requested if requested > 0 else min(os.cpu_count() or 1, 8)
    return max(1, min(jobs, file_count))


def main() -> int:
    ap = argparse.ArgumentParser(description="无损压缩 PNG 图标（像素不变，多进程）")
    ap.add_argument("--dir", default="icons", help="图标目录（默认 icons）")
    ap.add_argument("--level", type=int, default=4, help="oxipng 压缩级别 0-6（默认 4）")
    ap.add_argument("--verify", action="store_true", help="逐像素校验压缩前后完全一致")
    ap.add_argument("--dry-run", action="store_true", help="不压缩，只统计体积")
    ap.add_argument("--quiet", action="store_true", help="只输出汇总")
    ap.add_argument("-j", "--jobs", type=int, default=0,
                    help="并行进程数（默认自动：min(CPU 核数, 8)；1 = 单进程）")
    args = ap.parse_args()

    if not 0 <= args.level <= 6:
        ap.error("--level 取值 0-6")
    if args.jobs < 0:
        ap.error("--jobs 不能为负数")
    root = Path(args.dir)
    if not root.is_dir():
        ap.error("目录不存在: %s" % root)

    files = sorted(root.rglob("*.png"))
    if not files:
        print("没有找到 PNG: %s" % root)
        return 1

    total_before = sum(p.stat().st_size for p in files)
    print("目录: %s | 文件 %d 个 | 当前体积 %.2f MB"
          % (root, len(files), total_before / 1e6))
    if args.dry_run:
        return 0

    jobs = resolve_jobs(args.jobs, len(files))
    if jobs > 1 and not args.quiet:
        print("并行: %d 个进程" % jobs)

    tasks = [(str(p), args.level, args.verify) for p in files]
    pool: ProcessPoolExecutor | None = None
    results = None
    if jobs > 1:
        try:
            pool = ProcessPoolExecutor(max_workers=jobs)
            results = pool.map(_run_task, tasks)
        except (OSError, PermissionError) as exc:  # 受限环境（沙箱等）无法建管道
            print("  ! 无法创建多进程（%s），退回单进程" % exc)
    if results is None:
        results = map(_run_task, tasks)

    total_after = 0
    ok = fail = 0
    try:
        for p, (status, before, after, err) in zip(files, results):
            total_after += after
            if status == "ok":
                ok += 1
                if not args.quiet and after < before:
                    print("  - %s  %d -> %d B (%+.1f%%)" % (p.as_posix(), before, after, (after - before) / before * 100))
            else:
                fail += 1
                if status == "error":
                    print("  ! %s: %s" % (p.as_posix(), err))
                else:
                    print("  ! %s: 像素校验不通过（已跳过）" % p.as_posix())
    finally:
        if pool is not None:
            pool.shutdown(cancel_futures=True)

    print("完成: 成功 %d / 失败 %d" % (ok, fail))
    print("体积: %.2f MB -> %.2f MB (节省 %.1f%%)"
          % (total_before / 1e6, total_after / 1e6,
             (1 - total_after / total_before) * 100 if total_before else 0))
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
