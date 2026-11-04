# 开发环境搭建指南

移动端打包（`scripts/build.sh ios|android`）所需的本机环境安装与排错。

**当前机器状态**（2026-10-28 实测）：Flutter 3.47.7 ✅ / Xcode 27.1 ✅ /
CocoaPods 1.17.0 ✅ / Android SDK ✅（Homebrew 路径，见 4.1）/ JDK 17.0.21 ✅。
iOS 与 Android 打包均已可执行。

---

## 1. 先看结论：缺什么

| 依赖          | 要求                   | 本机状态                        | 安装方式                                            |
|-------------|----------------------|-----------------------------|-------------------------------------------------|
| Flutter     | 3.47.7（stable）       | ✅ 已装 3.47.7                   | `brew install --cask flutter`                   |
| **Xcode**   | **15 或更高**（完整版）      | ✅ 已装 27.1                    | App Store 安装，见第 2 节                             |
| CocoaPods   | 1.15+                | ✅ 已装 1.17.0                   | `brew install cocoapods`（**不要用 `gem install`**） |
| Android SDK | API 36 + build-tools | ⚠️ 已装，但只有 API 35          | `sdkmanager "platforms;android-36"`            |
| JDK         | **17 或更高**           | ✅ 已装 17.0.21                  | `brew install openjdk@17`（可与 1.8 共存，见 4.3） |

> Android SDK 装在 Homebrew 路径 `/opt/homebrew/share/android-commandlinetools`，
> 不是 Android Studio 默认的 `~/Library/Android/sdk`。
> Flutter 3.47 默认 `compileSdk = 36`，本机目前只装了 `android-35`，
> 构建时 AGP 会尝试自动下载；离线环境需手动 `sdkmanager "platforms;android-36"`。

一键预检：

```bash
./scripts/build.sh ios dev --check        # iOS 环境预检
./scripts/build.sh android dev --check     # Android 环境预检
```

### 1.1 还需要你提供凭据的两项

工具链装齐后，**出正式包还差两个凭据**，二者都不入库、需本地配置：

| 凭据 | 位置 | 配置方式 | 缺失后果 |
|------|------|---------|---------|
| iOS 签名团队 | `DEVELOPMENT_TEAM` 环境变量 或 `project.pbxproj` | 见 5.3 | 渠道 ipa 无法签名 |
| Android 正式 keystore | `zg-tsp-android/android/key.properties` | 见第 6 节 | release 退回 debug 签名，不可上架 |

---

## 2. 安装完整 Xcode（最关键的一步）

### 2.1 为什么 Command Line Tools 不够

`xcode-select -p` 指向 `/Library/Developer/CommandLineTools` 时，
`xcodebuild` **不存在**——只有编译器，没有 iOS 模拟器、SDK、设备支持，
无法执行 `flutter build ipa`。

```console
$ xcodebuild -version
xcode-select: error: tool 'xcodebuild' requires Xcode,
but active developer directory '/Library/Developer/CommandLineTools'
is a command line tools instance
```

### 2.2 安装步骤

**方式 A：App Store（推荐）**

1. 打开 App Store，搜索并安装 **Xcode**（Apple 官方，免费）
2. 首次启动 Xcode → 同意许可协议 → 等待「Installing additional
   components」组件安装完成（下载约 10 GB，视网速 10–40 分钟）
3. 安装完**必须**执行下面两条命令：

```bash
# 1) 把 developer 目录指向完整 Xcode
sudo xcode-select -s /Applications/Xcode.app/Contents/Developer

# 2) 初始化 Xcode 组件（首次必需，否则模拟器与设备支持不可用）
sudo xcodebuild -runFirstLaunch
```

> 第 2 步若跳过，`flutter doctor` 会报
> 「Xcode installation is incomplete」，`flutter run` 也可能起不来模拟器。

**方式 B：命令行下载（无需 App Store 账号，适合 CI）**

```bash
# 从 Apple 开发者下载页获取 xcode_*.xip（约 10 GB）
# https://developer.apple.com/download/all/

xip -x ~/Downloads/Xcode_16.xip
sudo mv Xcode.app /Applications/
sudo xcode-select -s /Applications/Xcode.app/Contents/Developer
sudo xcodebuild -runFirstLaunch
```

**方式 C：Homebrew Cask**

```bash
brew install --cask xcode
# cask 不会自动切 developer 目录，仍需手动执行上面两条 sudo 命令
```

### 2.3 验证

