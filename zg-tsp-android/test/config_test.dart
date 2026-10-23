/// 配置与数据模型单元测试。
///
/// 这些测试不需要服务端，可离线运行：
///     flutter test
library;

import 'package:flutter_test/flutter_test.dart';
import 'package:zg_tsp_android/core/config.dart';
import 'package:zg_tsp_android/core/models.dart';

void main() {
  group('AppConfig', () {
    test('默认渠道为 dev', () {
      expect(AppConfig.isDev, isTrue);
    });

    test('API 基地址可被构建期覆盖', () {
      // 未传 --dart-define 时应回落到本地调试地址
      expect(AppConfig.apiBaseUrl, isNotEmpty);
    });
  });

  group('UserInfo', () {
    test('从 JSON 解析', () {
      final u = UserInfo.fromJson({
        'id': 3,
        'username': 'student01',
        'role': 'student',
        'nickname': '张小明',
        'bind_code': 'B0101',
        'total_points': 50,
        'must_change_password': false,
      });

      expect(u.id, 3);
      expect(u.username, 'student01');
      expect(u.role, 'student');
      expect(u.nickname, '张小明');
      expect(u.bindCode, 'B0101');
      expect(u.totalPoints, 50);
      expect(u.mustChangePassword, isFalse);
    });

    test('可往返序列化（用于本地缓存）', () {
      const original = UserInfo(
        id: 7,
        username: 'teacher01',
        role: 'teacher',
        nickname: '王老师',
        totalPoints: 0,
      );
      final restored = UserInfo.fromJson(original.toJson());

      expect(restored.id, original.id);
      expect(restored.username, original.username);
      expect(restored.role, original.role);
      expect(restored.nickname, original.nickname);
    });

    test('缺省字段安全回落', () {
      final u = UserInfo.fromJson({'id': 1, 'username': 'x', 'role': 'student'});
      expect(u.totalPoints, 0);
      expect(u.mustChangePassword, isFalse);
      expect(u.bindCode, isNull);
    });
  });

  group('LoginResult', () {
    test('从 JSON 解析并含 token', () {
      final r = LoginResult.fromJson({
        'token': 'abc.def.ghi',
        'expire_at': 1793328561,
        'user': {'id': 1, 'username': 'admin', 'role': 'admin'},
        'must_change_password': true,
      });

      expect(r.token, 'abc.def.ghi');
      expect(r.mustChangePassword, isTrue);
      expect(r.user.role, 'admin');
    });
  });
}