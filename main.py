from datetime import datetime
from pathlib import Path

import json
import requests
import re
import sys
import time

import pandas as pd
import geopandas
import folium

import numpy as np
import matplotlib.pyplot as plt

API_URLS = ['https://lz4.overpass-api.de/api/',
            'https://z.overpass-api.de/api/']
API_STATUS_URLS = [url + 'status' for url in API_URLS]
API_INTERPRETER_URLS = [url + 'interpreter' for url in API_URLS]

api_url = 'https://lz4.overpass-api.de/api/' # alternativ: https://z.overpass-api.de/api/
api_status = api_url + 'status'
api_interpreter = api_url + 'interpreter'


def get_query(query, url=api_interpreter):
    
    now = datetime.now().strftime('%H:%M:%S')
    
    print('Querying... Current Time:', now)
    print('Query:', query)
    
    try:
        r = requests.get(url, params={'data': query})
        
    except:
        r = requests.Response()
        r.status_code = 500
        
    return r


#def get_data(query, wait=0):
#    if wait > 0:
#        print(f'Waiting for {wait} seconds')
#        display_counter(wait)
#    r = get_query(query)
#    code = r.status_code
#    if code == 200:
#        print('Query successful!')
#        data = r.json()
#        return data
#    else:
#        print('No data was acquired, Status Code: ', code)
#        print('Retrying...')
#        if slot_available():
#            return get_data(query)
#        else:
#            return get_data(query, wait=get_waittime())


def get_data(query, urls=API_URLS, wait=0):
    
    if wait > 0:
        print(f'Waiting for {wait} seconds')
        display_counter(wait)
    
    for url in urls:
        i = url + 'interpreter'
        s = url + 'status'
        
        if slot_available(s):
            r = get_query(query, url=i)
            code = r.status_code
            
            if code == 200:
                print('Query successful!')
                data = r.json()
                return data
            
            else:
                print('No data was acquired, Status Code: ', code)
                print('Retrying...')
    
    wait = min([get_waittime(url+'status') for url in urls])
    
    return get_data(query, urls=API_URLS, wait=wait)


def slot_available(url=api_status):
    r = requests.get(url)
    text = r.text.split('\n')
    
    for s in text:
        if 'slots available' in s:
            return True
    return False


def get_waittime(url=api_status):
    r = requests.get(url)
    text = r.text.split('\n')
    
    counter = []
    for s in text:
        if 'Slot available after' in s:
            rxp = re.search('\s(\d+)\s', s)
            time_left = int(rxp.group(1))
            counter.append(time_left)
    
    return min(counter) if len(counter) > 0 else 5


def display_counter(n):
    for i in range(n,-1,-1):
        time.sleep(1)
        sys.stdout.write(f"\r{i:03d}")
        sys.stdout.flush()
    print()
    return


def get_states(country_code='DE'):
    query = f'''[out:json];
    area["ISO3166-1"="{country_code}"]->.searchArea;
    rel["admin_level"="4"]["boundary"="administrative"]["ISO3166-2"~"{country_code}"](area.searchArea);
    out tags;'''
    return get_data(query)


def get_counties(state_code='DE-BW'):
    query = f'''[out:json];
    area["ISO3166-2"="{state_code}"]->.searchArea;
    relation["admin_level"=6]["boundary"="administrative"](area.searchArea);
    out tags;'''
    return get_data(query)


def get_climbing_facilities_basic(country_code='DE'):
    query = f'''area["ISO3166-1"="{country_code}"]->.searchArea;
    nwr[leisure=sports_centre][sport~"^.*(kletter|boulder|climb).*$",i](area.searchArea);
    out center;'''
    print(f'Getting climbing facilities for: {country_code}')
    return get_data(query)


def get_climbing_facilities_advanced(state_code='DE-BW'):
    query = f'''[out:json][maxsize:2000000000][timeout:300];
    area["ISO3166-2"="{state_code}"]->.searchArea;
    (nwr[name~"^.*(kletter|boulder|climb).*$",i][building](area.searchArea);
    nwr[sport~"^.*(kletter|boulder|climb).*$",i][building](area.searchArea);
    nwr[leisure=sports_centre][sport~"^.*(kletter|boulder|climb).*$",i](area.searchArea););
    out center;'''
    print(f'Getting climbing facilities for: {state_code}')
    return get_data(query)


def to_geojson(data, timestamp=''):
    if not timestamp:
        timestamp = datetime.utcnow().replace(microsecond=0).isoformat() + 'Z'
    
    # normalize data (assumes ways are stored with "out center")
    for i, element in enumerate(data):
        if data[i]['type'] == 'way':
            data[i]['lat'] = data[i]['center']['lat']
            data[i]['lon'] = data[i]['center']['lon']
        data[i]['tags']['id'] = data[i]['id']
        data[i]['tags']['type'] = data[i]['type']
    
    # create geojson
    out = {'type': 'FeatureCollection',
           "crs": {"type": "name",
                   "properties": {"name": "EPSG:4326"}
                  },
           'generator': 'overpass-api',
           'copyright': ('The data included in this document is from '
                         'www.openstreetmap.org. The data is made '
                         'available under ODbL.'),
           'timestamp': timestamp,
           'features': [
                       {'type': 'Feature',
                        'id': feature['id'],
                        'id_type': feature['type'],
                        'geometry': {'type': 'Point',
                                     'coordinates': [feature['lon'],
                                                     feature['lat']]},
                        'properties': {key: value
                                       for key, value in feature['tags'].items()}
                       }
                        for feature in data
                       ]
          }
    return out


def to_file(geojson, folder='', name=''):
    out = Path()
    folder = Path().absolute() / 'data' / 'climbing_facilities' if not folder else Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    name = 'climbing_facilities' + '_' + str(datetime.now().date()) if not name else name
    out = (folder / name).with_suffix('.geojson')
    with open(out, 'w') as f:
        f.write(json.dumps(geojson))


def query_osm(country_code='DE', advanced=True):
    name_ids = []
    data = []
    
    if not advanced:
        facilities = get_climbing_facilities_basic(country_code=country_code)
        for f in facilities['elements']:
            data.append(f)
        print('Finished')
        return data
    
    print('Getting states...')
    states = get_states(country_code=country_code)
    
    for state in states['elements']:
        i = state['tags']['ISO3166-2']
        name_ids.append(i)
    
    for i in name_ids:
        facilities = get_climbing_facilities_advanced(state_code=i)
        for f in facilities['elements']:
            data.append(f)
            
    print('Finished')
    return data


def show_plot(geojson):
    # Collect coords into list
    coords = []
    for elem in geojson['features']:
        lon = elem['geometry']['coordinates'][0]
        lat = elem['geometry']['coordinates'][1]
        coords.append((lon,lat))
    
    X = np.array(coords)
    
    plt.plot(X[:, 0], X[:, 1], 'o')
    plt.title('Climbing Facilities in Germany')
    plt.xlabel('Longitude')
    plt.ylabel('Latitude')
    plt.axis('equal')
    plt.show()