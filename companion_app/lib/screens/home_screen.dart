import 'dart:async';

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:provider/provider.dart';

import '../app_navigator.dart';
import '../models/digest_preview.dart';
import '../services/companion_sensor_coordinator.dart';
import '../services/push_notifications.dart';
import '../state/session_controller.dart';
import 'digest_browser_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> with WidgetsBindingObserver {
  DigestPreview? _digest;
  bool _loading = true;
  String? _loadError;
  final _correctionCtrl = TextEditingController();
  bool _submitting = false;
  String? _submitMessage;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      await _refresh();
      if (!mounted) {
        return;
      }
      final api = context.read<SessionController>().apiClient;
      if (api != null) {
        await PushNotificationsCoordinator.instance.start(
          navigatorKey: pulseNavigatorKey,
          apiClient: api,
        );
        await CompanionSensorCoordinator.instance.start(api);
      }
    });
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    CompanionSensorCoordinator.instance.stop();
    PushNotificationsCoordinator.instance.stop();
    _correctionCtrl.dispose();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      unawaited(CompanionSensorCoordinator.instance.onResume());
    }
  }

  Future<void> _refresh() async {
    final client = context.read<SessionController>().apiClient;
    if (client == null) {
      return;
    }
    setState(() {
      _loading = true;
      _loadError = null;
    });
    try {
      final json = await client.getLatestDigest();
      setState(() {
        _digest = DigestPreview.fromJson(json);
        _loading = false;
      });
    } catch (e) {
      setState(() {
        _loading = false;
        _digest = null;
        if (e is DioException && e.response?.statusCode == 404) {
          _loadError = 'No digest yet — run a digest on the server.';
        } else {
          _loadError = SessionController.describeDioError(e);
        }
      });
    }
  }

  Future<void> _submitCorrection() async {
    final text = _correctionCtrl.text.trim();
    if (text.isEmpty) {
      return;
    }
    final digest = _digest;
    if (digest == null || digest.date.isEmpty) {
      return;
    }
    final client = context.read<SessionController>().apiClient;
    if (client == null) {
      return;
    }
    setState(() {
      _submitting = true;
      _submitMessage = null;
    });
    try {
      await client.submitCorrection(
        contextId: digest.date,
        messageText: text,
      );
      _correctionCtrl.clear();
      if (mounted) {
        setState(() {
          _submitMessage = 'Correction sent.';
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _submitMessage = SessionController.describeDioError(e);
        });
      }
    } finally {
      if (mounted) {
        setState(() => _submitting = false);
      }
    }
  }

  Future<void> _openSettings() async {
    final session = context.read<SessionController>();
    final signOut = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Server'),
        content: const Text('Sign out and change URL or token?'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Sign out'),
          ),
        ],
      ),
    );
    if (signOut == true && context.mounted) {
      await session.signOut();
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Pulse'),
        actions: [
          IconButton(
            icon: const Icon(Icons.calendar_month),
            onPressed: () async {
              await Navigator.push<void>(
                context,
                MaterialPageRoute<void>(
                  builder: (_) => const DigestBrowserScreen(),
                ),
              );
              if (context.mounted) {
                await _refresh();
              }
            },
          ),
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _loading ? null : _refresh,
          ),
          IconButton(
            icon: const Icon(Icons.logout),
            onPressed: _openSettings,
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _refresh,
        child: CustomScrollView(
          physics: const AlwaysScrollableScrollPhysics(),
          slivers: [
            if (_loading)
              const SliverFillRemaining(
                child: Center(child: CircularProgressIndicator()),
              )
            else if (_loadError != null)
              SliverFillRemaining(
                child: Center(
                  child: Padding(
                    padding: const EdgeInsets.all(24),
                    child: Text(
                      _loadError!,
                      textAlign: TextAlign.center,
                    ),
                  ),
                ),
              )
            else if (_digest != null)
              SliverToBoxAdapter(
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Text(
                        _digest!.date,
                        style: Theme.of(context).textTheme.titleMedium,
                      ),
                      const SizedBox(height: 8),
                      MarkdownBody(
                        data: _digest!.markdown,
                        shrinkWrap: true,
                      ),
                      const Divider(height: 32),
                      Text(
                        'Correction',
                        style: Theme.of(context).textTheme.titleSmall,
                      ),
                      const SizedBox(height: 8),
                      TextField(
                        controller: _correctionCtrl,
                        decoration: const InputDecoration(
                          hintText: 'Applies to this digest date',
                          border: OutlineInputBorder(),
                        ),
                        minLines: 2,
                        maxLines: 4,
                        textCapitalization: TextCapitalization.sentences,
                      ),
                      if (_submitMessage != null) ...[
                        const SizedBox(height: 8),
                        Text(_submitMessage!),
                      ],
                      const SizedBox(height: 12),
                      FilledButton(
                        onPressed: _submitting ? null : _submitCorrection,
                        child: _submitting
                            ? const SizedBox(
                                height: 22,
                                width: 22,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                ),
                              )
                            : const Text('Send correction'),
                      ),
                      const SizedBox(height: 32),
                    ],
                  ),
                ),
              )
            else
              const SliverFillRemaining(
                child: Center(child: Text('Nothing to show')),
              ),
          ],
        ),
      ),
    );
  }
}
