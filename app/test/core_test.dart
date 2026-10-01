import 'dart:io';

import 'package:finsight/core/money.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('Indian digit grouping', () {
    expect(groupIndian(1234567), '12,34,567');
    expect(groupIndian(999), '999');
    expect(groupIndian(100000), '1,00,000');
    expect(rupees(48550), '₹486');
    expect(rupees(12345678, decimals: true), '₹1,23,456.78');
    expect(rupees(-5000), '-₹50');
  });

  test('bundled assets match shared/ (run `make fixtures` after editing shared/)', () {
    for (final name in ['categories.json', 'merchants.json', 'sms_hints.json']) {
      expect(File('assets/shared/$name').readAsStringSync(), File('../shared/$name').readAsStringSync(),
          reason: name);
    }
  });
}
