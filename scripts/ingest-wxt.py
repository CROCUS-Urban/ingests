"""Ingests a number of days of CROCUS WXT data

Usage:
    python ./ingest-wxt.py ndays year month day site out_directory

Author:
    Scott Collis - 5.9.2024
    Max Grover - 8.19.2024
"""

import sage_data_client
import matplotlib.pyplot as plt
import pandas as pd
from metpy.calc import dewpoint_from_relative_humidity, wet_bulb_temperature
from metpy.units import units
from PIL import Image
import numpy as np
import datetime
import xarray as xr
import os
import argparse


from matplotlib.dates import DateFormatter

def ingest_wxt(st, global_attrs, var_attrs, odir='/Users/scollis/data/wxt/' ):
    """
        Ingest from CROCUS WXTs using the Sage Data Client. 

        Ingests a whole day of WXT data and saves it as a NetCDF to odir
    
        Parameters
        ----------
        st : Datetime 
            Date to ingest

        global_attrs : dict
            Attributes that are specific to the site.
        
        var_attrs : dict
            Attributes that map variables in Beehive to
            CF complaint netCDF valiables.
        
    
        Returns
        -------
        None
    
    """
    
    hours = 24
    start = st.strftime('%Y-%m-%dT%H:%M:%SZ')
    end = (st + datetime.timedelta(hours=hours)).strftime('%Y-%m-%dT%H:%M:%SZ')
    print(start)
    print(end)
    df_temp = sage_data_client.query(start=start,
                                     end=end, 
                                        filter={
                                            "name" : 'wxt.env.temp|wxt.env.humidity|wxt.env.pressure|wxt.rain.accumulation',
                                            "plugin" : global_attrs['plugin'],
                                            "vsn" : global_attrs['WSN'],
                                            "sensor" : "vaisala-wxt536"
                                        }
    )
    winds = sage_data_client.query(start=start,
                                     end=end, 
                                        filter={
                                            "name" : 'wxt.wind.speed|wxt.wind.direction',
                                            "plugin" : global_attrs['plugin'],
                                            "vsn" : global_attrs['WSN'],
                                            "sensor" : "vaisala-wxt536"
                                        }
    )
    
    hums = df_temp[df_temp['name']=='wxt.env.humidity']
    temps = df_temp[df_temp['name']=='wxt.env.temp']
    pres = df_temp[df_temp['name']=='wxt.env.pressure']
    rain = df_temp[df_temp['name']=='wxt.rain.accumulation']


    npres = len(pres)
    nhum = len(hums)
    ntemps = len(temps)
    nrains = len(rain)
    print(npres, nhum, ntemps, nrains)
    minsamps = min([nhum, ntemps, npres, nrains])

    temps['time'] = pd.DatetimeIndex(temps['timestamp'].values)

    vals = temps.set_index('time')[0:minsamps]
    vals['temperature'] = vals.value.to_numpy()[0:minsamps]
    vals['humidity'] = hums.value.to_numpy()[0:minsamps]
    vals['pressure'] = pres.value.to_numpy()[0:minsamps]
    vals['rainfall'] = rain.value.to_numpy()[0:minsamps]

    direction = winds[winds['name']=='wxt.wind.direction']
    speed = winds[winds['name']=='wxt.wind.speed']

    nspeed = len(speed)
    ndir = len(direction)
    print(nspeed, ndir)
    minsamps = min([nspeed, ndir])

    speed['time'] = pd.DatetimeIndex(speed['timestamp'].values)
    windy = speed.set_index('time')[0:minsamps]
    windy['speed'] = windy.value.to_numpy()[0:minsamps]
    windy['direction'] = direction.value.to_numpy()[0:minsamps]


    winds10mean = windy.resample('10s').mean(numeric_only=True).ffill()
    winds10max = windy.resample('10s').max(numeric_only=True).ffill()
    dp = dewpoint_from_relative_humidity( vals.temperature.to_numpy() * units.degC, 
                                         vals.humidity.to_numpy() * units.percent)

    vals['dewpoint'] = dp
    vals10 = vals.resample('10s').mean(numeric_only=True).ffill() #ffil gets rid of nans due to empty resample periods
    wb = wet_bulb_temperature(vals10.pressure.to_numpy() * units.hPa,
                              vals10.temperature.to_numpy() * units.degC,
                              vals10.dewpoint.to_numpy() * units.degC)

    vals10['wetbulb'] = wb
    vals10['wind_dir_10s'] = winds10mean['direction']
    vals10['wind_mean_10s'] = winds10mean['speed']
    vals10['wind_max_10s'] = winds10max['speed']
    _ = vals10.pop('value')
    
    end_fname = st.strftime('_%Y%m%d_%H%M%S.nc')
    start_fname = odir + '/crocus-' + global_attrs['site_ID'] + '-' + 'wxt-'+ global_attrs['datalevel']
    fname = start_fname + end_fname
    
    try:
        os.remove(fname)
    except OSError:
        pass
    
    vals10xr = xr.Dataset.from_dataframe(vals10)
    vals10xr = vals10xr.sortby('time')
    
    vals10xr = vals10xr.assign_attrs(global_attrs)
    
    for varname in var_attrs.keys():
        vals10xr[varname] = vals10xr[varname].assign_attrs(var_attrs[varname])
    
    vals10xr.to_netcdf(fname)

