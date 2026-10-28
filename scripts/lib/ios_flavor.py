#!/usr/bin/env python3
"""为 iOS Flutter 工程补齐渠道（flavor）配置。

Flutter 的匹配规则（packages/flutter_tools/lib/src/ios/xcodeproj.dart）：

    scheme 名            = flavor 首字母大写           dev  -> Dev
    build configuration  = <基础配置>-<scheme>         Release-Dev / Release-Prod

`flutter build ipa --flavor dev` 会先按 scheme 找 Scheme，再按
`<基础配置>-<scheme>` 找 XCBuildConfiguration，两者缺一不可。

因此本脚本做三件事：
  1. 在 pbxproj 中新增 XCBuildConfiguration（Debug-Dev / Release-Dev / Profile-Dev）
  2. 在对应 XCConfigurationList 中登记这些配置
  3. 生成 xcshareddata/xcschemes/<Scheme>.xcscheme

生成的配置以现有的 Debug/Release/Profile 为模板，保证与工程一致。
"""

import argparse
import re
import shutil
import sys
from pathlib import Path

# pbxproj 里的对象 ID 为 24 位十六进制。这里按固定前缀生成，
# 保证同一 flavor 反复执行得到相同 ID（幂等）。
ID_PREFIX = "ZGTSPFLV"
ID_FLAVOR = "0000000000000000000001"  # 会被 flavor 派生的十六进制替换
ID_LIST = "0000000000000000000002"


def make_id(kind: str, flavor: str) -> str:
    """生成稳定且不与既有 ID 冲突的 24 位十六进制 ID。"""
    digest = int(hashlib_sha1(f"{kind}:{flavor}".encode()), 16)
    return f"{ID_PREFIX}{kind}{digest:016X}"[-24:]


def hashlib_sha1(data: bytes) -> str:
    import hashlib

    return hashlib.sha1(data).hexdigest()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def ensure_xcconfig_ref(pbxproj: str, xcconfig_name: str) -> tuple[str, str]:
    """确保 pbxproj 里有该 xcconfig 的 PBXFileReference，返回 (pbxproj, file_ref_id)。"""
    # 已存在引用？
    m = re.search(
        r"([0-9A-F]{24}) /\* " + re.escape(xcconfig_name) + r" \*/ = \{isa = PBXFileReference;",
        pbxproj,
    )
    if m:
        return pbxproj, m.group(1)

    file_ref_id = make_id("FR", xcconfig_name)
    ref_block = (
        f'\t\t{file_ref_id} /* {xcconfig_name} */ = {{isa = PBXFileReference; '
        f'lastKnownFileType = text.xcconfig; name = {xcconfig_name}; '
        f'path = Flutter/{xcconfig_name}; sourceTree = "<group>"; }};\n'
    )
    # 插入到 PBXFileReference section 的末尾
    pbxproj = insert_in_section(pbxproj, "PBXFileReference", ref_block)

    # 在 Flutter group 里登记该文件
    group_anchor = re.search(
        r"([0-9A-F]{24}) /\* Debug\.xcconfig \*/,\n", pbxproj
    )
    if group_anchor:
        pbxproj = pbxproj.replace(
            group_anchor.group(0),
            group_anchor.group(0) + f"\t\t\t\t{file_ref_id} /* {xcconfig_name} */,\n",
            1,
        )

    return pbxproj, file_ref_id


def insert_in_section(pbxproj: str, section: str, block: str) -> str:
    """在 `/* Begin <section> section */` 与 `/* End <section> section */` 之间插入。

    注意是在 Begin 标记之后**插入**，而不是把整个 section 的内容替换掉：
    若写成 pbxproj[:i] + block + pbxproj[j:]，section 里原有的条目
    （如 XCBuildConfiguration 段的 Debug/Release/Profile）会被整段丢弃，
    工程随之损坏。
    """
    begin = f"/* Begin {section} section */"
    end = f"/* End {section} section */"
    if begin not in pbxproj or end not in pbxproj:
        return pbxproj
    i = pbxproj.index(begin) + len(begin)
    return pbxproj[:i] + "\n" + block + pbxproj[i:]


