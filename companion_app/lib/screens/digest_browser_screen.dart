import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';

import '../models/digest_preview.dart';
import '../state/session_controller.dart';

class DigestBrowserScreen extends StatefulWidget {
  const DigestBrowserScreen({super.key});

  @override
  State<DigestBrowserScreen> createState() => _DigestBrowserScreenState();
}

class _DigestBrowserScreenState extends State<DigestBrowserScreen> {
  DateTime _selected = DateTime.now();
  DigestPreview? _digest;
  bool _loading = false;
  String? _error;

  String get _slug => DateFormat('yyyy-MM-dd').format(_selected);

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _load());
  }

  Future<void> _pickDate() async {
    final picked = await showDatePicker(
      context: context,
      initialDate: _selected,
      firstDate: DateTime(2020),
      lastDate: DateTime.now(),
    );
    if (picked != null) {
      setState(() => _selected = picked);
      await _load();
    }
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
      final json = await client.getDigest(_slug);
      setState(() {
        _digest = DigestPreview.fromJson(json);
        _loading = false;
      });
    } catch (e) {
      setState(() {
        _loading = false;
        _digest = null;
        if (e is DioException && e.response?.statusCode == 404) {
          _error = 'No digest for $_slug.';
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
        title: Text('Digest · $_slug'),
        actions: [
          IconButton(
            icon: const Icon(Icons.date_range),
            onPressed: _pickDate,
          ),
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
              : _digest == null
                  ? const SizedBox.shrink()
                  : ListView(
                      padding: const EdgeInsets.all(16),
                      children: [
                        MarkdownBody(
                          data: _digest!.markdown,
                          shrinkWrap: true,
                        ),
                      ],
                    ),
    );
  }
}
