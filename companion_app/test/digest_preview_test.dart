import 'package:flutter_test/flutter_test.dart';
import 'package:pulse_companion/models/digest_preview.dart';

void main() {
  test('DigestPreview.fromJson parses API shape', () {
    final d = DigestPreview.fromJson({
      'date': '2026-03-27',
      'markdown': '# Daily\n\nHello.',
    });
    expect(d.date, '2026-03-27');
    expect(d.markdown, '# Daily\n\nHello.');
  });
}
