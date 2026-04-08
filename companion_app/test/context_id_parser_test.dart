import 'package:flutter_test/flutter_test.dart';
import 'package:pulse_companion/utils/context_id_parser.dart';

void main() {
  test('insightIdFromContextId strips pattern prefix', () {
    expect(insightIdFromContextId('pattern:foo-bar'), 'foo-bar');
    expect(insightIdFromContextId('  pattern: x '), 'x');
  });

  test('insightIdFromContextId passes through bare slugs', () {
    expect(insightIdFromContextId('foo-bar'), 'foo-bar');
  });

  test('insightIdFromContextId handles empty', () {
    expect(insightIdFromContextId(null), isNull);
    expect(insightIdFromContextId(''), isNull);
    expect(insightIdFromContextId('   '), isNull);
  });
}