if __name__ == '__main__':
    
    # Site attributes

    wxt_global_NEIU = {'conventions': "CF 1.10",
                       'site_ID' : "NEIU",
                       'CAMS_tag' : "CMS-WXT-002",
                       'datastream' : "CMS_wxt536_NEIU_a1",
                       'datalevel' : "a1",
                       'plugin' : "registry.sagecontinuum.org/jrobrien/waggle-wxt536:0.*",
                       'WSN' : 'W08D',
                       'latitude' : 41.9804526,
                       'longitude' : -87.7196038}

    wxt_global_NU = {'conventions': "CF 1.10",
                     'WSN':'W099',
                     'site_ID' : "NU",
                     'CAMS_tag' : "CMS-WXT-005",
                     'datastream' : "CMS_wxt536_NU_a1",
                     'plugin' : "registry.sagecontinuum.org/jrobrien/waggle-wxt536:0.*",
                     'datalevel' : "a1",
                     'latitude' : 42.051469749,
                     'longitude' : -87.677667183}

    wxt_global_CSU = {'conventions': "CF 1.10",
                      'WSN':'W08E',
                      'site_ID' : "CSU",
                      'CAMS_tag' : "CMS-WXT-003",
                      'datastream' : "CMS_wxt536_CSU_a1",
                      'plugin' : "registry.sagecontinuum.org/jrobrien/waggle-wxt536:0.*",
                      'datalevel' : "a1",
                      'latitude' : 41.71996846,
                      'longitude' : -87.612805717}

    wxt_global_ATMOS = {'conventions': "CF 1.10",
                        'WSN':'W0A4',
                        'site_ID' : "ATMOS",
                        'CAMS_tag' : "CMS-WXT-001",
                        'datastream' : "CMS_wxt536_ATMOS_a1",
                        'plugin' : "registry.sagecontinuum.org/jrobrien/waggle-wxt536:0.*",
                        'datalevel' : "a1",
                        'latitude' : 41.7016264,
                        'longitude' : -87.9956515}

    wxt_global_UIC = {'conventions': "CF 1.10",
                      'WSN':'W096',
                      'site_ID' : "UIC",
                      'CAMS_tag' : "CMS-WXT-006",
                      'datastream' : "CMS_wxt536_UIC_a1",
                      'plugin' : "registry.sagecontinuum.org/jrobrien/waggle-wxt536:0.*",
                      'datalevel' : "a1",
                      'latitude' : 41.869407936,
                      'longitude' : -87.645806251}

    wxt_global_CCI = {'conventions': "CF 1.10",
                      'WSN':'W08B',
                      'site_ID' : "NEIU_CCIS",
                      'CAMS_tag' : "CMS-WXT-013",
                      'datastream' : "CMS_wxt536_NEIU_CCICS_a1",
                      'plugin' : "registry.sagecontinuum.org/jrobrien/waggle-wxt536:0.*",
                      'datalevel' : "a1",
                      'latitude' : 41.823038311,
                      'longitude' : -87.609379028}
    
    wxt_global_BIG = {'conventions': "CF 1.10",
                      'WSN':'W0A0',
                      'site_ID' : "BIG",
                      'CAMS_tag' : "CMS-WXT-016",
                      'datastream' : "CMS_wxt536_BIG_a1",
                      'plugin' : "registry.sagecontinuum.org/jrobrien/waggle-wxt536:0.*",
                      'datalevel' : "a1",
                      'latitude' : 41.77702369,
                      'longitude' : -87.609721059}

    wxt_global_HUM = {'conventions': "CF 1.10",
                      'WSN':'W0A1',
                      'site_ID' : "HUM",
                      'CAMS_tag' : "CMS-WXT-010",
                      'datastream' : "CMS_wxt536_HUM_a1",
                      'plugin' : "registry.sagecontinuum.org/jrobrien/waggle-wxt536:0.*",
                      'datalevel' : "a1",
                      'latitude' : 41.905513206,
                      'longitude' : -87.703525713}
    
    wxt_global_DOWN = {'conventions': "CF 1.10",
                      'WSN':'W09D',
                      'site_ID' : "DOWN",
                      'CAMS_tag' : "CMS-WXT-008",
                      'datastream' : "CMS_wxt536_DOWN_a1",
                      'plugin' : "registry.sagecontinuum.org/jrobrien/waggle-wxt536:0.*",
                      'datalevel' : "a1",
                      'latitude' : 41.701476659,
                      'longitude' : -87.9953044}
    
    wxt_global_SHEDD = {'conventions': "CF 1.10",
                        'WSN':'W09E',
                        'site_ID' : "SHEDD",
                        'CAMS_tag' : "CMS-WXT-007",
                        'datastream' : "CMS_wxt536_SHEDD_a1",
                        'plugin' : "registry.sagecontinuum.org/jrobrien/waggle-wxt536:0.*",
                        'datalevel' : "a1",
                        'latitude' : 41.867918965,
                        'longitude' : -87.613535027}
    
    wxt_global_VLPK = {'conventions': "CF 1.10",
                       'WSN':'W095',
                       'site_ID' : "VLPK",
                       'CAMS_tag' : "CMS-WXT-004",
                       'datastream' : "CMS_wxt536_VLPK_a1",
                       'plugin' : "registry.sagecontinuum.org/jrobrien/waggle-wxt536:0.*",
                       'datalevel' : "a1",
                       'latitude' : 41.884884633,
                       'longitude' : -87.978717410}
    #put these in a dictionary for accessing

    global_sites = {'NU' : wxt_global_NU, 
                    'CSU': wxt_global_CSU,
                    'NEIU' : wxt_global_NEIU,
                    'ATMOS': wxt_global_ATMOS,
                    'UIC': wxt_global_UIC,
                    'NEIU_CCICS': wxt_global_CCI,
                    "BIG": wxt_global_BIG,
                    'HUM': wxt_global_HUM,
                    "DOWN": wxt_global_DOWN,
                    "SHEDD": wxt_global_SHEDD,
                    "VLPK": wxt_global_VLPK}

    #Variable attributes

    var_attrs_wxt = {'temperature': {'standard_name' : 'air_temperature',
                           'units' : 'celsius'},
                    'humidity': {'standard_name' : 'relative_humidity',
                           'units' : 'percent'},
                    'dewpoint': {'standard_name' : 'dew_point_temperature',
                           'units' : 'celsius'},
                    'pressure': {'standard_name' : 'air_pressure',
                           'units' : 'hPa'},
                    'wind_mean_10s': {'standard_name' : 'wind_speed',
                           'units' : 'celsius'},
                    'wind_max_10s': {'standard_name' : 'wind_speed',
                           'units' : 'celsius'},
                    'wind_dir_10s': {'standard_name' : 'wind_from_direction',
                           'units' : 'degrees'},
                    'rainfall': {'standard_name' : 'precipitation_amount',
                           'units' : 'kg m-2'}}

    
    #Parsing the command line
    current = datetime.datetime.utcnow()
    parser = argparse.ArgumentParser(description='Optional app description')
    
    parser.add_argument('--ndays', type=int, default=1,
                    help='number of days to ingest')
    
    parser.add_argument('--y', type=int, default=current.year,
                    help='Year start')
    
    parser.add_argument('--m', type=int, default=current.month,
                    help='Month start')
    
    parser.add_argument('--d', type=int, default=current.day,
                    help='day start')
    
    parser.add_argument('--site', type=str, default="NEIU",
                    help='CROCUS Site')

    parser.add_argument('--odir', type=str,
                    help='Out directory (must exist)')

    args = parser.parse_args()
    print(args.ndays)
    start_date = datetime.datetime(args.y,args.m,args.d)
    site_args = global_sites[args.site]
    
    for i in range(args.ndays):
        this_date = start_date + datetime.timedelta(days=i)
        print(this_date)
        try:
            ingest_wxt(this_date,  site_args, var_attrs_wxt, odir=args.odir)
            print("Succeed")
        except Exception as e:
            print("Fail", e)
    
