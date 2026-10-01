// SMS parser. Deterministic, runs only on the phone, never stores the body.
//
// The same algorithm lives in ml/finsight_ml/parser_ref.py, where it is checked
// against shared/fixtures; each pattern below has the same name there. Change
// both together.

import 'sender_filter.dart';

const _amt = r'([0-9][0-9,]*(?:\.[0-9]{1,2})?)';
const _cur = r'(?:rs\.?|inr|₹)';

RegExp _re(String pattern, {bool multiLine = false}) =>
    RegExp(pattern, caseSensitive: false, multiLine: multiLine);

final currencyAmount = _re('$_cur\\s*$_amt');
final verbAmount = _re('(?:debited|credited)\\s+(?:by|for|with)\\s+$_cur?\\s*$_amt');
final balanceBefore = _re(r'(?:bal|balance|lmt|limit|avl|avbl|available)[^0-9]{0,12}$');
final balanceRe = _re(
    '(?:(?:avl|avbl|available)\\.?\\s*bal(?:ance)?|\\bbal)\\.?\\s*(?:is\\s*)?[:\\-]?\\s*$_cur?\\s*$_amt');
final balanceOnly = _re('balance in (?:your )?a/c\\s*\\S+\\s+is\\s+$_cur\\s*$_amt');
final availableLimit = _re('(?:avl|available)\\.?\\s*(?:lmt|limit)\\s*:?\\s*$_cur?\\s*$_amt');

final debitVerb = _re(r'\b(debited|debit(?!\s*card)|spent|sent|paid|withdrawn|used for|purchase)\b');
final creditVerb =
    _re(r'\b(credited|credit(?!\s*card)|received|deposited|refund(?:ed)?|reversed|reversal)\b');
final completedVerb = _re(
    r'\b(debited|credited|spent|sent|withdrawn|deposited|received|refunded|reversed|paid|has credit|used for)\b');

final cardMask = _re(r'\bcard\s*(?:no\.?|number)?\s*(?:ending(?:\s*with)?)?\s*[x*]*\s*([0-9]{4})\b');
final creditCard = _re(r'credit\s*card|(?:avl|available)\.?\s*(?:lmt|limit)');
final accountMask =
    _re(r'(?:a/c|acct|account|\bac)\.?\s*(?:no\.?)?\s*[:\-]?\s*(?:[x*]+|\.\.)?\s*([0-9]{3,6})\b');

final axisUpiRef = _re(r'UPI/P2[AM]/([0-9]{6,})/');
final refRe = _re(r'\b(?:upi\s*ref(?:erence)?\s*(?:no\.?|number)?|ref(?:erence)?\s*(?:no\.?|number|#)?|refno|rrn|'
    r'utr(?:\s*no\.?)?|txn\s*(?:id|no\.?))\s*[:.\-]?\s*([A-Za-z0-9]{6,25})');
final upiColonRef = _re(r'\bupi\s*:\s*([0-9]{6,})');
final hdfcNeft = _re(r'NEFT\s*Cr-[A-Za-z0-9]+-(.+?)-.+-([A-Za-z0-9]{8,})(?:\.|\s|$)');

final axisUpiParty = _re(r'UPI/P2([AM])/[0-9]+/([^\n/]+)');
final axisCardLines = _re(r'^Spent\nCard no\.[^\n]*\n[^\n]*\n[^\n]*\n([^\n]+)');
final toLine = _re(r'^To (.+)$', multiLine: true);
final iciciUpiPayee = _re(r';\s*(.+?)\s+credited');
final iciciCardPayee = _re(r'\bon\s+\d{1,2}-[A-Za-z]{3}-\d{2}\s+on\s+(.+?)\.\s*avl');
final vpaTo = _re(r'\bto\s+(?:vpa\s+)?([A-Za-z0-9._\-]+@[A-Za-z0-9.\-]+)');
final vpaFrom = _re(r'\bfrom\s+(?:vpa\s+)?([A-Za-z0-9._\-]+@[A-Za-z0-9.\-]+)');
const _end = r'(?=\s+on\b|\s+ref|\s+upi\b|\s+via\b|\s+for\b|\s+at\b|\s+towards\b|\.(?:\s|$)|,|\n|$)';
final atPayee = _re(r'\bat\s+(.+?)(?=\s+on\b|\s+via\b|\s+avl\b|\.(?:\s|$)|\n|$)');
final towardsPayee = _re('\\btowards\\s+(.+?)$_end');
final toPayee = _re('\\b(?:trf to|transfer to|paid to|sent to|to)\\s+(.+?)$_end');
const _creditEnd = r'(?=\s+on\b|\s+ref|\s+upi\b|\s+via\b|\s+credited\b|\s*\(|\.(?:\s|$)|,|\n|$)';
final fromPayer = _re('\\bfrom\\s+(.+?)$_creditEnd');
final byPayer = _re('\\bby\\s+(.+?)$_creditEnd');
final badParty = _re(r'^(your|the|a/c|ac)\b|a/c|\bacct\b|\bcard\b|\bbank a');

