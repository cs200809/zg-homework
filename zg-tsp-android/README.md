# zg-tsp-android

学校兴趣培养积分系统 —— Android 移动端模块（Flutter，学生 / 家长 / 老师 / admin 全覆盖）。

## 独立性

本模块**可单独检出、单独启动、单独打包**，不依赖仓库内其他模块：

- 与服务端**仅通过 HTTP 接口**通信，不引用服务端源码
- 与 iOS 端同源但**各自仓库独立维护**（决策 6），可独立构建、签名、发版
- 配置外置：API 基地址由构建期 `--dart-define` 注入，代码中不硬编码
- 服务端不可用时客户端仍可启动，接口调用降级提示，不崩溃

## 技术栈

Flutter（Dart 3.4+），**四角色全覆盖**（决策 1、2）：

- 学生端 / 家长端 / 老师端 / admin 端：功能全量提供，移动优先形态
- 与 Web 端功能一致，差异仅在交互形态（简表/卡片 vs 完整表格/抽屉/批量）
- 批量操作（如成语题库导入）在移动端提供逐条等效入口

## 前置条件

需先安装 Flutter SDK（当前环境未安装）：

```bash
# macOS
brew install --cask flutter
flutter --version
```

## 初始化工程

```bash
flutter create --org com.zgtsp --project-name zg_tsp_android --platforms=android .
```

> 本仓库已备好 `pubspec.yaml`、`lib/` 结构与 `.gitignore`；
> `flutter create` 会补齐 `android/` 平台工程目录。

## 启动

```bash
flutter pub get

flutter run --flavor dev \
  --dart-define=API_BASE_URL=http://127.0.0.1:8000 \
  --dart-define=FLAVOR=dev
```

## 打包（测试 + 生产渠道）

```bash
# 测试环境
flutter build apk --flavor dev \
  --dart-define=API_BASE_URL=https://test.example.com \
  --dart-define=FLAVOR=dev

# 生产环境
flutter build appbundle --flavor prod \
  --dart-define=API_BASE_URL=https://api.example.com \
  --dart-define=FLAVOR=prod
```

测试渠道产出 `.apk`，生产渠道产出 `.aab`。签名配置在 `android/key.properties`，**密钥库不入库**（见 `.gitignore`）。

## 目录结构

```
lib/
├── main.dart          应用入口
├── core/
│   ├── config.dart    构建期配置（API 基地址、渠道）
│   └── api_client.dart HTTP 客户端（统一 POST、错误码、降级）
├── pages/
│   ├── common/        登录/注册/强制改密
│   ├── student/       学生端
│   ├── parent/        家长端
│   ├── teacher/       老师端（移动形态）
│   └── admin/         admin 端（移动形态）
└── widgets/           通用组件
```

## 接口契约

全 POST + Body。完整清单见 PRD 第 7 节（`sys_doc/PRD.md`）——
与其他模块的唯一契约来源。

## 开发进度

- [x] P0 骨架：pubspec、配置、API 客户端、目录结构、.gitignore
- [ ] P0 待补：`flutter create` 生成 `android/` 平台工程（需先装 Flutter SDK）
- [ ] P8 页面接入（PRD 第 9 节，四角色全覆盖）
