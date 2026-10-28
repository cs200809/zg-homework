#!/usr/bin/env python3
"""为 Android Flutter 工程补齐渠道（flavor）配置。

向 `android/app/build.gradle.kts` 的 `android { }` 块注入：

    flavorDimensions += "channel"
    productFlavors {
        create("dev") {
            dimension = "channel"
            applicationIdSuffix = ".dev"
            resValue("string", "app_name", "...")   // 让两个渠道可同时安装
        }
        create("prod") {
            dimension = "channel"
        }
    }

同时把渠道名写进 `dart-defines`，这样 AppConfig.flavor 能读到 FLAVOR，
不必每次手工传 --dart-define=FLAVOR=...（命令行传入时优先级更高，仍可覆盖）。

脚本幂等：已存在 flavorDimensions 时直接跳过。
"""

import argparse
import re
import shutil
import sys
from pathlib import Path

FLAVOR_BLOCK = '''
    // ---- 渠道配置（由 scripts/build.sh 生成）----
    flavorDimensions += "channel"
    productFlavors {
        create("dev") {
            dimension = "channel"
            applicationIdSuffix = ".dev"
            versionNameSuffix = "-dev"
            resValue("string", "app_name", "zg-tsp-dev")
        }
        create("prod") {
            dimension = "channel"
            versionNameSuffix = "-prod"
            resValue("string", "app_name", "zg-tsp")
        }
    }
'''

# AGP 9.x 把 resValue 收进了 buildFeatures 开关，默认关闭。
# 不开这个开关，构建时会报：
#   "Product Flavor dev contains custom resource values, but the feature is disabled."
BUILD_FEATURES_BLOCK = '''
    buildFeatures {
        // resValue("string", "app_name", ...) 需要显式开启（AGP 9.x 默认关闭）
        resValues = true
    }
'''


def ensure_manifest_label(manifest_path: Path) -> bool:
    """把 manifest 里硬编码的 android:label 改成 @string/app_name。

    `resValue("string", "app_name", ...)` 只生成资源，不会改 manifest；
    manifest 若仍写死标签（如 android:label="zg_tsp_android"），
    各渠道在桌面上就还是同一个名字，resValue 等于白写。
    """
    if not manifest_path.exists():
        return False

    text = manifest_path.read_text(encoding="utf-8")
    if 'android:label="@string/app_name"' in text:
        return False

    new_text, n = re.subn(
        r'android:label\s*=\s*"[^"]*"',
        'android:label="@string/app_name"',
        text,
        count=1,
    )
    if n == 0:
        return False

    backup = manifest_path.with_suffix(manifest_path.suffix + ".bak")
    if not backup.exists():
        shutil.copy2(manifest_path, backup)

    manifest_path.write_text(new_text, encoding="utf-8")
    return True


def ensure_build_features(text: str, indent: str) -> str:
    """确保 android { } 块里有 buildFeatures { resValues = true }。

    已有 buildFeatures 块 → 在块内插入一行；
    没有 → 在 flavorDimensions 之前新建一个块。
    """
    if re.search(r"resValues\s*=", text):
        return text

    m = re.search(r"\n([ \t]*)buildFeatures[ \t]*\{", text)
    if m:
        # 已有 buildFeatures：插到块内第一行
        inner_indent = indent + "    "
        return (
            text[: m.end()]
            + f"\n{inner_indent}resValues = true"
            + text[m.end() :]
        )

    # 没有 buildFeatures：放在 flavorDimensions 之前
    dim = re.search(r"\n([ \t]*)flavorDimensions", text)
    if not dim:
        return text
    lines = BUILD_FEATURES_BLOCK.strip("\n").split("\n")
    base = len(lines[0]) - len(lines[0].lstrip())
    block = "\n".join(
        (indent + line[base:]) if line.strip() else line for line in lines
    )
    return text[: dim.start()] + "\n" + block + text[dim.start() :]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gradle", required=True, help="android/app/build.gradle.kts 路径")
    ap.add_argument("--flavor", required=True, help="当前要打包的 flavor（仅用于日志）")
    args = ap.parse_args()

    path = Path(args.gradle)
    if not path.exists():
        print(f"找不到 {path}", file=sys.stderr)
        return 1

    text = path.read_text(encoding="utf-8")

    # android { } 块的缩进（productFlavors / buildFeatures 都要用）
    m_indent = re.search(r"\n([ \t]*)buildTypes[ \t]*\{", text)
    indent = m_indent.group(1) if m_indent else "    "

    if "flavorDimensions" in text:
        print("  productFlavors 已存在，跳过注入")
    else:
        # 备份：build.gradle.kts → build.gradle.kts.bak
        # （with_suffix 会把 ".kts" 当成一个后缀，直接用会得到
        #   build.gradle.gradle.kts.bak 这种重复扩展名的文件名）
        backup = path.with_name(path.name + ".bak")
        if not backup.exists():
            shutil.copy2(path, backup)

        # 注入点：defaultConfig 块之后、buildTypes 之前
        # 缩进只取水平空白（[ \t]），不能用 \s —— \s 会把换行也吃进来，
        # 捕获到 "\n    "，拼到每一行前面就会多出空行。
        m = m_indent
        if not m:
            print("未找到 buildTypes 块，无法确定注入位置", file=sys.stderr)
            return 1

        # 先按 4 空格基准去掉公共缩进，再按目标缩进整体加上。
        lines = FLAVOR_BLOCK.strip("\n").split("\n")
        base = len(lines[0]) - len(lines[0].lstrip())
        block = "\n".join(
            (indent + line[base:]) if line.strip() else line for line in lines
        )

        # m.start() 指向 buildTypes 前的那个换行，直接在那里插入即可，
        # 否则会多出一个空行
        text = text[: m.start()] + "\n" + block + text[m.start() :]
        path.write_text(text, encoding="utf-8")

        print(f"  已注入 productFlavors：{path}")
        print(f"  备份：{backup}")

    # AGP 9.x 默认关闭 resValues 开关，不开构建会失败：
    #   "Product Flavor dev contains custom resource values, but the feature is disabled."
    # 这一步与 flavor 是否已注入无关，因此放在 if/else 之外，保证幂等。
    text = path.read_text(encoding="utf-8")
    new_text = ensure_build_features(text, indent)
    if new_text != text:
        path.write_text(new_text, encoding="utf-8")
        print("  已开启 buildFeatures.resValues（AGP 9.x 默认关闭）")

    # manifest 标签改为引用 @string/app_name，让 resValue 真正生效
    manifest = path.parent / "src" / "main" / "AndroidManifest.xml"
    if ensure_manifest_label(manifest):
        print(f"  manifest 标签已改为 @string/app_name：{manifest}")
    else:
        print("  manifest 标签已是 @string/app_name（或无需改动）")

    return 0


if __name__ == "__main__":
    sys.exit(main())