final cardBillCredit = _re(r'payment\b.*\breceived|received towards');

final otpRe = _re(r'\botp\b|one[\s-]?time password|verification code');
final requestRe = _re(r'requested money|collect request|request(?:ed)? (?:of|for) (?:rs|inr|₹)');
final futureRe =
    _re(r'will be (?:debited|credited|deducted)|\bis due\b|\bdue (?:on|by)\b|due date|scheduled for');
final declinedRe = _re(r'declined|\bfailed\b|unsuccessful|could not be processed|not processed');
final promoRe =
    _re(r'pre-?approved|apply now|offer valid|\bt&c\b|cashback up to|limited period|click here');

final _upiWord = _re(r'\bupi\b');
final _letters = RegExp(r'[A-Za-z]');
final _digit = RegExp(r'[0-9]');

enum Outcome { transaction, balance, rejected, skipped, miss }

class ParsedSms {
  ParsedSms(this.outcome, {this.reason = ''});

  final Outcome outcome;
  final String reason;
  int? amountPaise;
  String? direction; // "debit" | "credit"
  String? accountMask;
  String? card; // null | "debit" | "credit"
  String? merchantRaw;
  String mode = 'other';
  String? refNo;
  int? balancePaise;
  int? availableLimitPaise;
  bool isRefund = false;
  bool isCardBill = false;
  bool p2a = false;
  bool p2m = false;
  List<String> hints = const [];
  Sender? sender;
}

int toPaise(String text) {
  final clean = text.replaceAll(',', '');
  final dot = clean.indexOf('.');
  final whole = dot < 0 ? clean : clean.substring(0, dot);
  final frac = dot < 0 ? '' : clean.substring(dot + 1);
  return int.parse(whole) * 100 + int.parse('${frac}00'.substring(0, 2));
}

class SmsParser {
  SmsParser(this.hintPatterns);

  /// Hint name -> pattern, from shared/sms_hints.json.
  final Map<String, RegExp> hintPatterns;

  List<String> hintsFor(String body) =>
      [for (final e in hintPatterns.entries) if (e.value.hasMatch(body)) e.key];

  int? _amount(String body) {
    for (final m in currencyAmount.allMatches(body)) {
      final start = m.start - 25 < 0 ? 0 : m.start - 25;
      if (!balanceBefore.hasMatch(body.substring(start, m.start))) {
        return toPaise(m.group(1)!);
      }
    }
    final v = verbAmount.firstMatch(body);
    return v == null ? null : toPaise(v.group(1)!);
  }

  String? _direction(String body) {
    final d = debitVerb.firstMatch(body);
    final c = creditVerb.firstMatch(body);
    if (d != null && (c == null || d.start < c.start)) return 'debit';
    return c != null ? 'credit' : null;
  }

  /// Bank remarks glued after a payee ("J JOTHIMANI Info:P2A/624107..."): cut
  /// from the first "Info", P2A/P2M marker or 6+ digit run.
  static final partyNoise = _re(r'(?:\s*[:/-]?\s*\binfo\b|[\s/:-]*\bp2[am]\b|\s*[/:-]?\s*[0-9]{6,})[\s\S]*$');

  static String? cleanParty(String? text) {
    if (text == null) return null;
    var t = text.trim();
    if (!t.contains('@')) t = t.replaceFirst(partyNoise, '').trim(); // UPI handles keep their digits
    while (t.isNotEmpty && '.,;:'.contains(t[t.length - 1])) {
      t = t.substring(0, t.length - 1);
    }
    t = t.trim();
    if (t.isEmpty || t.length > 60 || !_letters.hasMatch(t) || badParty.hasMatch(t)) return null;
    return t;
  }

  static String? _first(List<RegExp> patterns, String body) {
    for (final p in patterns) {
      final m = p.firstMatch(body);
      if (m != null) {
        final party = cleanParty(m.group(1));
        if (party != null) return party;
      }
    }
    return null;
  }

  /// First reference-like token that contains a digit ("Ref No 4265..." or "UPI:4265...").
  static String? _reference(String body) {
    for (final pattern in [refRe, upiColonRef]) {
      for (final r in pattern.allMatches(body)) {
        if (_digit.hasMatch(r.group(1)!)) return r.group(1);
      }
    }
    return null;
  }

