"""One-off export of the official AEMET warning boundaries (WGS84)."""
import io
import gzip
import json
from pathlib import Path
import urllib.request
import zipfile
import shapefile
from pyproj import Transformer
SOURCE = 'https://www.aemet.es/documentos/es/eltiempo/prediccion/avisos/plan_meteoalerta/AEMET-meteoalerta-delimitacion-zonas.zip'
def build(raw):
    archive = zipfile.ZipFile(io.BytesIO(raw))
    zones = []
    for name in archive.namelist():
        if not name.endswith('.shp'):
            continue
        base = name[:-4]
        reader = shapefile.Reader(shp=io.BytesIO(archive.read(name)), dbf=io.BytesIO(archive.read(base + '.dbf')), encoding='latin1')
        project = Transformer.from_crs(archive.read(base + '.prj').decode(), 'EPSG:4326', always_xy=True)
        def coordinates(value):
            if isinstance(value[0], (int, float)):
                lon, lat = project.transform(value[0], value[1])
                return [round(lon, 6), round(lat, 6)]
            return [coordinates(v) for v in value]
        for row in reader.iterShapeRecords():
            record = row.record.as_dict()
            geometry = row.shape.__geo_interface__
            zones.append({'id': record['COD_Z'], 'name': record['NOM_Z'], 'geometry': {'type': geometry['type'], 'coordinates': coordinates(geometry['coordinates'])}})
    if len(zones) < 180:
        raise ValueError('Incomplete official boundaries')
    return {'schema': 1, 'source': SOURCE, 'attribution': 'AEMET. Delimitación de zonas Meteoalerta v6.', 'zones': zones}
if __name__ == '__main__':
    data = urllib.request.urlopen(SOURCE, timeout=30).read()
    target = Path(__file__).parent / 'data/zones.json.gz'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(gzip.compress((json.dumps(build(data), ensure_ascii=False, separators=(',', ':')) + '\n').encode(), mtime=0))
    print(f'{len(build(data)["zones"])} official zones exported')
