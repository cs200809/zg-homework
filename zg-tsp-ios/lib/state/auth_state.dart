/// 登录态管理。
///
/// token 与用户信息持久化到本地（PRD 5.1：JWT 存本地，有效期 7 天）。
/// 启动时用 /auth/me 校验 token 是否仍有效，失效则清理并回登录页。
library;

import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../core/api_client.dart';
import '../core/apis.dart';
import '../core/models.dart';

const _kToken = 'token';
const _kUser = 'user';

class AuthState extends ChangeNotifier {
  UserInfo? _user;
  bool _initialized = false;
  bool _loading = false;

  UserInfo? get user => _user;
  bool get initialized => _initialized;
  bool get loading => _loading;
  bool get isLoggedIn => _user != null;

  /// 启动时恢复登录态
  Future<void> init() async {
    final prefs = await SharedPreferences.getInstance();
    final token = prefs.getString(_kToken);
    final rawUser = prefs.getString(_kUser);

    if (token == null || rawUser == null) {
      _initialized = true;
      notifyListeners();
      return;
    }

    ApiClient.instance.setToken(token);
    try {
      // 服务端会校验 token 与用户状态，禁用用户的 token 会立即失效
      _user = await AuthApi.instance.me();
      await prefs.setString(_kUser, jsonEncode(_user!.toJson()));
    } catch (_) {
      // token 过期或账号被禁用 → 清理
      ApiClient.instance.setToken(null);
      await prefs.remove(_kToken);
      await prefs.remove(_kUser);
      _user = null;
    }
    _initialized = true;
    notifyListeners();
  }

  Future<void> login(String username, String password) async {
    _loading = true;
    notifyListeners();
    try {
      final result = await AuthApi.instance.login(username, password);
      ApiClient.instance.setToken(result.token);
      _user = result.user;

      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(_kToken, result.token);
      await prefs.setString(_kUser, jsonEncode(result.user.toJson()));

      _initialized = true;
      notifyListeners();
    } finally {
      _loading = false;
      notifyListeners();
    }
  }

  Future<void> logout() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_kToken);
    await prefs.remove(_kUser);
    ApiClient.instance.setToken(null);
    _user = null;
    notifyListeners();
  }

  /// 改密成功后清除强制改密标记
  Future<void> markPasswordChanged() async {
    if (_user == null) return;
    final updated = UserInfo(
      id: _user!.id,
      username: _user!.username,
      role: _user!.role,
      nickname: _user!.nickname,
      avatar: _user!.avatar,
      classId: _user!.classId,
      bindCode: _user!.bindCode,
      totalPoints: _user!.totalPoints,
      mustChangePassword: false,
    );
    _user = updated;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_kUser, jsonEncode(updated.toJson()));
    notifyListeners();
  }

  Future<void> refreshUser() async {
    try {
      _user = await AuthApi.instance.me();
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(_kUser, jsonEncode(_user!.toJson()));
      notifyListeners();
    } catch (_) {
      // 忽略：保留本地状态，下次操作再处理
    }
  }
}