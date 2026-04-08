import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:provider/provider.dart';

import '../models/insight_preview.dart';
import '../state/session_controller.dart';

/// Lists discovery patterns from `GET /api/insights`.
class PatternBrowserScreen extends StatefulWidget {
  const PatternBrowserScreen({super.key});

  @override
  State<PatternBrowserScreen> createState() => _PatternBrowserScreenState();
}

class _PatternBrowserScreenState extends State<PatternBrowserScreen> {
  List<Map<String, dynamic>> _rows = [];
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _load());
  }

  Future<void> _load() async {
    final client = context.read<SessionController>().apiClient;
    if (client == null) {
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final raw = await client.listInsights();
      setState(() {
        _rows = raw
            .map((e) => Map<String, dynamic>.from(e as Map))
            .toList();
        _loading = false;
      });
    } catch (e) {
      setState(() {
        _loading = false;
        _error = SessionController.describeDioError(e);
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Patterns'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _loading ? null : _load,
          ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? Center(
                  child: Padding(
                    padding: const EdgeInsets.all(24),
                    child: Text(_error!, textAlign: TextAlign.center),
                  ),
                )
              : _rows.isEmpty
                  ? const Center(
                      child: Text('No patterns yet — run discovery on the server.'),
                    )
                  : ListView.separated(
                      itemCount: _rows.length,
                      separatorBuilder: (_, __) => const Divider(height: 1),
                      itemBuilder: (context, i) {
                        final row = _rows[i];
                        final id = row['id'] as String? ?? '';
                        final title = row['title'] as String? ?? id;
                        final status = row['status'] as String? ?? '';
                        return ListTile(
                          title: Text(title),
                          subtitle: Text('$id · $status'),
                          onTap: () {
                            Navigator.push<void>(
                              context,
                              MaterialPageRoute<void>(
                                builder: (_) => PatternDetailScreen(insightId: id),
                              ),
                            );
                          },
                        );
                      },
                    ),
    );
  }
}

/// Shows one pattern from `GET /api/insights/{id}`.
class PatternDetailScreen extends StatefulWidget {
  const PatternDetailScreen({super.key, required this.insightId});

  final String insightId;

  @override
  State<PatternDetailScreen> createState() => _PatternDetailScreenState();
}

class _PatternDetailScreenState extends State<PatternDetailScreen> {
  InsightPreview? _insight;
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _load());
  }

  Future<void> _load() async {
    final client = context.read<SessionController>().apiClient;
    if (client == null) {
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final json = await client.getInsight(widget.insightId);
      setState(() {
        _insight = InsightPreview.fromDetailJson(json);
        _loading = false;
      });
    } catch (e) {
      setState(() {
        _loading = false;
        _insight = null;
        if (e is DioException && e.response?.statusCode == 404) {
          _error = 'No pattern for ${widget.insightId}.';
        } else {
          _error = SessionController.describeDioError(e);
        }
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(_insight?.title ?? widget.insightId),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _loading ? null : _load,
          ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? Center(
                  child: Padding(
                    padding: const EdgeInsets.all(24),
                    child: Text(_error!, textAlign: TextAlign.center),
                  ),
                )
              : _insight == null
                  ? const SizedBox.shrink()
                  : ListView(
                      padding: const EdgeInsets.all(16),
                      children: [
                        MarkdownBody(
                          data: _insight!.markdown,
                          shrinkWrap: true,
                        ),
                      ],
                    ),
    );
  }
}