def extract_config_block(pbxproj: str, config_name: str) -> str | None:
    """取出 Runner target 的既有 XCBuildConfiguration 的 buildSettings 作为模板。

    注意：pbxproj 里 Debug/Release 这类名字在 Runner、RunnerTests、
    PBXProject 三个 target 下各有一份，名字完全相同。
    必须先定位到 Runner target 的 XCConfigurationList，
    再顺着它引用的配置 ID 取模板，否则会取到 RunnerTests 的
    （带 TEST_HOST / BUNDLE_LOADER 等字段，套到 Runner 上会构建失败）。
    """
    # 1) 定位 Runner target 的 configuration list
    list_pattern = re.compile(
        r"97C147051CF9000F007C117D /\* Build configuration list for "
        r'PBXNativeTarget "Runner" \*/ = \{\n'
        r"\t\t\tisa = XCConfigurationList;\n"
        r"\t\t\tbuildConfigurations = \(\n(.*?)\t\t\t\);",
        re.DOTALL,
    )
    lm = list_pattern.search(pbxproj)
    if not lm:
        return None

    # 2) 收集该 list 引用的配置 ID
    conf_ids = re.findall(r"([0-9A-F]{24}) /\* " + re.escape(config_name) + r" \*/", lm.group(1))
    if not conf_ids:
        return None

    # 3) 按 ID 取对应的配置块（ID 唯一，天然排除其它 target）
    for conf_id in conf_ids:
        block_pattern = re.compile(
            r"(" + conf_id + r" /\* " + re.escape(config_name) + r" \*/ = \{\n"
            r"\t\t\tisa = XCBuildConfiguration;\n"
            r"(?:\t\t\tbaseConfigurationReference = ([0-9A-F]{24}) /\* [^*]+ \*/;\n)?"
            r"\t\t\tbuildSettings = \{\n(.*?)\n\t\t\t\};\n"
            r"\t\t\tname = " + re.escape(config_name) + r";\n"
            r"\t\t\};)",
            re.DOTALL,
        )
        bm = block_pattern.search(pbxproj)
        if bm:
            # group(2) 是可选的 baseConfigurationReference，
            # group(3) 才是 buildSettings 正文
            return bm.group(3)
    return None


def add_build_configurations(
    pbxproj: str, flavor: str, scheme: str, xcconfig_ref: str | None, xcconfig_name: str
) -> str:
    """为 Runner target 与 RunnerTests target 补齐带 flavor 的构建配置。"""
    debug_body = extract_config_block(pbxproj, "Debug")
    release_body = extract_config_block(pbxproj, "Release")
    if debug_body is None or release_body is None:
        raise SystemExit("无法在 pbxproj 中定位 Debug/Release 构建配置模板")

    # 三个基础配置 × flavor
    # 每个模式对应一份模板：Debug 模板用于 Debug-<Scheme>，
    # Release / Profile 模板用于 Release-<Scheme> / Profile-<Scheme>。
    variants = [
        ("Debug", debug_body),
        ("Release", release_body),
        ("Profile", release_body),
    ]

    new_blocks = []
    new_ids = []
    for mode, body in variants:
        conf_name = f"{mode}-{scheme}"
        # 幂等：配置块已存在就跳过
        if re.search(r"/\* " + re.escape(conf_name) + r" \*/ = \{", pbxproj):
            continue
        conf_id = make_id("BC", f"{flavor}:{conf_name}")
        new_ids.append((conf_name, conf_id))

        # 渠道 xcconfig 作为 baseConfiguration，
        # 其内部 include 了 Generated.xcconfig
        #
        # 注意注释里的文件名必须与 PBXFileReference 中的完全一致
        # （Dev.xcconfig，而非 dev.xcconfig）——大小写不符时
        # Xcode 会因为找不到该 base configuration 而构建失败。
        base_ref = (
            f"\t\t\tbaseConfigurationReference = {xcconfig_ref} /* {xcconfig_name} */;\n"
            if xcconfig_ref
            else ""
        )
        block = (
            f"\t\t{conf_id} /* {conf_name} */ = {{\n"
            f"\t\t\tisa = XCBuildConfiguration;\n"
            f"{base_ref}"
            f"\t\t\tbuildSettings = {{\n{body}\n\t\t\t}};\n"
            f"\t\t\tname = {conf_name};\n"
            f"\t\t}};\n"
        )
        new_blocks.append(block)

    if not new_blocks:
        return pbxproj

    pbxproj = insert_in_section(
        pbxproj, "XCBuildConfiguration", "".join(new_blocks)
    )

    # 登记到 Runner target 的 configuration list（97C147051CF9000F007C117D）
    runner_list = "97C147051CF9000F007C117D"
    entries = "".join(
        f"\t\t\t\t{conf_id} /* {conf_name} */,\n" for conf_name, conf_id in new_ids
    )
    list_pattern = re.compile(
        r"(" + runner_list + r" /\* Build configuration list for PBXNativeTarget \"Runner\" \*/ = \{\n"
        r"\t\t\tisa = XCConfigurationList;\n"
        r"\t\t\tbuildConfigurations = \(\n)(.*?)(\t\t\t\);)",
        re.DOTALL,
    )
    m = list_pattern.search(pbxproj)
    if not m:
        raise SystemExit("无法定位 Runner target 的 XCConfigurationList")

    # 幂等：list 里已登记过的配置 ID 不重复添加
    existing_list = m.group(2)
    to_add = "".join(
        f"\t\t\t\t{conf_id} /* {conf_name} */,\n"
        for conf_name, conf_id in new_ids
        if conf_id not in existing_list
    )
    if to_add:
        pbxproj = pbxproj[: m.end(2)] + to_add + pbxproj[m.end(2) :]

    return pbxproj


