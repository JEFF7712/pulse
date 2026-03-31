import 'package:dio/dio.dart';

import '../config/server_config_store.dart';

/// HTTP client for Pulse FastAPI (health unauthenticated; /api/* uses X-Pulse-Token).
class PulseApiClient {
  PulseApiClient(ServerConfig config)
      : _root = config.baseUrl,
        _token = config.token,
        _dio = Dio(
          BaseOptions(
            baseUrl: config.baseUrl,
            connectTimeout: const Duration(seconds: 15),
            receiveTimeout: const Duration(seconds: 30),
            headers: {'X-Pulse-Token': config.token},
          ),
        );

  final String _root;
  final String _token;
  final Dio _dio;

  /// GET /health — no companion header required by server; uses plain GET to [baseUrl].
  static Future<void> pingHealth(String baseUrl) async {
    final root = ServerConfigStore.normalizeBaseUrl(baseUrl);
    final dio = Dio(
      BaseOptions(
        connectTimeout: const Duration(seconds: 10),
        receiveTimeout: const Duration(seconds: 10),
      ),
    );
    final response = await dio.get<Map<String, dynamic>>('$root/health');
    if (response.statusCode != 200) {
      throw DioException(
        requestOptions: response.requestOptions,
        response: response,
        message: 'Unexpected status ${response.statusCode}',
      );
    }
    final data = response.data;
    if (data == null || data['status'] != 'ok') {
      throw DioException(
        requestOptions: response.requestOptions,
        response: response,
        message: 'Health check failed',
      );
    }
  }

  Future<Map<String, dynamic>> getLatestDigest() async {
    final response = await _dio.get<Map<String, dynamic>>('/api/digests/latest');
    return response.data ?? {};
  }

  Future<Map<String, dynamic>> getDigest(String dateSlug) async {
    final response =
        await _dio.get<Map<String, dynamic>>('/api/digests/$dateSlug');
    return response.data ?? {};
  }

  Future<void> submitCorrection({
    required String contextId,
    required String messageText,
  }) async {
    await _dio.post<void>(
      '/api/corrections',
      data: {
        'context_id': contextId,
        'message_text': messageText,
      },
    );
  }

  Future<void> registerDeviceToken({
    required String token,
    required String platform,
  }) async {
    await _dio.post<void>(
      '/api/device-token',
      data: {'token': token, 'platform': platform},
    );
  }

  /// POST /webhooks/companion — batch location/health events (server currently accepts without auth).
  Future<void> postCompanionEvents(List<Map<String, dynamic>> events) async {
    final dio = Dio(
      BaseOptions(
        baseUrl: _root,
        connectTimeout: const Duration(seconds: 20),
        receiveTimeout: const Duration(seconds: 30),
        headers: {'X-Pulse-Token': _token},
      ),
    );
    await dio.post<void>('/webhooks/companion', data: {'events': events});
  }
}
