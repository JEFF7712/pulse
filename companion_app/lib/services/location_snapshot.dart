import 'package:flutter/foundation.dart';
import 'package:geolocator/geolocator.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'companion_event_builders.dart';
import 'event_queue.dart';

/// Enqueues a throttled `location.enter` snapshot (design: app-as-connector).
class LocationSnapshotService {
  static const _prefsLastMs = 'companion_last_location_snapshot_ms';
  static const _minInterval = Duration(minutes: 25);

  Future<void> maybeEnqueue(EventQueue queue) async {
    if (kIsWeb) {
      return;
    }
    if (defaultTargetPlatform != TargetPlatform.iOS &&
        defaultTargetPlatform != TargetPlatform.android) {
      return;
    }

    final prefs = await SharedPreferences.getInstance();
    final nowMs = DateTime.now().millisecondsSinceEpoch;
    final last = prefs.getInt(_prefsLastMs) ?? 0;
    if (nowMs - last < _minInterval.inMilliseconds) {
      return;
    }

    try {
      var perm = await Geolocator.checkPermission();
      if (perm == LocationPermission.denied) {
        perm = await Geolocator.requestPermission();
      }
      if (perm == LocationPermission.denied ||
          perm == LocationPermission.deniedForever) {
        return;
      }

      final pos = await Geolocator.getCurrentPosition();
      await queue.enqueue({
        'type': 'location.enter',
        'timestamp': companionTimestampIsoUtc(DateTime.now()),
        'data': {
          'place': 'snapshot',
          'lat': pos.latitude,
          'lng': pos.longitude,
        },
      });
      await prefs.setInt(_prefsLastMs, nowMs);
    } catch (e) {
      debugPrint('LocationSnapshot: $e');
    }
  }
}
