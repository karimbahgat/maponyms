
import sqlite3

class Online(object):
    def __init__(self):
        import geopy
        self.coder = geopy.geocoders.Nominatim()

    def geocode(self, name, limit=10):
        ms = self.coder.geocode(name, exactly_one=False, limit=limit) or []
        for m in ms:
            yield {'type': 'Feature',
                   'properties': {'name': m.address,
                                  },
                   'geometry': {'type': 'Point',
                                'coordinates': (m.longitude, m.latitude)
                                },
                   }

class SQLiteCoder(object):
    def __init__(self, path=None):
        self.path = path or 'resources/gazetteers.db'
        self.db = sqlite3.connect(self.path)

    def geocode(self, name, limit=None, lang=None):
        # lang is ignored, keeping for legacy reasons
        if limit:
            raise NotImplemented("Geocode results 'limit' not yet implemented")
        _matches = "SELECT * FROM names WHERE name = ? COLLATE NOCASE"
        _select = "sources.name,locs.loc_id,GROUP_CONCAT(names.name, '|'),locs.lon,locs.lat"
        _from = "sources,locs,names,matches WHERE names.loc_id=matches.loc_id AND names.loc_id=locs.loc_id AND locs.source_id=sources.source_id"
        _groupby = "matches.loc_id"
        query = "WITH matches AS ({_matches}) SELECT {_select} FROM {_from} GROUP BY {_groupby}".format(_matches=_matches, _select=_select, _from=_from, _groupby=_groupby)
        results = self.db.cursor().execute(query, (name,))
        results = ({'type': 'Feature',
                   'properties': {'data':data,
                                  'id':ID,
                                  'name':names,
                                  'search':name,
                                  },
                   'geometry': {'type':'Point', 'coordinates':[lon,lat]},
                   } for data,ID,names,lon,lat in results)
        return results

