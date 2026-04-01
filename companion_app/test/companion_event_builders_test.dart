import 'package:flutter_test/flutter_test.dart';
import 'package:pulse_companion/services/companion_event_builders.dart';

void main() {
  test('buildStepsEventForLocalDay uses end-of-local-day as UTC ISO-8601', () {
    final day = DateTime(2026, 3, 27);
    final ev = buildStepsEventForLocalDay(day, 8420);
    expect(ev['type'], 'health.steps');
    expect(ev['data'], {'count': 8420});
    final ts = DateTime.parse(ev['timestamp'] as String);
    expect(ts.isUtc, isTrue);
    final endLocal = DateTime(2026, 3, 27, 23, 59, 59);
    expect(ts.difference(endLocal.toUtc()).inSeconds.abs() <= 1, isTrue);
  });

  test('stepsSentPrefsKeyForLocalDay is stable', () {
    expect(
      stepsSentPrefsKeyForLocalDay(DateTime(2026, 1, 5)),
      'companion_sent_steps_2026-01-05',
    );
  });
}
