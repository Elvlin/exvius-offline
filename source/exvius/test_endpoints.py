"""Own inert fixtures only; no upstream imports."""
import unittest
from prepare_endpoints import parse_contract
ROW='| `AlphaRequest` | `abcdefgh` | `12345678` | `/actionSymbol/route1.php` |\n'
class Endpoints(unittest.TestCase):
    def test_exact_schema(self):
        r=parse_contract(ROW.encode());self.assertEqual(r['classes'],1)
        self.assertEqual(r['by_class']['AlphaRequest']['encode_key'],'12345678')
        self.assertEqual(r['by_url_token'],{'route1':['AlphaRequest']})
    def test_shared_url_preserved(self):
        other=ROW.replace('AlphaRequest','BetaRequest').replace('abcdefgh','ijklmnop')
        r=parse_contract((ROW+other).encode());self.assertEqual(r['classes'],2);self.assertEqual(r['distinct_urls'],1)
    def test_identical_duplicate_not_multiplied(self):
        self.assertEqual(parse_contract((ROW+ROW).encode())['classes'],1)
    def test_conflicting_class_rejected(self):
        with self.assertRaises(ValueError):parse_contract((ROW+ROW.replace('route1','route2')).encode())
    def test_request_collision_rejected(self):
        with self.assertRaises(ValueError):parse_contract((ROW+ROW.replace('AlphaRequest','BetaRequest').replace('route1','route2')).encode())
    def test_same_wire_alias_preserved(self):
        r=parse_contract((ROW+ROW.replace('AlphaRequest','AliasRequest')).encode())
        self.assertEqual(r['classes'],2);self.assertEqual(r['distinct_urls'],1)
    def test_invalid_empty_table(self):
        for text in ('no rows',ROW.replace('12345678','short')):
            with self.assertRaises(ValueError):parse_contract(text.encode())
if __name__=='__main__':unittest.main()
