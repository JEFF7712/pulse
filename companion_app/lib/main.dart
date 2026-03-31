import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'app_navigator.dart';
import 'screens/home_screen.dart';
import 'screens/setup_screen.dart';
import 'services/push_notifications.dart';
import 'state/session_controller.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  FirebaseMessaging.onBackgroundMessage(firebaseMessagingBackgroundHandler);
  runApp(
    ChangeNotifierProvider(
      create: (_) {
        final session = SessionController();
        session.load();
        return session;
      },
      child: const PulseCompanionApp(),
    ),
  );
}

class PulseCompanionApp extends StatelessWidget {
  const PulseCompanionApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      navigatorKey: pulseNavigatorKey,
      title: 'Pulse Companion',
      theme: ThemeData(
        colorSchemeSeed: Colors.teal,
        useMaterial3: true,
      ),
      home: const _Root(),
    );
  }
}

class _Root extends StatelessWidget {
  const _Root();

  @override
  Widget build(BuildContext context) {
    return Consumer<SessionController>(
      builder: (context, session, _) {
        if (!session.ready) {
          return const Scaffold(
            body: Center(child: CircularProgressIndicator()),
          );
        }
        if (!session.isConfigured) {
          return const SetupScreen();
        }
        return const HomeScreen();
      },
    );
  }
}
