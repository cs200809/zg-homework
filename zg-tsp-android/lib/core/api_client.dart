/// 服务端 HTTP 客户端。
///
/// 独立性约束（PRD 2.2.1）：
/// - 仅通过 HTTP 与 zg-tsp-server 通信，不引用服务端源码
/// - 基地址取自构建期配置，见 config.dart
/// - 服务端不可用时抛出 [ServiceUnavailableError]，由调用方降级处理，不崩溃
library;

import 'dart:convert';

import 'package:http/http.dart' as http;

import 'config.dart';
import 'models.dart';

/// 服务端不可达（网络不通 / 服务端未启动）
class ServiceUnavailableError implements Exception {
  ServiceUnavailableError([this.message = '无法连接服务端，请检查网络或稍后重试']);

  final String message;

  @override
  String toString() => message;
}

/// 业务错误（含错误码，PRD 3.1）
class ApiException implements Exception {
  ApiException(this.code, this.message);

  final int code;
  final String message;

  bool get isUnauthorized => code == 401;
  bool get isForbidden => code == 403;

  @override
  String toString() => message;
}

/// 统一响应结构
class ApiResponse {
  final int code;
  final String message;
  final dynamic data;

  const ApiResponse({required this.code, required this.message, required this.data});

  factory ApiResponse.fromJson(Map<String, dynamic> json) => ApiResponse(
    code: json['code'] as int? ?? 500,
    message: json['message'] as String? ?? 'ok',
    data: json['data'],
  );
}

class ApiClient {
  ApiClient._();

  static final ApiClient instance = ApiClient._();

  String? _token;

  void setToken(String? token) => _token = token;

  String? get token => _token;

  String get _baseUrl => AppConfig.apiBaseUrl;

  /// 统一 POST 调用（全 POST + Body 约定，PRD 3.1）。
  Future<Json> post(String path, {Json body = const {}}) async {
    final uri = Uri.parse('$_baseUrl$path');

    late http.Response res;
    try {
      res = await http
          .post(
            uri,
            headers: {
              'Content-Type': 'application/json',
              if (_token != null) 'Authorization': 'Bearer $_token',
            },
            body: jsonEncode(body),
          )
          .timeout(AppConfig.timeout);
    } catch (_) {
      // 网络异常、DNS 失败、超时 —— 统一归为服务端不可用
      throw ServiceUnavailableError();
    }

    final decoded = jsonDecode(utf8.decode(res.bodyBytes));
    final payload = ApiResponse.fromJson(decoded as Map<String, dynamic>);

    if (payload.code != 0) {
      throw ApiException(payload.code, payload.message);
    }
    return (payload.data ?? {}) as Json;
  }

  /// multipart 上传（作业文件，PRD 5.3）
  Future<Json> postMultipart(String path, Map<String, String> fields) async {
    final uri = Uri.parse('$_baseUrl$path');

    try {
      final req = http.MultipartRequest('POST', uri);
      if (_token != null) {
        req.headers['Authorization'] = 'Bearer $_token';
      }
      fields.forEach((k, v) => req.fields[k] = v);

      final streamed = await req.send().timeout(AppConfig.timeout);
      final res = await http.Response.fromStream(streamed);
      final payload = ApiResponse.fromJson(
        jsonDecode(utf8.decode(res.bodyBytes)) as Map<String, dynamic>,
      );
      if (payload.code != 0) {
        throw ApiException(payload.code, payload.message);
      }
      return (payload.data ?? {}) as Json;
    } on ApiException {
      rethrow;
    } catch (_) {
      throw ServiceUnavailableError();
    }
  }
}

/// 业务异常转中文提示，供 UI 直接展示。
String errorMessage(Object e) {
  if (e is ApiException) return e.message;
  if (e is ServiceUnavailableError) return e.message;
  return e.toString();
}