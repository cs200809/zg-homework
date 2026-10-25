/// 按领域封装的接口调用（对应服务端 routers）。
///
/// 全 POST + Body，参数不携带于 URL（PRD 3.1）。
library;

import 'api_client.dart';
import 'models.dart';

class AuthApi {
  AuthApi._();
  static final instance = AuthApi._();

  Future<LoginResult> login(String username, String password) async {
    final data = await ApiClient.instance.post(
      '/auth/login',
      body: {'username': username, 'password': password},
    );
    return LoginResult.fromJson(data);
  }

  Future<UserInfo> me() async {
    final data = await ApiClient.instance.post('/auth/me');
    return UserInfo.fromJson(data['user'] as Map<String, dynamic>);
  }

  Future<void> register({
    required String username,
    required String password,
    required String role,
    String? nickname,
    String? teacherInviteCode,
  }) async {
    await ApiClient.instance.post('/auth/register', body: {
      'username': username,
      'password': password,
      'role': role,
      if (nickname != null && nickname.isNotEmpty) 'nickname': nickname,
      if (teacherInviteCode != null && teacherInviteCode.isNotEmpty)
        'teacher_invite_code': teacherInviteCode,
    });
  }

  Future<void> changePassword(String oldPassword, String newPassword) async {
    await ApiClient.instance.post('/auth/change-password', body: {
      'old_password': oldPassword,
      'new_password': newPassword,
    });
  }
}

class StudentApi {
  StudentApi._();
  static final instance = StudentApi._();

  // ---- 签到（PRD 5.4） ----
  Future<Json> checkin() => ApiClient.instance.post('/checkin/do');

  Future<Json> checkinStatus() => ApiClient.instance.post('/checkin/status');

  // ---- 积分（PRD 5.4） ----
  Future<Json> rank(String type, {int page = 1, int size = 50}) =>
      ApiClient.instance.post('/points/rank', body: {
        'type': type,
        'page': page,
        'size': size,
      });

  Future<Json> pointLog({int page = 1, int size = 20, String? type}) =>
      ApiClient.instance.post('/points/log', body: {
        'page': page,
        'size': size,
        if (type != null) 'type': type,
      });

  Future<Json> pointSummary() => ApiClient.instance.post('/points/summary');

  // ---- 作业（PRD 5.3） ----
  Future<Json> todayHomework() => ApiClient.instance.post('/homework/today');

  Future<Json> homeworkDetail(int id) =>
      ApiClient.instance.post('/homework/detail', body: {'homework_id': id});

  Future<Json> startHomework(int id) =>
      ApiClient.instance.post('/homework/start', body: {'homework_id': id});

  Future<Json> submitHomework(int id, {String? text, String? filePath}) =>
      ApiClient.instance.postMultipart('/homework/submit', {
        'homework_id': '$id',
        if (text != null && text.isNotEmpty) 'text_content': text,
      });

  // ---- 阅读（PRD 5.5） ----
  Future<Json> articleList({int page = 1, int size = 20}) =>
      ApiClient.instance.post('/articles/list', body: {'page': page, 'size': size});

  Future<Json> articleDetail(int id) =>
      ApiClient.instance.post('/articles/detail', body: {'article_id': id});

  Future<Json> heartbeat(int articleId, int seconds) =>
      ApiClient.instance.post('/articles/heartbeat', body: {
        'article_id': articleId,
        'seconds': seconds,
      });

  Future<Json> finishArticle(int id) =>
      ApiClient.instance.post('/articles/finish', body: {'article_id': id});

  // ---- 游戏（PRD 5.6） ----
  Future<Json> sudokuStart(String difficulty) =>
      ApiClient.instance.post('/games/sudoku/start', body: {'difficulty': difficulty});

  Future<Json> sudokuResult(
    String puzzleId,
    int duration,
    bool success, {
    List<List<int>>? board,
  }) => ApiClient.instance.post('/games/sudoku/result', body: {
    'puzzle_id': puzzleId,
    'duration': duration,
    'success': success,
    if (board != null) 'board': board,
  });