SCHEME_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<Scheme
   LastUpgradeVersion = "1510"
   version = "1.3">
   <BuildAction
      parallelizeBuildables = "YES"
      buildImplicitDependencies = "YES">
      <PreActions>
         <ExecutionAction
            ActionType = "Xcode.IDEStandardExecutionActionsCore.ExecutionActionType.ShellScriptAction">
            <ActionContent
               title = "Run Prepare Flutter Framework Script"
               scriptText = "/bin/sh &quot;$FLUTTER_ROOT/packages/flutter_tools/bin/xcode_backend.sh&quot; prepare&#10;">
               <EnvironmentBuildable>
                  <BuildableReference
                     BuildableIdentifier = "primary"
                     BlueprintIdentifier = "97C146ED1CF9000F007C117D"
                     BuildableName = "Runner.app"
                     BlueprintName = "Runner"
                     ReferencedContainer = "container:Runner.xcodeproj">
                  </BuildableReference>
               </EnvironmentBuildable>
            </ActionContent>
         </ExecutionAction>
      </PreActions>
      <BuildActionEntries>
         <BuildActionEntry
            buildForTesting = "YES"
            buildForRunning = "YES"
            buildForProfiling = "YES"
            buildForArchiving = "YES"
            buildForAnalyzing = "YES">
            <BuildableReference
               BuildableIdentifier = "primary"
               BlueprintIdentifier = "97C146ED1CF9000F007C117D"
               BuildableName = "Runner.app"
               BlueprintName = "Runner"
               ReferencedContainer = "container:Runner.xcodeproj">
            </BuildableReference>
         </BuildActionEntry>
      </BuildActionEntries>
   </BuildAction>
   <TestAction
      buildConfiguration = "{debug_conf}"
      selectedDebuggerIdentifier = "Xcode.DebuggerFoundation.Debugger.LLDB"
      selectedLauncherIdentifier = "Xcode.DebuggerFoundation.Launcher.LLDB"
      customLLDBInitFile = "$(SRCROOT)/Flutter/ephemeral/flutter_lldbinit"
      shouldUseLaunchSchemeArgsEnv = "YES">
      <MacroExpansion>
         <BuildableReference
            BuildableIdentifier = "primary"
            BlueprintIdentifier = "97C146ED1CF9000F007C117D"
            BuildableName = "Runner.app"
            BlueprintName = "Runner"
            ReferencedContainer = "container:Runner.xcodeproj">
         </BuildableReference>
      </MacroExpansion>
      <Testables>
         <TestableReference
            skipped = "NO"
            parallelizable = "YES">
            <BuildableReference
               BuildableIdentifier = "primary"
               BlueprintIdentifier = "331C8080294A63A400263BE5"
               BuildableName = "RunnerTests.xctest"
               BlueprintName = "RunnerTests"
               ReferencedContainer = "container:Runner.xcodeproj">
            </BuildableReference>
         </TestableReference>
      </Testables>
   </TestAction>
   <LaunchAction
      buildConfiguration = "{debug_conf}"
      selectedDebuggerIdentifier = "Xcode.DebuggerFoundation.Debugger.LLDB"
      selectedLauncherIdentifier = "Xcode.DebuggerFoundation.Launcher.LLDB"
      customLLDBInitFile = "$(SRCROOT)/Flutter/ephemeral/flutter_lldbinit"
      launchStyle = "0"
      useCustomWorkingDirectory = "NO"
      ignoresPersistentStateOnLaunch = "NO"
      debugDocumentVersioning = "YES"
      debugServiceExtension = "internal"
      enableGPUValidationMode = "1"
      allowLocationSimulation = "YES">
      <BuildableProductRunnable
         runnableDebuggingMode = "0">
         <BuildableReference
            BuildableIdentifier = "primary"
            BlueprintIdentifier = "97C146ED1CF9000F007C117D"
            BuildableName = "Runner.app"
            BlueprintName = "Runner"
            ReferencedContainer = "container:Runner.xcodeproj">
         </BuildableReference>
      </BuildableProductRunnable>
   </LaunchAction>
   <ProfileAction
      buildConfiguration = "{profile_conf}"
      selectedDebuggerIdentifier = "Xcode.DebuggerFoundation.Debugger.LLDB"
      selectedLauncherIdentifier = "Xcode.DebuggerFoundation.Launcher.LLDB"
      shouldUseLaunchSchemeArgsEnv = "YES"
      savedToolIdentifier = ""
      useCustomWorkingDirectory = "NO"
      debugDocumentVersioning = "YES">
      <BuildableProductRunnable
         runnableDebuggingMode = "0">
         <BuildableReference
            BuildableIdentifier = "primary"
            BlueprintIdentifier = "97C146ED1CF9000F007C117D"
            BuildableName = "Runner.app"
            BlueprintName = "Runner"
            ReferencedContainer = "container:Runner.xcodeproj">
         </BuildableReference>
      </BuildableProductRunnable>
   </ProfileAction>
   <AnalyzeAction
      buildConfiguration = "{debug_conf}">
   </AnalyzeAction>
   <ArchiveAction
      buildConfiguration = "{release_conf}"
      revealArchiveInOrganizer = "YES">
   </ArchiveAction>
