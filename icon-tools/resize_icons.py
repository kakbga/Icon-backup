#!/usr/bin/env python3
"""resize_icons.py — 批量处理图标尺寸（边长自定义 + 圆角方形遮罩）。

默认把 --dir 下所有 PNG 规整成 144x144 RGBA 圆角方形（圆角半径 = 边长 x 32/144 ≈ 22.2%）。
处理只做三步：补成正方形 -> LANCZOS 缩放到目标边长 -> alpha 乘以圆角遮罩。
圆角遮罩用 4x 超采样再缩小，边缘带抗锯齿；不抠图、不去白底、不改色、不做有损量化。
已经合规的文件会被跳过（幂等）。

用法:
  py resize_icons.py --report                         只看，不写盘
  py resize_icons.py --apply                          144x144 原地写回
  py resize_icons.py --size 180 --apply               自定义边长，圆角自动等比
  py resize_icons.py --size 256 --radius 48 --apply   自定义边长 + 自定义圆角
  py resize_icons.py --size 144 --no-mask --apply     只改尺寸，不加圆角
  py resize_icons.py --dir icons --out out --apply    输出到另一个目录（完整镜像，保留子目录结构）
  py resize_icons.py --apply --force                  强制重跑（即使看起来已合规）
  py resize_icons.py --quiet                          只输出汇总

--out 与 --dir 不同时会输出完整镜像：需要处理的重新渲染，已合规的原样复制。

依赖: Pillow
"""
from __future__ import annotations

import argparse
import os
import shutil
import statistics
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

DEFAULT_SIZE = 144
RADIUS_RATIO = 32 / 144  # 仓库规范：144px 时 r=32
MASK_SUPERSAMPLE = 4

try:  # Windows 控制台默认 GBK，中文/符号可能编码失败；统一改成 UTF-8
    reconfigure_stdout = getattr(sys.stdout, "reconfigure", None)
    if reconfigure_stdout is not None:
        reconfigure_stdout(encoding="utf-8")
    reconfigure_stderr = getattr(sys.stderr, "reconfigure", None)
    if reconfigure_stderr is not None:
        reconfigure_stderr(encoding="utf-8")
except Exception:  # noqa: BLE001  (老版本 Python / 输出被重定向时不处理)
    pass

LANCZOS = getattr(getattr(Image, "Resampling", Image), "LANCZOS")


def build_mask(size: int, radius: int) -> Image.Image:
    """圆角遮罩：内部 255，圆角外 0；先超采样再缩小，得到抗锯齿边缘。"""
    radius = max(0, min(radius, size // 2))
    if radius == 0:
        return Image.new("L", (size, size), 255)
    ss = MASK_SUPERSAMPLE if size <= 512 else 2
    big = size * ss
    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, big - 1, big - 1], radius=radius * ss, fill=255
    )
    return mask.resize((size, size), LANCZOS)


