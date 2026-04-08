/// Normalizes Pulse notification [context_id] values for pattern browsing.
String? insightIdFromContextId(String? raw) {
  if (raw == null) {
    return null;
  }
  final s = raw.trim();
  if (s.isEmpty) {
    return null;
  }
  if (s.startsWith('pattern:')) {
    return s.substring('pattern:'.length).trim();
  }
  return s;
}
