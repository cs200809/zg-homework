/// 服务端数据类型（与 zg-tsp-server 响应一一对应，PRD 第 7 节）。
///
/// iOS 与 Android 两份代码同源，各自仓库独立维护（决策 6）。
library;

class UserInfo {
  final int id;
  final String username;
  final String role; // admin / teacher / student / parent
  final String? nickname;
  final String? avatar;
  final int? classId;
  final String? bindCode;
  final int totalPoints;
  final bool mustChangePassword;

  const UserInfo({
    required this.id,
    required this.username,
    required this.role,
    this.nickname,
    this.avatar,
    this.classId,
    this.bindCode,
    this.totalPoints = 0,
    this.mustChangePassword = false,
  });

  factory UserInfo.fromJson(Map<String, dynamic> json) => UserInfo(
    id: json['id'] as int,
    username: json['username'] as String,
    role: json['role'] as String,
    nickname: json['nickname'] as String?,
    avatar: json['avatar'] as String?,
    classId: json['class_id'] as int?,
    bindCode: json['bind_code'] as String?,
    totalPoints: json['total_points'] as int? ?? 0,
    mustChangePassword: json['must_change_password'] as bool? ?? false,
  );

  Map<String, dynamic> toJson() => {
    'id': id,
    'username': username,
    'role': role,
    'nickname': nickname,
    'avatar': avatar,
    'class_id': classId,
    'bind_code': bindCode,
    'total_points': totalPoints,
    'must_change_password': mustChangePassword,
  };
}

class LoginResult {
  final String token;
  final int expireAt;
  final UserInfo user;
  final bool mustChangePassword;

  const LoginResult({
    required this.token,
    required this.expireAt,
    required this.user,
    required this.mustChangePassword,
  });

  factory LoginResult.fromJson(Map<String, dynamic> json) => LoginResult(
    token: json['token'] as String,
    expireAt: json['expire_at'] as int,
    user: UserInfo.fromJson(json['user'] as Map<String, dynamic>),
    mustChangePassword: json['must_change_password'] as bool? ?? false,
  );
}

/// 分页响应（PRD 3.2）：{list, total, page, size}
class Paged<T> {
  final List<T> list;
  final int total;
  final int page;
  final int size;

  const Paged({
    required this.list,
    required this.total,
    required this.page,
    required this.size,
  });

  factory Paged.fromJson(
    Map<String, dynamic> json,
    T Function(Map<String, dynamic>) parse,
  ) => Paged(
    list: (json['list'] as List)
        .map((e) => parse(e as Map<String, dynamic>))
        .toList(),
    total: json['total'] as int? ?? 0,
    page: json['page'] as int? ?? 1,
    size: json['size'] as int? ?? 20,
  );
}

/// 通用键值对，避免为每个小结构体建类。
typedef Json = Map<String, dynamic>;