  Future<Json> idiomStart() => ApiClient.instance.post('/games/idiom/start');

  Future<Json> idiomQuestion(String sessionId) =>
      ApiClient.instance.post('/games/idiom/question', body: {'session_id': sessionId});

  Future<Json> idiomAnswer(String sessionId, String answer) =>
      ApiClient.instance.post('/games/idiom/answer', body: {
        'session_id': sessionId,
        'answer': answer,
      });

  Future<Json> idiomResult(String sessionId) =>
      ApiClient.instance.post('/games/idiom/result', body: {'session_id': sessionId});

  Future<Json> gameRecords({int page = 1, int size = 20}) =>
      ApiClient.instance.post('/games/records', body: {'page': page, 'size': size});
}

class TeacherApi {
  TeacherApi._();
  static final instance = TeacherApi._();

  Future<Json> myClasses() => ApiClient.instance.post('/classes/my');

  Future<Json> createClass(String name) =>
      ApiClient.instance.post('/classes/create', body: {'name': name});

  Future<Json> classStudents(int classId) =>
      ApiClient.instance.post('/classes/students', body: {'class_id': classId});

  Future<Json> removeStudent(int classId, int studentId) =>
      ApiClient.instance.post('/classes/remove-student', body: {
        'class_id': classId,
        'student_id': studentId,
      });

  Future<Json> homeworkList(int classId, {int page = 1, int size = 20}) =>
      ApiClient.instance.post('/homework/list', body: {
        'class_id': classId,
        'page': page,
        'size': size,
      });

  Future<Json> createHomework({
    required int classId,
    required String title,
    required String deadline,
    String? description,
    String? subject,
  }) => ApiClient.instance.post('/homework/create', body: {
    'class_id': classId,
    'title': title,
    'deadline': deadline,
    if (description != null && description.isNotEmpty) 'description': description,
    if (subject != null && subject.isNotEmpty) 'subject': subject,
  });

  Future<Json> homeworkRecords(int homeworkId) =>
      ApiClient.instance.post('/homework/records', body: {'homework_id': homeworkId});

  Future<Json> deleteHomework(int id) =>
      ApiClient.instance.post('/homework/delete', body: {'homework_id': id});

  Future<Json> articleList({int page = 1, int size = 50}) =>
      ApiClient.instance.post('/articles/list', body: {'page': page, 'size': size});

  Future<Json> createArticle(String title, String content) =>
      ApiClient.instance.post('/articles/create', body: {
        'title': title,
        'content': content,
      });

  Future<Json> deleteArticle(int id) =>
      ApiClient.instance.post('/articles/delete', body: {'article_id': id});

  Future<Json> articleRecords(int id) =>
      ApiClient.instance.post('/articles/records', body: {'article_id': id});
}

class ParentApi {
  ParentApi._();
  static final instance = ParentApi._();

  Future<Json> children() => ApiClient.instance.post('/parent/children');

  Future<Json> bind(String bindCode) =>
      ApiClient.instance.post('/parent/bind', body: {'bind_code': bindCode});

  Future<Json> childPoints(int studentId, {int page = 1, int size = 20}) =>
      ApiClient.instance.post('/parent/child-points', body: {
        'student_id': studentId,
        'page': page,
        'size': size,
      });

  Future<Json> consumeItems() => ApiClient.instance.post('/parent/consume-items');

  Future<Json> consume(
    int studentId,
    String item,
    int points, {
    String? remark,
  }) => ApiClient.instance.post('/parent/consume', body: {
    'student_id': studentId,
    'item': item,
    'points': points,
    if (remark != null && remark.isNotEmpty) 'remark': remark,
  });

  Future<Json> unbind(int studentId) =>
      ApiClient.instance.post('/parent/unbind', body: {'student_id': studentId});
}

class AdminApi {
  AdminApi._();
  static final instance = AdminApi._();

  Future<Json> statsOverview() => ApiClient.instance.post('/admin/stats/overview');

