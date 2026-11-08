"""Publish an atomic nationwide AEMET CAP snapshot. No API key is required."""
import concurrent.futures
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

FEED = 'https://www.aemet.es/documentos_d/eltiempo/prediccion/avisos/rss/CAP_AFAE_wah_RSS.xml'
CAP = '{urn:oasis:names:tc:emergency:cap:1.2}'
ROOT = Path(__file__).parent

def download(url):
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != 'https' or parsed.netloc != 'www.aemet.es' or not parsed.path.startswith('/documentos_d/eltiempo/prediccion/avisos/'):
        raise ValueError('Untrusted source URL')
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'Homebase-Official-Warnings/1.0'}), timeout=20) as response:
                if response.geturl().split('/')[2] != 'www.aemet.es':
                    raise ValueError('Unexpected redirect')
                data = response.read(8_000_001)
                if len(data) > 8_000_000:
                    raise ValueError('Oversized source')
                return data
        except (OSError, TimeoutError):
            if attempt == 2:
                raise
            time.sleep(attempt + 1)

def timestamp(text):
    parsed = datetime.fromisoformat(text.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('Missing official time zone')
    return int(parsed.timestamp())

def parse_cap(raw):
    root = ET.fromstring(raw)
    if root.tag != CAP + 'alert':
        raise ValueError('Invalid CAP response')
    text = lambda key: root.findtext(CAP + key, '')
    identifier, sent = text('identifier'), timestamp(text('sent'))
    if not identifier:
        raise ValueError('Missing CAP identifier')
    refs = [reference.split(',')[1] for reference in text('references').split() if len(reference.split(',')) == 3]
    result = {'id': identifier, 'sent': sent, 'references': refs, 'warnings': []}
    if text('status') != 'Actual' or text('scope') != 'Public' or text('msgType') == 'Cancel':
        return result
    infos = root.findall(CAP + 'info')
    spanish = [info for info in infos if info.findtext(CAP + 'language', '').startswith('es')]
    if not spanish:
        raise ValueError('Missing official Spanish warning text')
    for info in spanish:
        value = lambda key: info.findtext(CAP + key, '')
        params = {p.findtext(CAP + 'valueName'): p.findtext(CAP + 'value') for p in info.findall(CAP + 'parameter')}
        level = params.get('AEMET-Meteoalerta nivel', '').lower()
        if level in ('verde', '') and value('severity') in ('Minor', 'Unknown'):
            continue
        if level not in ('amarillo', 'naranja', 'rojo'):
            raise ValueError('Unrecognized official warning level')
        start, end = timestamp(value('onset') or value('effective')), timestamp(value('expires'))
        if end <= start:
            raise ValueError('Invalid validity interval')
        for area in info.findall(CAP + 'area'):
            zones = [g.findtext(CAP + 'value') for g in area.findall(CAP + 'geocode') if g.findtext(CAP + 'valueName') == 'AEMET-Meteoalerta zona']
            polygons = []
            for polygon in area.findall(CAP + 'polygon'):
                ring = [[float(lon), float(lat)] for lat, lon in (pair.split(',') for pair in (polygon.text or '').split())]
                if len(ring) < 4 or any(abs(lon) > 180 or abs(lat) > 90 for lon, lat in ring):
                    raise ValueError('Invalid CAP polygon')
                polygons.append(ring)
            if not zones or not polygons:
                raise ValueError('Missing official warning geography')
            result['warnings'].append({'id': identifier + ':' + ','.join(zones), 'sent': sent, 'level': level, 'event': value('event'), 'headline': value('headline'), 'description': value('description'), 'instruction': value('instruction'), 'area': area.findtext(CAP + 'areaDesc', ''), 'zoneIds': zones, 'polygons': polygons, 'start': start, 'end': end, 'source': 'AEMET'})
    return result

def snapshot(raw_feed, messages, now):
    replaced = {ref for message in messages for ref in message['references']}
    warnings = [warning for message in messages if message['id'] not in replaced for warning in message['warnings'] if warning['end'] > now]
    return {'schema': 1, 'checkedAt': now, 'feedDigest': hashlib.sha256(raw_feed).hexdigest(), 'source': FEED, 'attribution': 'AEMET. Avisos oficiales Meteoalerta. Datos reutilizados sin alterar su contenido.', 'warnings': sorted(warnings, key=lambda warning: (warning['start'], warning['id']))}

def collect(fetch=download, now=None):
    now = int(time.time()) if now is None else now
    raw = fetch(FEED)
    feed = ET.fromstring(raw)
    channel = feed.find('channel')
    if channel is None or 'AEMET' not in channel.findtext('title', ''):
        raise ValueError('Unexpected official feed')
    items = channel.findall('item')
    links = list(dict.fromkeys(item.findtext('link', '') for item in items))
    if any(not link.endswith('.xml') for link in links):
        raise ValueError('Unexpected national feed entry')
    if len(links) > 2000:
        raise ValueError('Oversized feed')
    previous_path = ROOT / 'data/warnings.json'
    try:
        previous = json.loads(previous_path.read_text())
    except (OSError, ValueError):
        previous = None
    if previous and previous.get('schema') == 1 and previous.get('feedDigest') == hashlib.sha256(raw).hexdigest():
        previous['checkedAt'] = now
        previous['warnings'] = [warning for warning in previous['warnings'] if warning['end'] > now]
        return previous
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        messages = list(pool.map(lambda url: parse_cap(fetch(url)), links))
    # Never publish a mixture of two revisions of the nationwide feed.
    if fetch(FEED) != raw:
        raise ValueError('Official feed changed during collection; keep previous snapshot')
    return snapshot(raw, messages, now)

if __name__ == '__main__':
    value = collect()
    target = ROOT / 'data/warnings.json'
    temp = target.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, separators=(',', ':')) + '\n')
    temp.replace(target)
    print(f'Verified {len(value["warnings"])} official warnings at {value["checkedAt"]}')
