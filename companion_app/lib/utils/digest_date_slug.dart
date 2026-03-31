/// Parses `yyyy-MM-dd` digest filenames / notification [context_id] values.
DateTime? parseDigestDateSlug(String? slug) {
  if (slug == null || slug.isEmpty) {
    return null;
  }
  final parts = slug.split('-');
  if (parts.length != 3) {
    return null;
  }
  try {
    final y = int.parse(parts[0]);
    final m = int.parse(parts[1]);
    final d = int.parse(parts[2]);
    return DateTime(y, m, d);
  } on FormatException {
    return null;
  }
}