  Future<Json> classes({int page = 1, int size = 20}) =>
      ApiClient.instance.post('/admin/classes/list', body: {'page': page, 'size': size});

  Future<Json> createInvites(int count, int expireDays) =>
      ApiClient.instance.post('/admin/invite/create', body: {
        'count': count,
        'expire_days': expireDays,
      });

  Future<Json> inviteList({int page = 1, int size = 20, String? status}) =>
      ApiClient.instance.post('/admin/invite/list', body: {
        'page': page,
        'size': size,
        if (status != null) 'status': status,
      });

  Future<Json> revokeInvite(int codeId) =>
      ApiClient.instance.post('/admin/invite/revoke', body: {'code_id': codeId});

  Future<Json> users({
    int page = 1,
    int size = 20,
    String? role,
    String? status,
    String? keyword,
  }) => ApiClient.instance.post('/admin/users/list', body: {
    'page': page,
    'size': size,
    if (role != null) 'role': role,
    if (status != null) 'status': status,
    if (keyword != null && keyword.isNotEmpty) 'keyword': keyword,
  });

  Future<Json> disableUser(int userId) =>
      ApiClient.instance.post('/admin/users/disable', body: {'user_id': userId});

  Future<Json> enableUser(int userId) =>
      ApiClient.instance.post('/admin/users/enable', body: {'user_id': userId});

  Future<Json> resetPassword(int userId) =>
      ApiClient.instance.post('/admin/users/reset-password', body: {'user_id': userId});

  Future<Json> rules() => ApiClient.instance.post('/admin/rules/list');

  Future<Json> updateRule({
    required String ruleKey,
    int? points,
    int? dailyLimit,
    String? extraConfig,
    bool? enabled,
  }) => ApiClient.instance.post('/admin/rules/update', body: {
    'rule_key': ruleKey,
    if (points != null) 'points': points,
    if (dailyLimit != null) 'daily_limit': dailyLimit,
    if (extraConfig != null) 'extra_config': extraConfig,
    if (enabled != null) 'enabled': enabled,
  });

  Future<Json> articleList({int page = 1, int size = 20, String? status}) =>
      ApiClient.instance.post('/articles/list', body: {
        'page': page,
        'size': size,
        if (status != null) 'status': status,
      });

  Future<Json> createArticle(String title, String content) =>
      ApiClient.instance.post('/articles/create', body: {
        'title': title,
        'content': content,
      });

  Future<Json> deleteArticle(int id) =>
      ApiClient.instance.post('/articles/delete', body: {'article_id': id});
  // ---- 成语题库（PRD 5.8.6） ----
  Future<Json> idiomList({
    int page = 1,
    int size = 20,
    String? keyword,
    bool? enabled,
  }) => ApiClient.instance.post('/admin/idioms/list', body: {
    'page': page,
    'size': size,
    if (keyword != null && keyword.isNotEmpty) 'keyword': keyword,
    if (enabled != null) 'enabled': enabled,
  });

  Future<Json> importIdioms(List<Map<String, dynamic>> items, String mode) =>
    ApiClient.instance.post('/admin/idioms/import', body: {
      'items': items,
      'mode': mode,
    });

  Future<Json> updateIdiom({
    required int questionId,
    String? prompt,
    String? answer,
    List<String>? distractors,
    String? difficulty,
    bool? enabled,
  }) => ApiClient.instance.post('/admin/idioms/update', body: {
    'question_id': questionId,
    if (prompt != null) 'prompt': prompt,
    if (answer != null) 'answer': answer,
    if (distractors != null) 'distractors': distractors,
    if (difficulty != null) 'difficulty': difficulty,
    if (enabled != null) 'enabled': enabled,
  });

  Future<Json> deleteIdiom(int questionId) =>
    ApiClient.instance.post('/admin/idioms/delete', body: {'question_id': questionId});

  Future<Json> batchDeleteIdioms(List<int> questionIds) =>
    ApiClient.instance.post('/admin/idioms/batch-delete', body: {
      'question_ids': questionIds,
    });

}
