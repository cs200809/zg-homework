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
├── main.dart          应用入口 + 角色路由守卫
├── core/
│   ├── config.dart    构建期配置（API 基地址、渠道）
│   ├── models.dart    数据类型定义
│   ├── api_client.dart HTTP 客户端（统一 POST、错误码、降级）
│   └── apis.dart      按领域封装的接口（auth/student/teacher/parent/admin）
├── state/auth_state.dart  登录态（Provider + 本地持久化）
├── pages/
│   ├── common/        登录/注册/强制改密/我的
│   ├── student/       首页/作业/阅读/游戏/积分
│   ├── parent/        孩子/积分明细/消耗
│   ├── teacher/       班级/作业/文章
│   └── admin/         概览/邀请码/用户/规则/成语题库
└── widgets/           通用组件（StatCard/EmptyView/ErrorView 等）
```

## 四角色导航（PRD 第 9 节）

| 角色   | 底部导航                                      |
|--------|--------------------------------------------|
| 学生   | 首页 / 作业 / 阅读 / 游戏 / 我的                |
| 老师   | 班级 / 作业 / 文章 / 我的                      |
| admin  | 概览 / 邀请码 / 用户 / 规则 / 题库 / 我的        |
| 家长   | 我的孩子 / 我的                                |

## 开发

```bash
flutter pub get
flutter analyze          # 静态检查
flutter test             # 单元测试
flutter run --dart-define=API_BASE_URL=http://10.0.2.2:8000
```

> Android 模拟器访问宿主机需用 `10.0.2.2` 而非 `127.0.0.1`。

## 接口契约

全 POST + Body。完整清单见 PRD 第 7 节（`zg-tsp-docs` 仓库的
`sys_doc/PRD.md`）—— 与其他模块的唯一契约来源。

## 开发进度

- [x] P0 骨架：pubspec、配置、API 客户端、目录结构、.gitignore
- [x] P0：`flutter create` 生成 `android/` 平台工程
- [x] P8 四角色页面（与 ios 端同源，各自仓库独立），含成语题库管理
- [x] `flutter analyze` 无问题、`flutter test` 6 个用例通过