```bash
$ xcode-select -p
/Applications/Xcode.app/Contents/Developer        # ✅ 不再是 CommandLineTools

$ xcodebuild -version
Xcode 16.2                                    # ✅ 需 ≥ 15
Build version 16C5032a

$ flutter doctor
[✓] Xcode - develop for iOS and macOS
```

### 2.4 磁盘空间

Xcode 约 **40 GB**（下载 10 GB + 解压 + 模拟器运行时 + 组件）。
装前先确认空间：

```bash
df -h / | tail -1
```

---

## 3. CocoaPods

Flutter 的 iOS 插件依赖由 CocoaPods 管理，缺它 `flutter build ipa` 会在
`pod install` 阶段失败。

### 3.1 安装（推荐 Homebrew）

```bash
brew install cocoapods
pod --version
```

### 3.2 为什么不要 `sudo gem install cocoapods`

macOS 自带的 **系统 Ruby 2.6**（`/usr/bin/ruby`）权限受限，
`sudo gem install cocoapods` 常见两类失败：

- `ERROR: While executing gem ... (Gem::FilePermissionError)`
  —— 系统目录只读，需要 sudo，会污染系统环境
- 装上了但 `pod` 命令找不到 —— gem 的 bin 目录不在 `PATH` 里

若已用 gem 装过，卸载后改用 brew：

```bash
sudo gem uninstall cocoapods
brew install cocoapods
which pod    # 应指向 /opt/homebrew/bin/pod
```

> 另一种规范做法是用 rbenv 装独立 Ruby 再装 gem：
> `brew install rbenv && rbenv install 3.2.2 && rbenv global 3.2.2 && gem install cocoapods`。
> 但本项目用 brew 的 cocoapods 就够了，不必多引入 rbenv。

### 3.3 验证

```bash
$ pod --version
1.17.0
```

---

## 4. Android SDK 与 JDK

### 4.1 Android SDK

```bash
brew install --cask android-commandlinetools
brew install --cask android-platform-tools        # adb

# 接受许可（必须，否则 gradle 同步依赖会卡住）
yes | sdkmanager --licenses

# 安装构建所需组件
sdkmanager "platform-tools" "platforms;android-35" "build-tools;35.0.0"
```

> `sdkmanager` 需要 Java，Homebrew 的 cask 会提示装 temurin：
> `brew install --cask temurin`（见 4.2）。

**SDK 路径说明**：Homebrew 的 SDK 根目录是
`/opt/homebrew/share/android-commandlinetools`（**不是** Android Studio 默认的
`~/Library/Android/sdk`）。若你用 Android Studio 装过 SDK，则以
`~/Library/Android/sdk` 为准，两者择一即可。

设置环境变量（写入 `~/.zshrc`）：

```bash
# 用 Homebrew 路径
export ANDROID_HOME="/opt/homebrew/share/android-commandlinetools"
export PATH="$PATH:$ANDROID_HOME/platform-tools:$ANDROID_HOME/cmdline-tools/latest/bin"

# 若用 Android Studio 装的 SDK，改用下面两行
# export ANDROID_HOME="$HOME/Library/Android/sdk"
# export PATH="$PATH:$ANDROID_HOME/platform-tools:$ANDROID_HOME/cmdline-tools/latest/bin"
```

验证：

```bash
$ echo $ANDROID_HOME
/opt/homebrew/share/android-commandlinetools
$ flutter doctor
[✓] Android toolchain - develop for Android devices
```

#### ⚠️ 坑一：`android-platform-tools` cask 会被误判为 SDK 根

装了 `brew install --cask android-platform-tools` 之后，Flutter 的
`flutter doctor` 可能把 SDK 根报成：

```
Android SDK at /opt/homebrew/Caskroom/android-platform-tools/37.0.1
```

那个目录**只有 adb**，没有 `platforms/`、`build-tools/`、`ndk/`。
原因见 Flutter 源码 `android_sdk.dart` 的 `validSdkDirectory()`——
只要存在 `platform-tools/` 或 `licenses/` 就算有效 SDK 目录。

Gradle 拿它当 SDK 根时，会在安装 NDK 时报：

```
com.android.builder.sdk.LicenceNotAcceptedException: Failed to install
the following Android SDK packages as some licences have not been accepted.
    ndk;28.2.13676358 NDK (Side by side) 28.2.13676358
```

**解决办法**：显式导出 `ANDROID_HOME` 指向真正的 SDK 根
（`/opt/homebrew/share/android-commandlinetools`）。
`scripts/build.sh` 与 `scripts/dev.sh` 已在构建时自动导出，无需手工设置。