</Scheme>
"""


def write_scheme(
    scheme_dir: Path, scheme: str, debug_conf: str, release_conf: str, profile_conf: str
) -> Path:
    """生成渠道 Scheme。

    文件名必须是 `<scheme>.xcscheme`（如 Dev.xcscheme），不能是
    `Runner-<scheme>.xcscheme`：Scheme 的 XML 里没有 name 属性，
    Xcode/xcodebuild 用**文件名**作为 scheme 名，Flutter 期望的正是
    title-case 后的 flavor 名（dev → Dev）。叫 Runner-Dev 的话，
    `flutter build ipa --flavor dev` 会因找不到名为 Dev 的 scheme 而报错：

        The Xcode project defines schemes: Runner, Runner-Dev
        You must specify a --flavor option to select one of the available schemes.
    """
    scheme_dir.mkdir(parents=True, exist_ok=True)
    path = scheme_dir / f"{scheme}.xcscheme"
    # 清理早期版本生成的 Runner-<scheme>.xcscheme，避免留下多余的 scheme
    stale = scheme_dir / f"Runner-{scheme}.xcscheme"
    if stale.exists() and stale != path:
        stale.unlink()
    path.write_text(
        SCHEME_TEMPLATE.format(
            debug_conf=debug_conf,
            release_conf=release_conf,
            profile_conf=profile_conf,
        ),
        encoding="utf-8",
    )
    return path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True, help="project.pbxproj 路径")
    ap.add_argument("--xcconfig", required=True, help="渠道 xcconfig 文件名，如 Dev.xcconfig")
    ap.add_argument("--flavor", required=True, help="flavor 名，如 dev")
    ap.add_argument("--scheme", required=True, help="scheme 名，如 Dev")
    args = ap.parse_args()

    pbx_path = Path(args.project)
    if not pbx_path.exists():
        print(f"找不到 {pbx_path}", file=sys.stderr)
        return 1

    pbxproj = read_text(pbx_path)

    # 备份，便于回滚手工改动
    backup = pbx_path.with_suffix(".pbxproj.bak")
    if not backup.exists():
        shutil.copy2(pbx_path, backup)

    pbxproj, ref_id = ensure_xcconfig_ref(pbxproj, args.xcconfig)
    pbxproj = add_build_configurations(
        pbxproj, args.flavor, args.scheme, ref_id, args.xcconfig
    )
    write_text(pbx_path, pbxproj)

    scheme_path = write_scheme(
        pbx_path.parent / "xcshareddata" / "xcschemes",
        args.scheme,
        debug_conf=f"Debug-{args.scheme}",
        release_conf=f"Release-{args.scheme}",
        profile_conf=f"Profile-{args.scheme}",
    )

    print(f"  pbxproj 已更新：{pbx_path}")
    print(f"  Scheme 已生成：{scheme_path}")
    print(f"  备份：{backup}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