  ParsedSms parse(String senderRaw, String rawBody) {
    final sender = classifySender(senderRaw);
    if (sender.kind == SenderKind.personal) {
      return ParsedSms(Outcome.skipped, reason: 'personal sender')..sender = sender;
    }
    if (sender.kind == SenderKind.promotional) {
      return ParsedSms(Outcome.rejected, reason: 'promo')..sender = sender;
    }
    final body = rawBody.replaceAll('\r\n', '\n').replaceAll('\r', '\n');
    final completed = completedVerb.hasMatch(body);
    if (requestRe.hasMatch(body)) return ParsedSms(Outcome.rejected, reason: 'request');
    if (futureRe.hasMatch(body)) return ParsedSms(Outcome.rejected, reason: 'future');
    if (declinedRe.hasMatch(body)) return ParsedSms(Outcome.rejected, reason: 'declined');
    if (!completed && otpRe.hasMatch(body)) return ParsedSms(Outcome.rejected, reason: 'otp');
    if (!completed && promoRe.hasMatch(body)) return ParsedSms(Outcome.rejected, reason: 'promo');
    if (!completed) {
      final m = balanceOnly.firstMatch(body) ?? balanceRe.firstMatch(body);
      final acct = accountMask.firstMatch(body);
      if (m != null && acct != null) {
        return ParsedSms(Outcome.balance)
          ..sender = sender
          ..accountMask = acct.group(1)
          ..balancePaise = toPaise(m.group(1)!);
      }
    }

    final amount = _amount(body);
    final direction = _direction(body);
    if (amount == null || direction == null) {
      return ParsedSms(Outcome.miss, reason: amount == null ? 'no amount' : 'no direction')
        ..sender = sender;
    }

    final p = ParsedSms(Outcome.transaction)
      ..sender = sender
      ..amountPaise = amount
      ..direction = direction;
    final card = cardMask.firstMatch(body);
    if (card != null) {
      p.accountMask = card.group(1);
      p.card = creditCard.hasMatch(body) ? 'credit' : 'debit';
    } else {
      p.accountMask = accountMask.firstMatch(body)?.group(1);
    }

    final axisRef = axisUpiRef.firstMatch(body);
    final neft = hdfcNeft.firstMatch(body);
    if (axisRef != null) {
      p.refNo = axisRef.group(1);
    } else if (neft != null) {
      p.refNo = neft.group(2);
    } else {
      p.refNo = _reference(body);
    }

    final bal = balanceRe.firstMatch(body);
    p.balancePaise = bal == null ? null : toPaise(bal.group(1)!);
    final lim = availableLimit.firstMatch(body);
    p.availableLimitPaise = lim == null ? null : toPaise(lim.group(1)!);

    final axis = axisUpiParty.firstMatch(body);
    if (axis != null) {
      p.merchantRaw = cleanParty(axis.group(2));
      p.p2a = axis.group(1)!.toUpperCase() == 'A';
      p.p2m = axis.group(1)!.toUpperCase() == 'M';
    } else if (direction == 'credit' && p.card != null) {
      p.merchantRaw = null; // a payment received on a card has no merchant
    } else if (direction == 'credit') {
      p.merchantRaw =
          neft != null ? cleanParty(neft.group(1)) : _first([vpaFrom, fromPayer, byPayer], body);
    } else {
      p.merchantRaw = _first([
        axisCardLines,
        toLine,
        iciciUpiPayee,
        iciciCardPayee,
        vpaTo,
        atPayee,
        towardsPayee,
        toPayee,
      ], body);
    }

    final lower = body.toLowerCase();
    if (_upiWord.hasMatch(lower) || body.contains('@')) {
      p.mode = 'upi';
    } else if (RegExp(r'\bneft\b').hasMatch(lower)) {
      p.mode = 'neft';
    } else if (RegExp(r'\bimps\b').hasMatch(lower)) {
      p.mode = 'imps';
    } else if (RegExp(r'\brtgs\b').hasMatch(lower)) {
      p.mode = 'rtgs';
    } else if (RegExp(r'\batm\b').hasMatch(lower)) {
      p.mode = 'atm';
    } else if (RegExp(r'net ?banking').hasMatch(lower)) {
      p.mode = 'netbanking';
    } else if (p.card != null && direction == 'debit') {
      p.mode = 'card';
    }
    p.hints = hintsFor(body);
    p.isRefund = direction == 'credit' && p.hints.contains('refund');
    p.isCardBill = direction == 'credit' && p.card != null && cardBillCredit.hasMatch(body);
    return p;
  }
}
