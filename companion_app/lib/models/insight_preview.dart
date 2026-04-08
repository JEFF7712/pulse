class InsightPreview {
  const InsightPreview({
    required this.id,
    required this.title,
    required this.markdown,
  });

  final String id;
  final String title;
  final String markdown;

  factory InsightPreview.fromDetailJson(Map<String, dynamic> json) {
    return InsightPreview(
      id: json['id'] as String? ?? '',
      title: json['title'] as String? ?? '',
      markdown: json['markdown'] as String? ?? '',
    );
  }
}
