# Official AEMET warnings for Homebase

Deploy this directory as the root of a **separate public repository** named
`reciomalodavid/homebase-weather-alerts`, default branch `main`. Do not copy the
Homebase private app or any account/profile/favorite data into that repository.
The only public data are official weather warnings and geographical boundaries.

The included Actions workflow runs at minutes 7, 22, 37 and 52. GitHub scheduling
can be delayed; it is not a real-time warning service. Push the sources to start
the initial collection. Scheduled workflows must be on the default branch.
Standard hosted Actions runners in public repositories are free. No weather API
key, personal token or Firebase credential is used; writes use the job's built-in
GITHUB_TOKEN with contents:write. Enable Actions if repository policy requires it.

`collector.py` verifies the national AEMET RSS index, downloads the CAP messages,
selects official Spanish text, colors, area codes and polygons, applies updates,
cancellations and expiry, and publishes data atomically only if every download
and validation succeeds and the index stays unchanged. Failures keep the previous
snapshot. An unchanged index revalidates the previous snapshot without repeatedly
downloading all CAP files. `checkedAt` is the collection time, `sent` the official
message issuance time. CAP text is not translated or reinterpreted.

`build_zones.py` converts the official published AEMET Meteoalerta v6 zone archive
from UTM30N to WGS84, including coastal zones, with pyshp 2.3.1 / pyproj 3.7.2.
Coordinates retain six decimals without simplifying boundaries. The resulting
compressed catalog is built once by the workflow and committed. Rebuild it when
AEMET updates the zone definitions. The app also matches actual CAP polygons.
Locations outside known zones display unconfirmed coverage rather than no warnings.
The app treats a check older than 45 minutes as stale, with no false all-clear.

Sources and attribution: AEMET (Agencia Estatal de Meteorología), official CAP
Meteoalerta warnings and official zone definitions. Preserve this attribution and
all original warning text. Source URLs are embedded in the exported data.

Tests: `python -m unittest test_collector` (from this directory).
Live check: `python collector.py`. Never replace a failed fetch with an empty list.
Published files: `data/warnings.json`, `data/zones.json.gz`.
No mobile push notifications are sent.
