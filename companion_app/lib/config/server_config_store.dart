import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Persists Pulse server base URL and companion token (see design: X-Pulse-Token).
class ServerConfigStore {
  ServerConfigStore({FlutterSecureStorage? storage})
      : _storage = storage ?? const FlutterSecureStorage();

  static const _kBaseUrl = 'pulse_server_base_url';
  static const _kToken = 'pulse_companion_token';

  final FlutterSecureStorage _storage;

  Future<ServerConfig?> load() async {
    final base = (await _storage.read(key: _kBaseUrl))?.trim();
    final token = (await _storage.read(key: _kToken))?.trim();
    if (base == null || base.isEmpty || token == null || token.isEmpty) {
      return null;
    }
    return ServerConfig(baseUrl: normalizeBaseUrl(base), token: token);
  }

  Future<void> save(ServerConfig config) async {
    await _storage.write(
      key: _kBaseUrl,
      value: normalizeBaseUrl(config.baseUrl),
    );
    await _storage.write(key: _kToken, value: config.token);
  }

  Future<void> clear() async {
    await _storage.delete(key: _kBaseUrl);
    await _storage.delete(key: _kToken);
  }

  static String normalizeBaseUrl(String raw) {
    var s = raw.trim();
    while (s.endsWith('/')) {
      s = s.substring(0, s.length - 1);
    }
    return s;
  }
}

class ServerConfig {
  const ServerConfig({required this.baseUrl, required this.token});

  final String baseUrl;
  final String token;
}
