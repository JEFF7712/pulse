import 'dart:async';

import 'package:flutter/foundation.dart';

import 'event_queue.dart';
import 'health_ingestion.dart';
import 'location_snapshot.dart';
import 'pulse_api_client.dart';

/// Runs health + location ingestion into [EventQueue] and flushes to Pulse periodically.
class CompanionSensorCoordinator {
  CompanionSensorCoordinator._();
  static final CompanionSensorCoordinator instance =
      CompanionSensorCoordinator._();

  final EventQueue _queue = EventQueue();
  final HealthIngestionService _health = HealthIngestionService();
  final LocationSnapshotService _location = LocationSnapshotService();

  PulseApiClient? _api;
  Timer? _flushTimer;

  Future<void> start(PulseApiClient api) async {
    if (_api != null) {
      return;
    }
    _api = api;
    _flushTimer = Timer.periodic(const Duration(minutes: 5), (_) {
      unawaited(_flush());
    });
    await onResume();
  }

  Future<void> stop() async {
    _flushTimer?.cancel();
    _flushTimer = null;
    _api = null;
  }

  Future<void> onResume() async {
    final api = _api;
    if (api == null) {
      return;
    }
    await _health.collectAndEnqueue(_queue);
    await _location.maybeEnqueue(_queue);
    await _flush();
  }

  Future<void> _flush() async {
    final api = _api;
    if (api == null) {
      return;
    }
    try {
      await _queue.flush(api);
    } catch (e) {
      debugPrint('CompanionSensorCoordinator: flush failed: $e');
    }
  }
}
