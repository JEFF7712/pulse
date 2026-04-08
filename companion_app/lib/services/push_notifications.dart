import 'dart:async';

import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';

import '../screens/pattern_screens.dart';
import '../utils/context_id_parser.dart';
import 'pulse_api_client.dart';

const _androidChannelId = 'pulse_insights';
const _androidChannelName = 'Pulse insights';

/// Top-level handler for data-only / background FCM (must be a top-level function).
@pragma('vm:entry-point')
Future<void> firebaseMessagingBackgroundHandler(RemoteMessage message) async {
  if (Firebase.apps.isEmpty) {
    await Firebase.initializeApp();
  }
  debugPrint('Pulse push background message: ${message.messageId}');
}

class PushNotificationsCoordinator {
  PushNotificationsCoordinator._();
  static final PushNotificationsCoordinator instance =
      PushNotificationsCoordinator._();

  final FlutterLocalNotificationsPlugin _local =
      FlutterLocalNotificationsPlugin();

  final List<StreamSubscription<dynamic>> _subscriptions = [];

  GlobalKey<NavigatorState>? _navigatorKey;
  bool _started = false;
  String? _lastRegisteredToken;

  /// Registers FCM, posts device tokens to Pulse, shows foreground notifications,
  /// and opens [PatternDetailScreen] when [context_id] maps to a pattern slug.
  Future<void> start({
    required GlobalKey<NavigatorState> navigatorKey,
    required PulseApiClient apiClient,
  }) async {
    if (_started) {
      return;
    }
    _navigatorKey = navigatorKey;

    try {
      if (Firebase.apps.isEmpty) {
        await Firebase.initializeApp();
      }
    } catch (e, st) {
      debugPrint(
        'Pulse push: Firebase.initializeApp failed — add GoogleService-Info.plist '
        '(iOS) and google-services.json + Gradle plugin (Android). Error: $e',
      );
      debugPrint('$st');
      _navigatorKey = null;
      return;
    }

    await _initLocalNotifications();
    await _requestPermissions();

    final messaging = FirebaseMessaging.instance;
    final platform = _deviceTokenPlatform();
    if (platform == null) {
      debugPrint('Pulse push: skipping token registration on this platform.');
      _navigatorKey = null;
      return;
    }

    _started = true;

    Future<void> register(String token) async {
      if (token.isEmpty || token == _lastRegisteredToken) {
        return;
      }
      try {
        await apiClient.registerDeviceToken(token: token, platform: platform);
        _lastRegisteredToken = token;
        debugPrint('Pulse push: registered device token with server.');
      } catch (e) {
        debugPrint('Pulse push: registerDeviceToken failed: $e');
      }
    }

    _subscriptions.add(
      messaging.onTokenRefresh.listen(register),
    );

    final token = await messaging.getToken();
    if (token != null) {
      await register(token);
    }

    _subscriptions.add(
      FirebaseMessaging.onMessage.listen(_onForegroundMessage),
    );

    _subscriptions.add(
      FirebaseMessaging.onMessageOpenedApp.listen((m) {
        _openPatternFromMessageData(m.data);
      }),
    );

    final initial = await messaging.getInitialMessage();
    if (initial != null) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _openPatternFromMessageData(initial.data);
      });
    }
  }

  void stop() {
    for (final sub in _subscriptions) {
      sub.cancel();
    }
    _subscriptions.clear();
    _started = false;
    _navigatorKey = null;
    _lastRegisteredToken = null;
  }

  String? _deviceTokenPlatform() {
    switch (defaultTargetPlatform) {
      case TargetPlatform.iOS:
        return 'ios';
      case TargetPlatform.android:
        return 'android';
      default:
        return null;
    }
  }

  Future<void> _initLocalNotifications() async {
    const androidInit = AndroidInitializationSettings('@mipmap/ic_launcher');
    const darwinInit = DarwinInitializationSettings();
    await _local.initialize(
      const InitializationSettings(
        android: androidInit,
        iOS: darwinInit,
        macOS: darwinInit,
      ),
      onDidReceiveNotificationResponse: _onLocalNotificationTapped,
    );

    final androidPlugin = _local.resolvePlatformSpecificImplementation<
        AndroidFlutterLocalNotificationsPlugin>();
    await androidPlugin?.createNotificationChannel(
      const AndroidNotificationChannel(
        _androidChannelId,
        _androidChannelName,
        description: 'Insight and Pulse alerts',
        importance: Importance.defaultImportance,
      ),
    );
  }

  Future<void> _requestPermissions() async {
    await FirebaseMessaging.instance.requestPermission(
      alert: true,
      badge: true,
      sound: true,
    );

    final iosPlugin = _local.resolvePlatformSpecificImplementation<
        IOSFlutterLocalNotificationsPlugin>();
    await iosPlugin?.requestPermissions(alert: true, badge: true, sound: true);

    final androidPlugin = _local.resolvePlatformSpecificImplementation<
        AndroidFlutterLocalNotificationsPlugin>();
    if (defaultTargetPlatform == TargetPlatform.android) {
      await androidPlugin?.requestNotificationsPermission();
    }
  }

  Future<void> _onForegroundMessage(RemoteMessage message) async {
    final title = message.notification?.title ?? 'Pulse';
    final body = message.notification?.body ?? '';
    final contextId = message.data['context_id'] as String?;

    await _local.show(
      message.hashCode,
      title,
      body,
      const NotificationDetails(
        android: AndroidNotificationDetails(
          _androidChannelId,
          _androidChannelName,
          channelDescription: 'Insight and Pulse alerts',
          importance: Importance.defaultImportance,
          priority: Priority.defaultPriority,
        ),
        iOS: DarwinNotificationDetails(),
      ),
      payload: contextId,
    );
  }

  void _onLocalNotificationTapped(NotificationResponse response) {
    final payload = response.payload;
    if (payload != null && payload.isNotEmpty) {
      _openPatternFromContextId(payload);
    }
  }

  void _openPatternFromMessageData(Map<String, dynamic> data) {
    final id = data['context_id'] as String?;
    _openPatternFromContextId(id);
  }

  void _openPatternFromContextId(String? contextId) {
    final slug = insightIdFromContextId(contextId);
    if (slug == null || slug.isEmpty) {
      return;
    }
    final nav = _navigatorKey?.currentState;
    if (nav == null) {
      return;
    }
    nav.push(
      MaterialPageRoute<void>(
        builder: (_) => PatternDetailScreen(insightId: slug),
      ),
    );
  }
}
