import 'package:flutter_test/flutter_test.dart';
import 'package:pulse_companion/utils/digest_date_slug.dart';

void main() {
  test('parseDigestDateSlug accepts yyyy-MM-dd', () {
    expect(parseDigestDateSlug('2026-03-27'), DateTime(2026, 3, 27));
  });

  test('parseDigestDateSlug returns null for invalid input', () {
    expect(parseDigestDateSlug(null), isNull);
    expect(parseDigestDateSlug(''), isNull);
    expect(parseDigestDateSlug('bad'), isNull);
    expect(parseDigestDateSlug('2026-xx-01'), isNull);
  });
}
