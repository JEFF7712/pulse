import 'package:intl/intl.dart';

/// UTC ISO-8601 for Pulse companion webhook `timestamp` fields.
String companionTimestampIsoUtc(DateTime dt) => dt.toUtc().toIso8601String();

/// `health.steps` for a completed local calendar day (timestamp end-of-day local → UTC).
Map<String, dynamic> buildStepsEventForLocalDay(DateTime localDay, int stepCount) {
  final endLocal = DateTime(
    localDay.year,
    localDay.month,
    localDay.day,
    23,
    59,
    59,
  );
  return {
    'type': 'health.steps',
    'timestamp': companionTimestampIsoUtc(endLocal),
    'data': {'count': stepCount},
  };
}

String stepsSentPrefsKeyForLocalDay(DateTime localDay) {
  return 'companion_sent_steps_${DateFormat('yyyy-MM-dd').format(localDay)}';
}
