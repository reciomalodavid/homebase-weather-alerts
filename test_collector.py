import copy
import unittest
from collector import parse_cap, snapshot, collect, FEED

XML = '''<alert xmlns="urn:oasis:names:tc:emergency:cap:1.2"><identifier>one</identifier><sender>http://www.aemet.es</sender><sent>2026-11-08T10:00:00Z</sent><status>Actual</status><scope>Public</scope><msgType>Alert</msgType><info><language>es-ES</language><event>Aviso de lluvia</event><severity>Moderate</severity><onset>2026-11-08T12:00:00+01:00</onset><expires>2026-11-08T14:00:00+01:00</expires><headline>Aviso amarillo</headline><description>20 mm.</description><instruction>Precaución.</instruction><parameter><valueName>AEMET-Meteoalerta nivel</valueName><value>amarillo</value></parameter><area><areaDesc>Sur de Mallorca</areaDesc><polygon>39,2 40,2 40,3 39,3 39,2</polygon><geocode><valueName>AEMET-Meteoalerta zona</valueName><value>645404</value></geocode></area></info></alert>'''

class CollectorTests(unittest.TestCase):
    def test_official_color_text_geometry_and_timezone(self):
        message = parse_cap(XML)
        warning = message['warnings'][0]
        self.assertEqual(warning['level'], 'amarillo')
        self.assertEqual(warning['description'], '20 mm.')
        self.assertEqual(warning['polygons'][0][0], [2, 39])
        self.assertEqual(warning['zoneIds'], ['645404'])
        self.assertEqual(warning['end'] - warning['start'], 7200)

    def test_replacement_cancellation_and_expiry(self):
        original = parse_cap(XML)
        replacement = copy.deepcopy(original)
        replacement['id'] = 'two'
        replacement['references'] = ['one']
        replacement['warnings'][0]['level'] = 'naranja'
        now = original['warnings'][0]['start']
        self.assertEqual(len(snapshot(b'feed', [original, replacement], now)['warnings']), 1)
        cancelled = {'id':'three', 'references':['two'], 'warnings':[]}
        self.assertEqual(snapshot(b'feed', [original, replacement, cancelled], now)['warnings'], [])
        self.assertEqual(snapshot(b'feed', [original], now + 7200)['warnings'], [])

    def test_rejects_missing_geography_unknown_level_and_invalid_time(self):
        for bad in [XML.replace('amarillo', 'azul'), XML.replace('<polygon>39,2 40,2 40,3 39,3 39,2</polygon>', ''), XML.replace('14:00:00+01:00', '11:00:00+01:00')]:
            with self.assertRaises(ValueError): parse_cap(bad)

    def test_test_messages_and_cancel_messages_are_not_live_warnings(self):
        self.assertEqual(parse_cap(XML.replace('<status>Actual', '<status>Test'))['warnings'], [])
        self.assertEqual(parse_cap(XML.replace('<msgType>Alert', '<msgType>Cancel'))['warnings'], [])

    def test_failure_does_not_create_empty_snapshot_and_changing_feed_rejected(self):
        feed = b'<rss><channel><title>AEMET</title><item><link>https://www.aemet.es/documentos_d/eltiempo/prediccion/avisos/cap/a.xml</link></item></channel></rss>'
        calls = 0
        def fetch(url):
            nonlocal calls
            if url == FEED:
                calls += 1
                return feed if calls == 1 else feed + b' '
            return XML
        with self.assertRaisesRegex(ValueError, 'changed'): collect(fetch=fetch, now=1)
        with self.assertRaises(ValueError): collect(fetch=lambda url: b'<html>error</html>', now=1)

if __name__ == '__main__': unittest.main()
