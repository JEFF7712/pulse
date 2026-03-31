import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';

import '../config/server_config_store.dart';
import '../services/pulse_api_client.dart';

class SessionController extends ChangeNotifier {
  SessionController({
    ServerConfigStore? store,
  }) : _store = store ?? ServerConfigStore();

  final ServerConfigStore _store;

  bool _ready = false;
  bool get ready => _ready;

  ServerConfig? _config;
  ServerConfig? get config => _config;

  bool get isConfigured => _config != null;

  PulseApiClient? get apiClient =>
      _config == null ? null : PulseApiClient(_config!);

  Future<void> load() async {
    _ready = false;
    notifyListeners();
    _config = await _store.load();
    _ready = true;
    notifyListeners();
  }

  /// Verifies GET /health then persists URL + token.
  Future<void> saveAndValidate(String baseUrl, String token) async {
    final trimmedUrl = baseUrl.trim();
    final trimmedToken = token.trim();
    if (trimmedUrl.isEmpty || trimmedToken.isEmpty) {
      throw StateError('Server URL and token are required.');
    }
    await PulseApiClient.pingHealth(trimmedUrl);
    final cfg = ServerConfig(
      baseUrl: ServerConfigStore.normalizeBaseUrl(trimmedUrl),
      token: trimmedToken,
    );
    await _store.save(cfg);
    _config = cfg;
    notifyListeners();
  }

  Future<void> signOut() async {
    await _store.clear();
    _config = null;
    notifyListeners();
  }

  static String describeDioError(Object e) {
    if (e is DioException) {
      final status = e.response?.statusCode;
      if (status == 401) {
        return 'Unauthorized — check your companion token.';
      }
      if (status == 404) {
        return 'Not found — check the server URL and that Pulse is running.';
      }
      return e.message ?? 'Network error';
    }
    if (e is StateError) {
      return e.message;
    }
    return e.toString();
  }
}
