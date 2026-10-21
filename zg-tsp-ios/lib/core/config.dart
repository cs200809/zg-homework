/// 应用配置。
///
/// 独立性约束（PRD 2.2.1）：
/// - API 基地址由**构建期** `--dart-define=API_BASE_URL=...` 注入，
///   代码中不硬编码任何地址。
/// - 两端（ios / android）此文件内容一致，各自仓库独立维护。
///
/// 构建示例：
///   flutter build ipa --flavor dev  --dart-define=API_BASE_URL=https://test.example.com
///   flutter build ipa --flavor prod --dart-define=API_BASE_URL=https://api.example.com
library;

class AppConfig {
  const AppConfig._();

  /// 服务端基地址。缺省指向本地开发地址，仅供调试。
  static const String apiBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://127.0.0.1:8000',
  );

  /// 渠道标识：dev / prod
  static const String flavor = String.fromEnvironment(
    'FLAVOR',
    defaultValue: 'dev',
  );

  static bool get isDev => flavor == 'dev';

  /// 请求超时
  static const Duration timeout = Duration(seconds: 15);
}