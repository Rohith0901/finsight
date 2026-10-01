// Who sent an SMS. Personal numbers are dropped before anything reads the body.

enum SenderKind { bank, unknown, personal, promotional }

class Sender {
  const Sender(this.kind, {this.bank, this.header = ''});
  final SenderKind kind;
  final String? bank;
  final String header;
}

final _personal = RegExp(r'^\+?[0-9]{10,13}$');
final _alnum = RegExp(r'^[A-Z0-9]+$');

/// DLT headers of banks we know. Extend this from your own messages; senders not
/// listed are still parsed when the text looks like a transaction, and show up
/// on the Settings > Needs review screen.
const bankHeaders = <String, String>{
  'HDFCBK': 'hdfc', 'HDFCBN': 'hdfc', 'SBIUPI': 'sbi', 'SBIINB': 'sbi', 'ATMSBI': 'sbi',
  'SBIPSG': 'sbi', 'CBSSBI': 'sbi', 'SBICRD': 'sbi', 'ICICIB': 'icici', 'ICICIT': 'icici',
  'AXISBK': 'axis', 'AXISMR': 'axis', 'KOTAKB': 'kotak', 'PNBSMS': 'pnb', 'BOIIND': 'boi',
  'BOBTXN': 'bob', 'BOBSMS': 'bob', 'CANBNK': 'canara', 'UNIONB': 'union', 'IDFCFB': 'idfc',
  'INDUSB': 'indusind', 'YESBNK': 'yes', 'FEDBNK': 'federal', 'AUBANK': 'au',
  'PAYTMB': 'paytm', 'AIRBNK': 'airtel', 'RBLBNK': 'rbl', 'CENTBK': 'central',
  'SCBANK': 'sc', 'HSBCIN': 'hsbc', 'CITIBK': 'citi', 'AMEXIN': 'amex',
};

Sender classifySender(String raw) {
  final s = raw.trim().toUpperCase().replaceAll(' ', '');
  if (_personal.hasMatch(s)) return const Sender(SenderKind.personal);
  final parts = s.split('-');
  final suffix = parts.length > 1 && parts.last.length == 1 ? parts.last : '';
  if (suffix == 'P') return const Sender(SenderKind.promotional);
  final candidates = parts.where((p) => p.length == 6 && _alnum.hasMatch(p)).toList();
  final header = candidates.isNotEmpty ? candidates.last : (s.length == 6 ? s : '');
  final bank = bankHeaders[header];
  if (bank != null) return Sender(SenderKind.bank, bank: bank, header: header);
  return Sender(SenderKind.unknown, header: header);
}
