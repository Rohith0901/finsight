// The app's state and use cases. Screens read from here and call its methods.

import 'dart:async';
import 'dart:math';

import 'package:flutter/foundation.dart';

import '../api/api_client.dart';
import '../core/money.dart';
import '../core/rules.dart';
import '../data/models.dart';
import '../data/repository.dart';
import '../ingestion/pipeline.dart';
import '../ingestion/sms_source.dart';

class ChatTurn {
  ChatTurn(this.question, {this.answer, this.facts = const [], this.error, this.provider});
  final String question;
  String? answer;
  List<Map<String, dynamic>> facts;
  String? error;
  String? provider;
}

class AppState extends ChangeNotifier {
  AppState({
    required this.repo,
    required this.pipeline,
    required this.rules,
    this.inbox,
    this.demoJsonl,
    ApiClient Function(ServerConfig)? clientFactory,
  }) : _clientFactory = clientFactory ?? ((c) => ApiClient(c));

  final Repository repo;
  final IngestionPipeline pipeline;
  final SharedRules rules;
  final InboxSmsSource? inbox;
  final Future<String> Function()? demoJsonl;
  final ApiClient Function(ServerConfig) _clientFactory;

  List<Txn> transactions = [];
  Map<String, dynamic>? insights;
  DateTime? insightsAt;
  String? status; // one-line message for the UI
  bool busy = false;
  bool consented = false;
  bool hasSmsPermission = false;
  ServerConfig server = const ServerConfig(baseUrl: '', token: '', fingerprint: '');
  int? manualBalancePaise;
  int? smsBalancePaise;
  int savingsTargetPaise = 0;
  String assistantProvider = 'auto';
  final List<ChatTurn> chat = [];
  StreamSubscription<void>? _inboxWatch;
  Timer? _debounce;

  int? get balancePaise => manualBalancePaise ?? smsBalancePaise;

  ApiClient? _client;
  ServerConfig? _clientConfig;

  ApiClient? get _api {
    if (!server.isComplete) return null;
    if (_client == null || !identical(_clientConfig, server)) {
      _client?.close();
      _client = _clientFactory(server);
      _clientConfig = server;
    }
    return _client;
  }

  Future<void> load() async {
    consented = await repo.setting('consent_ts') != null;
    server = ServerConfig(
      baseUrl: await repo.setting('server_url') ?? '',
      token: await repo.setting('server_token') ?? '',
      fingerprint: await repo.setting('server_fingerprint') ?? '',
    );
    manualBalancePaise = int.tryParse(await repo.setting('manual_balance') ?? '');
    savingsTargetPaise = int.tryParse(await repo.setting('savings_target') ?? '') ?? 0;
    assistantProvider = await repo.setting('assistant_provider') ?? 'auto';
    final cached = await repo.cached('insights');
    if (cached != null) {
      insights = cached.$1;
      insightsAt = cached.$2;
    }
    if (inbox != null) hasSmsPermission = await inbox!.hasPermission();
    await _reload();
  }

  Future<void> _reload() async {
    transactions = await repo.recent();
    smsBalancePaise = await repo.knownBalance();
    notifyListeners();
  }

  Future<void> _run(String label, Future<void> Function() work) async {
    busy = true;
    status = label;
    notifyListeners();
    try {
      await work();
    } on ApiException catch (e) {
      status = e.message;
    } catch (e) {
      // Errors and exceptions alike: a bad response must not crash a tap.
      status = 'Something went wrong: ${e.runtimeType}';
    } finally {
      busy = false;
      await _reload();
    }
  }

  // ------------------------------------------------------------ consent, SMS

  Future<void> giveConsent() async {
    await repo.setSetting('consent_ts', DateTime.now().toIso8601String());
    consented = true;
    if (inbox != null) hasSmsPermission = await inbox!.requestPermission();
    notifyListeners();
    if (hasSmsPermission) {
      watchInbox();
      await scanInbox();
    }
  }

  void watchInbox() {
    if (inbox == null || !hasSmsPermission || _inboxWatch != null) return;
    _inboxWatch = inbox!.changes.listen((_) {
      _debounce?.cancel();
      _debounce = Timer(const Duration(seconds: 2), () => scanInbox(quiet: true));
    });
  }

  Future<void> scanInbox({bool quiet = false}) async {
    if (inbox == null || !consented || !hasSmsPermission || busy) return;
    await _run(quiet ? 'Checking for new messages' : 'Reading bank messages', () async {
      final counts = await pipeline.syncFrom(inbox!);
      final added = counts[IngestStatus.inserted] ?? 0;
      status = added == 0 ? 'No new transactions' : 'Added $added transactions';
      if (added > 0) await _afterNewData();
    });
  }

