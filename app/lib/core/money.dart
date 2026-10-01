// Rupee formatting with Indian digit grouping (1,23,456), no locale data needed.

String groupIndian(int n) {
  final neg = n < 0;
  final s = n.abs().toString();
  if (s.length <= 3) return neg ? '-$s' : s;
  var head = s.substring(0, s.length - 3);
  final tail = s.substring(s.length - 3);
  final parts = <String>[];
  while (head.length > 2) {
    parts.insert(0, head.substring(head.length - 2));
    head = head.substring(0, head.length - 2);
  }
  if (head.isNotEmpty) parts.insert(0, head);
  return '${neg ? '-' : ''}${parts.join(',')},$tail';
}

/// ₹ amount for paise; whole rupees (half up) unless [decimals].
String rupees(int paise, {bool decimals = false}) {
  final neg = paise < 0;
  final abs = paise.abs();
  if (decimals) {
    final frac = (abs % 100).toString().padLeft(2, '0');
    return '${neg ? '-' : ''}₹${groupIndian(abs ~/ 100)}.$frac';
  }
  final whole = (abs + 50) ~/ 100;
  return '${neg && whole > 0 ? '-' : ''}₹${groupIndian(whole)}';
}

const _months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

String dayMonth(DateTime d) => '${d.day} ${_months[d.month - 1]}';

String timeOfDay(DateTime d) =>
    '${d.hour.toString().padLeft(2, '0')}:${d.minute.toString().padLeft(2, '0')}';