def default_radius(size: int) -> int:
    return max(0, min(size // 2, round(size * RADIUS_RATIO)))


def border_color(rgba: Image.Image):
    """最外一圈不透明像素的中位色，用于非正方形图标补边；透明底返回 None。

    只有最外圈几乎全是不透明像素时才认为原图有实色底（阈值 90%）：
    横版透明 wordmark 常有几个字形贴边，但通常铺不满整圈，避免把字形颜色当成底色。
    """
    w, h = rgba.size
    ring = [(x, 0) for x in range(w)] + [(x, h - 1) for x in range(w)]
    ring += [(0, y) for y in range(h)] + [(w - 1, y) for y in range(h)]
    opaque: list[tuple[int, int, int, int]] = []
    for x, y in ring:
        pixel = rgba.getpixel((x, y))
        if isinstance(pixel, tuple) and len(pixel) == 4:
            r, g, b, alpha = pixel
            pixel_rgba = (int(r), int(g), int(b), int(alpha))
            if pixel_rgba[3] > 128:
                opaque.append(pixel_rgba)
    if len(opaque) < len(ring) * 0.9:
        return None
    return tuple(int(statistics.median(c[i] for c in opaque)) for i in range(3))


def to_square(rgba: Image.Image) -> Image.Image:
    """非正方形 -> 居中补成正方形（能取到边框底色就填底色，否则填透明）。"""
    w, h = rgba.size
    if w == h:
        return rgba
    side = max(w, h)
    color = border_color(rgba)
    canvas = Image.new("RGBA", (side, side), (color + (255,)) if color else (0, 0, 0, 0))
    canvas.alpha_composite(rgba, ((side - w) // 2, (side - h) // 2))
    return canvas


def render(
    src: Image.Image, size: int, radius: int | None, mask: Image.Image | None = None
) -> Image.Image:
    """补正方形 -> 缩放 -> 圆角遮罩。radius=None 表示不加圆角。"""
    im = to_square(src.convert("RGBA"))
    if im.size != (size, size):
        im = im.resize((size, size), LANCZOS)
    if radius is None:
        return im
    if mask is None:
        mask = build_mask(size, radius)
    r, g, b, a = im.split()
    return Image.merge("RGBA", (r, g, b, ImageChops.multiply(a, mask)))


def outside_visible(im: Image.Image, mask: Image.Image) -> bool:
    """圆角遮罩之外是否还有可见 alpha（True = 不合规）。

    只看 mask == 0 的区域：抗锯齿遮罩在边缘有 1..254 的过渡值，
    这些位置本来就允许有 alpha。
    """
    outside = mask.point(lambda v: 255 if v == 0 else 0)
    return ImageChops.multiply(im.split()[3], outside).getbbox() is not None


def is_done(im: Image.Image, size: int, mask: Image.Image | None) -> bool:
    """True = 已符合目标，可跳过。"""
    if im.size != (size, size) or im.mode != "RGBA":
        return False
    if mask is None:
        return True
    if outside_visible(im, mask):
        return False
    # 旧版硬边遮罩：边缘 alpha 仍是 255，没有按抗锯齿遮罩衰减。
    # 需要重跑一次，否则换成抗锯齿遮罩后这些文件永远不会被更新。
    return ImageChops.subtract(im.split()[3], mask).getbbox() is None


def reason(im: Image.Image, size: int, mask: Image.Image | None) -> str:
    """不合规的原因（可读）。"""
    if im.size != (size, size):
        return "尺寸 %dx%d" % im.size
    if im.mode != "RGBA":
        return "模式 %s" % im.mode
    if mask is None:
        return "已合规"
    if outside_visible(im, mask):
        return "圆角外仍有可见像素"
    if ImageChops.subtract(im.split()[3], mask).getbbox() is not None:
        return "圆角边缘 alpha 未按遮罩衰减（旧版硬边遮罩？）"
    return "已合规"


def save_atomic(im: Image.Image, dst: Path) -> None:
    """先写同目录临时文件再原子替换，失败时不会留下半个 PNG。"""
    fd, tmp_name = tempfile.mkstemp(prefix=".icon-", suffix=".tmp", dir=str(dst.parent))
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        im.save(tmp, format="PNG", optimize=True)
        if dst.exists():
            try:
                shutil.copymode(dst, tmp)
            except OSError:
                pass
        os.replace(tmp, dst)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def copy_atomic(src: Path, dst: Path) -> None:
    """原样复制合规文件到 --out，先写临时文件再替换。"""
    fd, tmp_name = tempfile.mkstemp(prefix=".icon-", suffix=".tmp", dir=str(dst.parent))
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        shutil.copy2(src, tmp)
        os.replace(tmp, dst)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description="批量处理图标尺寸（自定义边长 + 圆角方形）")
    ap.add_argument("--dir", default="icons", help="源目录（默认 icons）")
    ap.add_argument("--out", default=None, help="输出目录（默认原地覆盖；不同时完整镜像并保留子目录结构）")
    ap.add_argument("--size", type=int, default=DEFAULT_SIZE, help="目标边长，正方形（默认 144）")
    ap.add_argument("--radius", type=int, default=None, help="圆角半径（默认按边长等比 size*32/144）")
    ap.add_argument("--no-mask", action="store_true", help="不加圆角遮罩，只缩放尺寸")
    ap.add_argument("--apply", action="store_true", help="真正写盘（不加则只报告）")
    ap.add_argument("--force", action="store_true", help="即使已合规也重新渲染")
    ap.add_argument("--report", action="store_true", help="逐条列出待处理文件及原因")
    ap.add_argument("--quiet", action="store_true", help="只输出汇总")
    args = ap.parse_args()

    if args.size < 8:
        ap.error("--size 太小，至少 8")
    if args.radius is not None:
        if args.no_mask:
            ap.error("--radius 不能与 --no-mask 同时使用")
        max_radius = args.size // 2
        if not 0 <= args.radius <= max_radius:
            ap.error("--radius 取值范围 0-%d" % max_radius)

    src_root = Path(args.dir)
    if not src_root.is_dir():
        ap.error("源目录不存在: %s" % src_root)
    out_root = Path(args.out) if args.out else src_root
    same_root = out_root.resolve() == src_root.resolve()
    if args.out and not same_root:
        rs, ro = src_root.resolve(), out_root.resolve()
        if ro in rs.parents:
            ap.error("--out 不能包含 --dir: %s" % out_root)
        if out_root.exists() and not out_root.is_dir():
            ap.error("--out 不是目录: %s" % out_root)

    files = sorted(src_root.rglob("*.png"))
    if args.out and not same_root:
        # 允许 --out 位于 --dir 内部，但必须把它排除在扫描之外，避免输出被当成输入。
        out_abs = out_root.resolve()
        files = [p for p in files if not _is_relative_to(p.resolve(), out_abs)]
    if not files:
        print("没有找到 PNG: %s" % src_root)
        return 1

    radius = None if args.no_mask else (args.radius if args.radius is not None else default_radius(args.size))
    mask = None if radius is None else build_mask(args.size, radius)

    todo = []
    scan_errors = {}
    for p in files:
        try:
            with Image.open(p) as im:
                im.load()
                if args.force or not is_done(im, args.size, mask):
                    todo.append(p)
        except Exception as exc:  # noqa: BLE001  坏文件不能让整批中断
            scan_errors[p] = exc
            todo.append(p)
    done = len(files) - len(todo)

    print("目标: %dx%d %s | 待处理 %d / 已合规 %d / 合计 %d"
          % (args.size, args.size, "无圆角" if radius is None else "r=%d" % radius,
             len(todo), done, len(files)))

    if args.report and not args.quiet:
        for p in todo:
            if p in scan_errors:
                print("   - %s | 无法读取: %s" % (p.as_posix(), scan_errors[p]))
                continue
            with Image.open(p) as im:
                im.load()
                print("   - %s  %dx%d %s | %s"
                      % (p.as_posix(), im.size[0], im.size[1], im.mode, reason(im, args.size, mask)))

    if not args.apply:
        if todo:
            print("（未写盘，加 --apply 才会处理）")
        return 1 if scan_errors else 0

    todo_set = set(todo)
    if same_root:
        work = [(p, True) for p in todo]
    else:
        # --out 是完整镜像：待处理的重渲染，已合规的原样复制。
        work = [(p, p in todo_set) for p in files]

    written = copied = 0
    failures = []
    for p, needs_render in work:
        try:
            dst = p if same_root else out_root / p.relative_to(src_root)
            dst.parent.mkdir(parents=True, exist_ok=True)
            if needs_render:
                with Image.open(p) as im:
                    im.load()
                    out = render(im, args.size, radius, mask)
                save_atomic(out, dst)
                written += 1
            else:
                copy_atomic(p, dst)
                copied += 1
        except Exception as exc:  # noqa: BLE001
            failures.append((p, exc))
            print("  ! %s: %s" % (p.as_posix(), exc))

    if failures:
        print("完成: 写入 %d 个，复制 %d 个，失败 %d 个 -> %s"
              % (written, copied, len(failures), out_root))
        return 1
    if not work:
        print("完成: 无需处理")
    else:
        print("完成: 写入 %d 个，复制 %d 个 -> %s" % (written, copied, out_root))
    return 0


if __name__ == "__main__":
    sys.exit(main())