  Future<void> loadDemo() async {
    if (demoJsonl == null) return;
    await _run('Loading demo data', () async {
      final counts = await pipeline.syncFrom(DemoSmsSource(await demoJsonl!()), tag: 'demo');
      status = 'Demo: ${counts[IngestStatus.inserted]} transactions, '
          '${counts[IngestStatus.rejected]} messages correctly ignored';
      await _afterNewData();
    });
  }

  Future<void> _afterNewData() async {
    final api = _api;
    if (api == null) return;
    await _categorizeIfPossible(api);
    await _refreshInsights(api);
  }

  // ------------------------------------------------------------ backend

  Future<void> _categorize(ApiClient api) async {
    final pending = await repo.pending();
    if (pending.isEmpty) return;
    for (final r in await api.classify(pending)) {
      final abstained = r['abstained'] == true;
      await repo.setCategory(int.parse(r['id'] as String), abstained ? 'unknown' : r['category'] as String,
          abstained ? 'unknown' : 'model', (r['confidence'] as num).toDouble());
    }
  }

  /// The model being unavailable (no trained model on the server) leaves
  /// those rows pending; insights still work from the rule-based categories.
  Future<void> _categorizeIfPossible(ApiClient api) async {
    try {
      await _categorize(api);
    } on ApiException catch (e) {
      if (e.code != 'model_unavailable') rethrow;
    }
  }

  Future<List<Txn>> _window() =>
      repo.since(DateTime.now().subtract(const Duration(days: 120)));

  Future<void> _refreshInsights(ApiClient api) async {
    final result = await api.insights(await _window(), DateTime.now(),
        balancePaise: balancePaise, savingsTargetPaise: savingsTargetPaise);
    await repo.cache('insights', result);
    insights = result;
    insightsAt = DateTime.now();
    status = 'Updated';
  }

  Future<void> refresh() async {
    final api = _api;
    if (api == null) {
      status = 'Add the server address, token and certificate fingerprint in Settings';
      notifyListeners();
      return;
    }
    await _run('Updating insights', () async {
      await _categorizeIfPossible(api);
      await _refreshInsights(api);
    });
  }

  Future<String> testConnection() async {
    final api = _api;
    if (api == null) return 'Fill in all three server fields first.';
    return await api.health() ? 'Connected' : 'Could not reach the server or the certificate did not match.';
  }

  Future<void> ask(String question) async {
    final turn = ChatTurn(question);
    chat.add(turn);
    notifyListeners();
    final api = _api;
    if (api == null) {
      turn.error = 'Connect to the server in Settings to ask questions.';
      notifyListeners();
      return;
    }
    try {
      final r = await api.chat(question, await _window(), DateTime.now(),
          balancePaise: balancePaise, savingsTargetPaise: savingsTargetPaise,
          provider: assistantProvider);
      turn.answer = r['answer'] as String;
      turn.facts = (r['facts'] as List).cast<Map<String, dynamic>>();
      turn.provider = r['provider_used'] as String?;
    } on ApiException catch (e) {
      turn.error = e.message;
    } catch (e) {
      turn.error = 'Something went wrong (${e.runtimeType}).';
    }
    notifyListeners();
  }

  // ------------------------------------------------------------ test messages

  /// Ready-made bank messages dated now, with fresh reference numbers. The
  /// first debits the account whose balance the app knows, so the balance
  /// drops by exactly the amount. Each is (label, sender, body).
  Future<List<(String, String, String)>> sampleMessages() async {
    final now = DateTime.now();
    String two(int n) => n.toString().padLeft(2, '0');
    const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    final yy = two(now.year % 100);
    final dashed = '${two(now.day)}-${two(now.month)}-$yy';
    final r = Random();
    String ref() => '5${List.generate(11, (_) => r.nextInt(10)).join()}';
    final acct = await repo.latestSavingsAccount();
    final mask = acct?.mask ?? '4821';
    final balance = acct == null || acct.balancePaise < 25000
        ? ''
        : ' Avl bal Rs ${rupees(acct.balancePaise - 25000, decimals: true).replaceAll('₹', '')}.';
    return [
      ('₹250 UPI payment to Swiggy', 'VM-HDFCBK',
          'Money Sent! Rs 250.00 from HDFC Bank A/c **$mask to SWIGGY on $dashed. '
              'UPI Ref No ${ref()}.$balance Not you? Call 18000000000'),
      ('₹180 debit card at Chaayos', 'JM-ATMSBI',
          'Dear Customer, your SBI Debit Card ending 8954 was used for Rs.180.00 at Chaayos on '
              '${two(now.day)}/${two(now.month)}/$yy. If not done by you, call 1800000000 -SBI'),
      ('₹500 received from a friend', 'AD-KOTAKB-S',
          'Received Rs.500.00 in your Kotak Bank AC X2802 from RAHUL SINGH on $dashed.UPI Ref:${ref()}.'),
      ('₹90 UPI to a person, with bank remarks', 'JM-ATMSBI',
          'Dear UPI user A/C X9174 debited by 90.0 on date ${two(now.day)}${months[now.month - 1]}$yy '
              'trf to J JOTHIMANI Info:P2A/${ref()} Refno ${ref()}. If not u? call 1800000000. -SBI'),
      ('OTP (should be ignored)', 'VM-HDFCBK',
          '${100000 + r.nextInt(900000)} is your OTP for a transaction of Rs 250.00 at SWIGGY. '
              'Do not share it with anyone. -HDFC Bank'),
    ];
  }