#### ⚠️ 坑二：compileSdk 必须是 36

Flutter 3.47 默认 `compileSdk = 36`，而 `sdkmanager "platforms;android-35"`
只装到 35。缺 36 时有两种表现：

- AGP 能联网 → 自动下载安装（需 `licenses/` 已接受）
- 无法联网 → 报 `requires libraries and applications that depend on it to
  compile against version 36 or later of the Android APIs`

预检会提示当前已装版本；缺失时执行：

```bash
sdkmanager "platforms;android-36"
```

另外，第三方插件若把 `compileSdk` 写死成 34（如 `file_picker 8.x`），
同样会触发上述报错。`file_picker ≥ 10.3.10` 改为
`compileSdk flutter.compileSdkVersion`，可跟随 Flutter 的版本。

### 4.2 JDK 17+

Android Gradle Plugin 9.x 要求 **JDK 17+**。本机当前是 **JDK 1.8**，
`./scripts/build.sh android dev --check` 会直接判失败。

**先装 JDK 17（不覆盖已有 JDK）**：

```bash
# 方式 A：Homebrew 的 openjdk（formula 名是 openjdk@17，不是 --jdk@17）
brew install openjdk@17

# 方式 B：Homebrew 的 temurin（android-commandlinetools cask 推荐）
brew install --cask temurin
```

macOS 的 `java_home` 支持多版本并存，`brew install` 是**新增**一个 JDK，
**不会**改动已有的 1.8。

> ⚠️ `brew install --jdk@17` 会报 `Error: invalid option: --jdk@17` ——
> Homebrew 里没有这个包名，formula 名是 `openjdk@17`（无 `--` 前缀）。

安装后，两种方式的 `JAVA_HOME` 路径不同：

```bash
# 方式 A（openjdk@17）：keg-only，不会自动进 java_home 的搜索路径
export JAVA_HOME="/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home"

# 方式 B（temurin）
export JAVA_HOME="/opt/homebrew/opt/temurin/libexec/openjdk.jdk/Contents/Home"
```

---

### 4.3 JDK 1.8 与 17 共存（本机推荐方案）

> **本机 Java 项目必须继续用 JDK 1.8，不能升级。**
> 本节说明如何让 Android 打包单独用 JDK 17，两者互不干扰。

#### 为什么可以共存

本机当前状态（实测）：

| 项                    | 状态                                                                              |
|---------------------|-----------------------------------------------------------------------------------|
| `JAVA_HOME`          | **未设置** —— 系统 `java` 是 `/usr/bin/java` shim，指向 1.8                       |
| IntelliJ IDEA 的 JDK | 已配 `1.8` → `/Library/Java/JavaVirtualMachines/jdk-1.8.jdk/Contents/Home`        |
| IDE 构建             | IntelliJ 的 Gradle JVM 与 `gradle.properties` **独立于 `JAVA_HOME`**                |

关键在于 **Flutter 找 Java 的顺序**（`flutter_tools/lib/src/android/java.dart`）：

```
1) flutter config --jdk-dir 指定的目录   ← 本方案用它
2) JAVA_HOME 环境变量
3) PATH 上的 java
```

`flutter config --jdk-dir` 写的是 Flutter 自己的配置文件
（`~/.config/flutter/settings`），**不碰 `JAVA_HOME`、不碰 `PATH`、
不碰 `java`/`javac` 命令**，因此：

- 你的 Java 1.8 项目 —— IntelliJ 配置不变、命令行 `java` 不变 —— **完全不受影响**
- 只有 Flutter / Android 打包走 JDK 17

#### 操作步骤

```bash
# 1) 装 JDK 17（见 4.2）
brew install openjdk@17

# 2) 让 Flutter 单独指向它
#    openjdk@17 是 keg-only，不在 java_home 的默认搜索路径里，
#    所以这里直接写 brew 的路径，不要用 $(/usr/libexec/java_home -v 17)
flutter config --jdk-dir="/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home"

# 若用 temurin 装的：
# flutter config --jdk-dir="/opt/homebrew/opt/temurin/libexec/openjdk.jdk/Contents/Home"
```

输出 `Setting "jdk-dir" value to "..."` 即成功。

