import 'package:flutter_test/flutter_test.dart';
import 'package:pulse_companion/models/insight_preview.dart';

void main() {
  test('InsightPreview.fromDetailJson parses API shape', () {
    final d = InsightPreview.fromDetailJson({
      'id': 'late-work',
      'title': 'Late work',
      'markdown': '# Late work\n\nHello.',
    });
    expect(d.id, 'late-work');
    expect(d.title, 'Late work');
    expect(d.markdown, '# Late work\n\nHello.');
  });
}