  static const _reasons = {
    'otp': 'it is a one-time password',
    'promo': 'it is an offer',
    'declined': 'the payment failed',
    'request': 'it is a payment request, not a payment',
    'future': 'it is a reminder of a future payment',
  };

  /// Runs a message through the same steps as an SMS that just arrived
  /// (parser, rules, duplicate check) and says what happened.
  Future<String> simulateSms(String sender, String body) async {
    final s = sender.trim();
    final b = body.trim();
    if (s.isEmpty || b.isEmpty) return 'Enter a sender and a message.';
    final before = balancePaise;
    final parsed = pipeline.parser.parse(s, b);
    final status = await pipeline.ingest(SmsMessage(s, b, DateTime.now()), source: 'test');
    await _reload();
    switch (status) {
      case IngestStatus.inserted:
        final t = await repo.lastInserted();
        if (t == null) return 'Recorded.';
        final verb = t.direction == 'debit' ? 'Debited' : 'Credited';
        final category =
            t.categorySource == 'pending' ? 'waiting for a category' : rules.categoryName(t.categoryId);
        var msg = '$verb ${rupees(t.amountPaise, decimals: true)}: ${t.displayName}, $category.';
        final after = balancePaise;
        if (after != null && after != before) {
          msg += before == null
              ? '\nBalance now ${rupees(after)}.'
              : '\nBalance ${rupees(before)} → ${rupees(after)}.';
        }
        if (_api != null) unawaited(_run('Updating insights', _afterNewData));
        return msg;
      case IngestStatus.duplicate:
        return 'Already recorded: the same bank reference, or the same payment within a minute, is '
            'already in the list. Pick the sample again for a new reference.';
      case IngestStatus.balance:
        return 'Balance update only, no transaction.';
      case IngestStatus.rejected:
        return 'Ignored, as it should be: ${_reasons[parsed.reason] ?? parsed.reason}.';
      case IngestStatus.skipped:
        return 'Ignored: "$s" is not a bank sender.';
      case IngestStatus.miss:
        return 'This looks like a bank message, but no pattern matched it (${parsed.reason}). '
            'It was added to the review list in Settings.';
    }
  }

  // ------------------------------------------------------------ edits

  Future<void> correct(Txn t, String category) async {
    await repo.correct(t, category);
    await _reload();
  }

  Future<void> saveServer(ServerConfig c) async {
    var url = c.baseUrl.trim();
    if (url.isNotEmpty && !url.contains('://')) url = 'https://$url'; // "192.168.1.5:8443" works too
    c = ServerConfig(baseUrl: url, token: c.token, fingerprint: c.fingerprint);
    await repo.setSetting('server_url', c.baseUrl.trim());
    await repo.setSetting('server_token', c.token.trim());
    await repo.setSetting('server_fingerprint', normalizeFingerprint(c.fingerprint));
    server = ServerConfig(
        baseUrl: c.baseUrl.trim(), token: c.token.trim(),
        fingerprint: normalizeFingerprint(c.fingerprint));
    notifyListeners();
  }

  Future<void> saveMoney({int? manualBalance, required int savingsTarget}) async {
    await repo.setSetting('manual_balance', manualBalance?.toString());
    await repo.setSetting('savings_target', '$savingsTarget');
    manualBalancePaise = manualBalance;
    savingsTargetPaise = savingsTarget;
    notifyListeners();
  }

  Future<void> setAssistantProvider(String p) async {
    await repo.setSetting('assistant_provider', p);
    assistantProvider = p;
    notifyListeners();
  }

  Future<void> deleteEverything() async {
    _debounce?.cancel();
    _debounce = null;
    await repo.wipe();
    await _inboxWatch?.cancel();
    _inboxWatch = null;
    _client?.close();
    _client = null;
    _clientConfig = null;
    server = const ServerConfig(baseUrl: '', token: '', fingerprint: '');
    manualBalancePaise = null;
    savingsTargetPaise = 0;
    assistantProvider = 'auto';
    insights = null;
    insightsAt = null;
    chat.clear();
    consented = false;
    status = 'All FinSight data on this phone was deleted';
    await _reload();
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _inboxWatch?.cancel();
    _client?.close();
    super.dispose();
  }
}