> 若希望 `/usr/libexec/java_home -v 17` 也能找到它（**可选**，会把它注册进
> macOS 的 JDK 列表，但仍不会改变 1.8 的默认地位）：
>
> ```bash
> sudo ln -sfn /opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk \
>   /Library/Java/JavaVirtualMachines/openjdk-17.jdk
> ```
>
> 做完这步后 `flutter config --jdk-dir=$(/usr/libexec/java_home -v 17)` 就能用了。
> 不想注册就别做这步，直接用上面的绝对路径。

#### 验证两边都正常

```bash
# 你的 Java 项目侧：应仍是 1.8
$ java -version
java version "1.8.0_421"                    # ✅ 未受影响

$ echo "JAVA_HOME=${JAVA_HOME:-<未设置>}"
JAVA_HOME=<未设置>                            # ✅ 依然未设置

# Flutter 打包侧：应是 17
$ ./scripts/build.sh android dev --check
  ✓ 打包用 JDK 17.0.x：/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home
```

#### 回退

不想用 JDK 17 了，清掉该配置即可（系统 JDK 不受影响）：

```bash
flutter config --jdk-dir=      # 传空值即移除
```

#### 备选：只在打包时临时切换

若不想改全局 Flutter 配置，也可在打包命令前临时指定 `JAVA_HOME`：

```bash
JAVA_HOME="/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home" \
  ./scripts/build.sh android dev
```

Flutter 找 Java 的顺序里 `JAVA_HOME` 排第 2，所以这样也有效。

但 `scripts/build.sh` 内部是直接调 `flutter build`，**不读取** `JAVA_HOME`
来选 JDK（Flutter 走的是上面 1)/2)/3) 顺序），所以更推荐用
`flutter config --jdk-dir`。

> **不建议**用 `org.gradle.java.home` 写进 `android/gradle.properties`：
> 那是**绝对路径**，提交进仓库后在同事机器 / CI 上会失效。
> `flutter config --jdk-dir` 是每台机器各自的本地配置，不入库。

#### Gradle daemon 缓存的坑

Gradle daemon 是常驻进程，会记住启动时的 JDK。改完 JDK 后若行为没变：

```bash
cd zg-tsp-android/android
./gradlew --stop        # 停掉旧 daemon
```



---

## 5. iOS 签名（打包 ipa 必需）

`flutter build ipa` 需要证书与描述文件。**证书不入库**，需本地配置。

### 5.1 配置 Apple Developer 账号

