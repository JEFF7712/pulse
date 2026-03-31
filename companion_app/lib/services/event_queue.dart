import 'dart:convert';

import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';
import 'package:sqflite/sqflite.dart';
import 'package:uuid/uuid.dart';

import 'pulse_api_client.dart';

/// Persists companion events locally until POST /webhooks/companion succeeds.
class EventQueue {
  EventQueue({Database? database}) : _dbOverride = database;

  final Database? _dbOverride;
  Database? _db;

  static const _table = 'companion_event_queue';

  Future<Database> _open() async {
    final overrideDb = _dbOverride;
    if (overrideDb != null) {
      return overrideDb;
    }
    final cached = _db;
    if (cached != null) {
      return cached;
    }
    final dir = await getApplicationDocumentsDirectory();
    final path = p.join(dir.path, 'pulse_companion_events.db');
    _db = await openDatabase(
      path,
      version: 1,
      onCreate: (db, version) async {
        await db.execute('''
          CREATE TABLE $_table (
            id TEXT PRIMARY KEY NOT NULL,
            payload TEXT NOT NULL,
            created_at INTEGER NOT NULL
          )
        ''');
      },
    );
    return _db!;
  }

  Future<void> enqueue(Map<String, dynamic> event) async {
    final db = await _open();
    final id = const Uuid().v4();
    await db.insert(_table, {
      'id': id,
      'payload': jsonEncode(event),
      'created_at': DateTime.now().millisecondsSinceEpoch,
    });
  }

  Future<int> pendingCount() async {
    final db = await _open();
    final rows = await db.rawQuery(
      'SELECT COUNT(*) as c FROM $_table',
    );
    final c = rows.first['c'];
    if (c is int) {
      return c;
    }
    return (c as num?)?.toInt() ?? 0;
  }

  /// Sends queued events in batches; removes rows on success.
  Future<void> flush(PulseApiClient client) async {
    final db = await _open();
    final rows = await db.query(
      _table,
      orderBy: 'created_at ASC',
    );
    if (rows.isEmpty) {
      return;
    }

    final events = <Map<String, dynamic>>[];
    final ids = <String>[];
    for (final row in rows) {
      final id = row['id'] as String?;
      final raw = row['payload'] as String?;
      if (id == null || raw == null) {
        continue;
      }
      final decoded = jsonDecode(raw);
      if (decoded is Map<String, dynamic>) {
        events.add(decoded);
        ids.add(id);
      }
    }
    if (events.isEmpty) {
      return;
    }

    await client.postCompanionEvents(events);
    final batch = db.batch();
    for (final id in ids) {
      batch.delete(_table, where: 'id = ?', whereArgs: [id]);
    }
    await batch.commit(noResult: true);
  }
}
