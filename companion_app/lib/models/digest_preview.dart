class DigestPreview {
  const DigestPreview({required this.date, required this.markdown});

  final String date;
  final String markdown;

  factory DigestPreview.fromJson(Map<String, dynamic> json) {
    return DigestPreview(
      date: json['date'] as String? ?? '',
      markdown: json['markdown'] as String? ?? '',
    );
  }
}