1. 注册 [Apple Developer Program](https://developer.apple.com/programs/)
   （个人账号 $99/年，企业账号 $299/年；**免费账号无法打包 ipa**）
2. 在 `Certificates, Identifiers & Profiles` 创建：
    - **Apple Distribution** 证书（打包用）
    - App ID：`com.zgtsp.zgTspIos`（与 `PRODUCT_BUNDLE_IDENTIFIER` 一致）
    - Provisioning Profile

### 5.2 安装证书到钥匙串

`.p12` 文件双击导入「钥匙串访问」→ 信任证书 → 允许访问钥匙。

### 5.3 配置工程签名

在 `zg-tsp-ios/ios/Runner.xcodeproj/project.pbxproj` 中，
为 **Runner** target 配置 `DEVELOPMENT_TEAM`：

```bash
grep -o 'DEVELOPMENT_TEAM = [A-Z0-9]*' \
  zg-tsp-ios/ios/Runner.xcodeproj/project.pbxproj
```

若为空则打包会因「No signing certificate」失败。

**方式一：用 build.sh 的环境变量注入（推荐，可脚本化）**

```bash
DEVELOPMENT_TEAM=<你的 Team ID> ./scripts/build.sh ios dev
```

`build.sh` 会把它写进渠道 xcconfig（`ios/Flutter/Dev.xcconfig`）：

```
DEVELOPMENT_TEAM = <你的 Team ID>
CODE_SIGN_STYLE = Automatic
```

该 xcconfig 是 `Debug/Release/Profile-Dev` 三个构建配置的 baseConfiguration，
因此三个配置会同时带上签名团队。渠道已配置过时 `build.sh` 也会重新校验并更新该文件。

**方式二：在 Xcode 图形界面配置**

```bash
open zg-tsp-ios/ios/Runner.xcworkspace
```

选中 Runner target → Signing & Capabilities → 勾选 Automatically manage
signing → 选择 Team。

> 提示：方式一写入的是 `ios/Flutter/Dev.xcconfig`，该文件由脚本生成、已 gitignore；
> 方式二直接改 `project.pbxproj`（入库）。两者选其一即可。

### 5.4 跳过签名（仅验证构建，不产出可安装 ipa）

```bash
flutter build ipa --flavor dev --no-codesign
```

---

## 6. Android 签名（打包 release 必需）

`prod` 渠道出 `.aab` 上架，必须用正式签名；缺 `key.properties` 时
gradle 会退回 debug 签名，**产物不可上架**。

```bash
# 1) 生成 keystore
keytool -genkey -v \
  -keystore ~/zg-tsp-release.jks \
  -keyalg RSA -keysize 2048 -validity 10000 \
  -alias zgtsp

# 2) 写入 zg-tsp-android/android/key.properties（不入库）
#    也可直接复制模板：cp zg-tsp-android/android/key.properties.example \
#                     zg-tsp-android/android/key.properties
cat > zg-tsp-android/android/key.properties <<'EOF'
storePassword=<keystore 密码>
keyPassword=<key 密码>
keyAlias=zgtsp
storeFile=/Users/<你的用户名>/zg-tsp-release.jks
EOF

# 3) 确认 .gitignore 已忽略该文件
grep key.properties zg-tsp-android/android/.gitignore
```

> `storeFile` 支持绝对路径，也支持相对 `android/` 目录的相对路径
> （如 `storeFile=../zg-tsp-release.jks`）。
> `key.properties` 存在时 release 构建使用其中的正式签名；**文件缺失时自动退回
> debug 签名**（`CN=Android Debug`，仅供内部测试，不可上架），
> `build.sh` 的 `check_android_signing` 会同步给出告警。

---

## 7. 数据库初始化（服务端）

部署到空机器时，先把数据库建起来。一条命令完成
「建库 → 建 14 张表 → 写积分规则种子 → 创建 admin 账户」：

```bash
./scripts/init.sh              # 幂等，可重复执行
./scripts/init.sh --drop       # 先删库重建（危险，需二次确认）
```

脚本从 `zg-tsp-server/.env` 的 `DATABASE_URL` 解析连接信息
（也可用 `MYSQL_HOST` / `MYSQL_PORT` / `MYSQL_USER` / `MYSQL_PASSWORD` /
`MYSQL_DATABASE` 覆盖），并按 `dev.sh` 相同的顺序探测仓库目录。

### 两条初始化路径的区别

| | `scripts/init.sh` | `python -m app.seed.initial_data` |
|---|---|---|
| 建表方式 | 导入 `zg-tsp-docs/sql/init.sql` | SQLAlchemy `create_all()` |
| 数据内容 | 建表 + 10 条积分规则 + admin | 建表 + 积分规则 + admin + 班级 + 4 个测试账号 + 家长绑定 + 成语题库 |
| 适用场景 | 部署 / 生产 | 本地开发联调 |
| 密码来源 | `ADMIN_INIT_PASSWORD`，未设则随机生成并打印 | 同左 |

两者可共存：先跑 `init.sh`，需要联调数据再跑 `initial_data`
（它对已存在的表幂等，只补种子）。

### 建表 SQL 的来源

`zg-tsp-docs/sql/init.sql` 由 `python -m app.seed.export_ddl` **从 ORM 生成**，
不要手工编辑。权威来源是 `zg-tsp-server/app/models/entities.py`（14 张表）——
**不是**本仓库 PRD 第 4.1 节，后者是 SQLite 方言，与服务端实际跑的 MySQL 8 不符。

改了 ORM 的字段后重新生成：

```bash
cd zg-tsp-server && python -m app.seed.export_ddl
```

### 两处需要注意的地方

1. **admin 密码以占位符写入**。`init.sql` 里 admin 的 `password_hash` 是
   `__ADMIN_BCRYPT_HASH__`，由 `init.sh` 在运行时替换成实际 bcrypt 哈希。
   直接用 `mysql < init.sql` 导入会导致 admin **无法登录**。
2. **admin 已存在时不会被覆盖**。重复执行 `init.sh` 不会把运维改过的密码打回
   原形，也不会重置 `must_change_password`。

---

## 8. 完整验证流程

环境装齐后按顺序执行：

```bash
# 1) 全局体检
flutter doctor -v

# 2) 渠道与构建配置预检
./scripts/build.sh ios dev --check
./scripts/build.sh android dev --check

# 3) 首次打包（脚本会自动补齐 flavor 配置）
./scripts/build.sh ios dev
./scripts/build.sh android dev

# 4) 查看产物
ls -lh dist/
```

> `scripts/build.sh` 会在工程里**自动生成**渠道相关文件
> （iOS 的 `Dev.xcconfig` / `Dev.xcscheme` / `*-Dev` 构建配置，
> Android 的 `productFlavors`）。首次执行会先备份原文件为 `*.bak`。

---

## 9. 常见问题

**Q：`flutter doctor` 报「CocoaPods not installed」但明明装了 pod**

```bash
which pod          # 路径不对就是 PATH 问题
echo $PATH | tr ':' '\n' | grep -i homebrew
```

**Q：pod install 报 `CDN: trunk URL couldn't be downloaded` / `Could not find compatible versions`**

国内网络访问 CocoaPods 官方 CDN 不稳，改用清华镜像：

```bash
# 1) 换成镜像源
pod repo remove trunk
pod repo add trunk https://mirrors.tuna.tsinghua.edu.cn/git/CocoaPods/Specs.git
pod repo update trunk

# 2) Podfile 首行必须显式写 source，否则 CocoaPods 1.8+ 会自动切回官方 CDN
#    （在 zg-tsp-ios/ios/Podfile 第一行加）
# source 'https://mirrors.tuna.tsinghua.edu.cn/git/CocoaPods/Specs.git'
```

备用镜像：阿里云 `https://mirrors.aliyun.com/repo/CocoaPods/Specs.git`。
镜像源体积约 1.4 GB，首次 `pod repo update` 较慢，之后走增量。

**Q：pod install 报 `Unable to find a specification for "xxx"`**

Podfile 里的 `source` 与 `pod repo list` 中的地址不一致：

```bash
pod repo list          # 确认当前源
grep -n "^source" zg-tsp-ios/ios/Podfile
```

**Q：pod install 卡在 `Unable to find a specification` 且提示 CDN 错误**

清理损坏的搜索索引缓存后重试：

```bash
rm ~/Library/Caches/CocoaPods/search_index.json
pod install
```

**Q：`flutter build ipa` 报 `No profiles for 'com.zgtsp.zgTspIos' found`**

Provisioning Profile 没创建或没匹配 Bundle ID，见第 5 节。

**Q：`xcodebuild: error: Unable to find a destination`**

模拟器运行时未装：Xcode → Settings → Platforms → iOS 26.x → Download。

**Q：Android 构建报 `Unsupported class file major version` / `invalid source release: 17`**

打包用的 JDK 版本不对。本机需要 JDK 1.8 与 17 共存，见第 4.3 节：

```bash
flutter config --jdk-dir="/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home"
```

若改完仍报同样错误，多半是 **Gradle daemon 缓存**了旧 JDK：

```bash
cd zg-tsp-android/android && ./gradlew --stop
```

**Q：装完 JDK 17 后，我的 Java 1.8 项目还能正常用吗？**

能。只要**不设 `JAVA_HOME`**、不动 IntelliJ 的 JDK 配置，就完全不受影响。
本方案用 `flutter config --jdk-dir`，它只写 Flutter 自己的配置文件，
详见第 4.3 节。

**Q：`flutter config --jdk-dir` 怎么撤销 / 查看当前值？**

```bash
flutter config --jdk-dir=        # 传空值 = 移除该配置
cat ~/.config/flutter/settings   # 查看当前所有 Flutter 配置
```

**Q：`flutter build apk` 报 `Failed to install the following Android SDK packages`**

`sdkmanager --licenses` 没执行，许可未接受，见第 4.1 节。

**Q：`zsh: command not found: pod` / `java`**

`~/.zshrc` 里的 `export` 没生效：执行 `source ~/.zshrc`，
或把导出语句加到 `~/.zprofile`。

---

## 10. 参考

- Flutter iOS 部署：<https://docs.flutter.dev/deployment/ios>
- Flutter Android 部署：<https://docs.flutter.dev/deployment/android>
- Apple Developer：<https://developer.apple.com>
- CocoaPods 镜像（清华 TUNA）：<https://mirrors.tuna.tsinghua.edu.cn/help/CocoaPods/>
- Homebrew CocoaPods：<https://formulae.brew.sh/formula/cocoapods>
- Homebrew Android 命令行工具：<https://formulae.brew.sh/cask/android-commandlinetools>

> 本文档中标注的版本要求依据实测环境：
> Flutter 3.47.7 要求 Xcode ≥ 15（`flutter_tools` 中 `xcodeRequiredVersion = Version(15, null, null)`）；
> Homebrew `cocoapods` 当前为 1.17.0；`android-commandlinetools` cask 的 SDK 根目录为
> `/opt/homebrew/share/android-commandlinetools`。
