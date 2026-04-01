import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:health/health.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'companion_event_builders.dart';
import 'event_queue.dart';

/// Reads steps (completed local days) and sleep sessions from HealthKit / Health Connect.
class HealthIngestionService {
  HealthIngestionService({Health? health}) : _health = health ?? Health();

  final Health _health;

  static const _prefsSleepSent = 'companion_sent_sleep_session_end_ids';

  Future<void> collectAndEnqueue(EventQueue queue) async {
    if (kIsWeb) {
      return;
    }
    if (!Platform.isIOS && !Platform.isAndroid) {
      return;
    }

    try {
      await _health.configure();
    } catch (e, st) {
      debugPrint('HealthIngestion: configure failed: $e\n$st');
      return;
    }

    if (Platform.isAndroid) {
      try {
        if (!await _health.isHealthConnectAvailable()) {
          debugPrint('HealthIngestion: Health Connect not available.');
          return;
        }
      } catch (e) {
        debugPrint('HealthIngestion: Health Connect check failed: $e');
        return;
      }
    }

    const types = [
      HealthDataType.STEPS,
      HealthDataType.SLEEP_IN_BED,
      HealthDataType.SLEEP_ASLEEP,
    ];
    try {
      await _health.requestAuthorization(
        types,
        permissions: List.filled(types.length, HealthDataAccess.READ),
      );
    } catch (e) {
      debugPrint('HealthIngestion: requestAuthorization failed: $e');
    }

    final prefs = await SharedPreferences.getInstance();
    final now = DateTime.now();

    try {
      await _syncStepsForCompletedDays(queue, prefs, now);
    } catch (e, st) {
      debugPrint('HealthIngestion: steps sync failed: $e\n$st');
    }

    try {
      await _syncSleepSessions(queue, prefs, now);
    } catch (e, st) {
      debugPrint('HealthIngestion: sleep sync failed: $e\n$st');
    }
  }

  Future<void> _syncStepsForCompletedDays(
    EventQueue queue,
    SharedPreferences prefs,
    DateTime now,
  ) async {
    final todayStart = DateTime(now.year, now.month, now.day);
    for (var i = 1; i <= 7; i++) {
      final day = todayStart.subtract(Duration(days: i));
      final key = stepsSentPrefsKeyForLocalDay(day);
      if (prefs.getBool(key) == true) {
        continue;
      }

      final start = DateTime(day.year, day.month, day.day);
      final end = DateTime(day.year, day.month, day.day, 23, 59, 59, 999);

      final total = await _health.getTotalStepsInInterval(start, end);
      if (total == null || total <= 0) {
        continue;
      }

      await queue.enqueue(buildStepsEventForLocalDay(day, total));
      await prefs.setBool(key, true);
    }
  }

  Future<void> _syncSleepSessions(
    EventQueue queue,
    SharedPreferences prefs,
    DateTime now,
  ) async {
    final end = now;
    final start = end.subtract(const Duration(days: 6));

    final inBed = await _health.getHealthDataFromTypes(
      types: [HealthDataType.SLEEP_IN_BED],
      startTime: start,
      endTime: end,
    );
    if (inBed.isEmpty) {
      return;
    }

    inBed.sort((a, b) => a.dateFrom.compareTo(b.dateFrom));

    final merged = <_MergedSleep>[];
    for (final p in inBed) {
      if (merged.isEmpty) {
        merged.add(_MergedSleep(p.dateFrom, p.dateTo));
        continue;
      }
      final last = merged.last;
      if (p.dateFrom.difference(last.end) <= const Duration(hours: 2)) {
        last.end = p.dateTo.isAfter(last.end) ? p.dateTo : last.end;
      } else {
        merged.add(_MergedSleep(p.dateFrom, p.dateTo));
      }
    }

    final asleepPoints = await _health.getHealthDataFromTypes(
      types: [HealthDataType.SLEEP_ASLEEP],
      startTime: start,
      endTime: end,
    );

    var sent = prefs.getStringList(_prefsSleepSent) ?? <String>[];

    for (final s in merged) {
      final inBedMin = s.end.difference(s.start).inMinutes;
      if (inBedMin < 90) {
        continue;
      }

      final id = s.end.toUtc().millisecondsSinceEpoch.toString();
      if (sent.contains(id)) {
        continue;
      }

      var asleepMin = 0;
      for (final ap in asleepPoints) {
        asleepMin += _overlapMinutes(s.start, s.end, ap.dateFrom, ap.dateTo);
      }
      if (asleepMin <= 0) {
        asleepMin = (inBedMin * 0.85).round();
      }
      if (asleepMin > inBedMin) {
        asleepMin = inBedMin;
      }

      await queue.enqueue({
        'type': 'health.sleep',
        'timestamp': companionTimestampIsoUtc(s.end),
        'data': {
          'in_bed_minutes': inBedMin,
          'asleep_minutes': asleepMin,
        },
      });

      sent = [...sent, id];
      while (sent.length > 48) {
        sent = sent.sublist(sent.length - 48);
      }
    }

    await prefs.setStringList(_prefsSleepSent, sent);
  }
}

int _overlapMinutes(
  DateTime a0,
  DateTime a1,
  DateTime b0,
  DateTime b1,
) {
  final s = a0.isAfter(b0) ? a0 : b0;
  final e = a1.isBefore(b1) ? a1 : b1;
  if (!e.isAfter(s)) {
    return 0;
  }
  return e.difference(s).inMinutes;
}

class _MergedSleep {
  _MergedSleep(this.start, this.end);

  DateTime start;
  DateTime end;
}
