"""Ingests a number of days of CROCUS WXT data

Usage:
    python ./ingest-aqt.py ndays year month day site out_directory
    For example, for the Northwestern site on June 20, 2024, one would use, and output would be in the current directory
    python ingest-aqt.py 1 2024 6 20 NU .

Author:
    Scott Collis - 5.9.2024
"""

import sage_data_client
import matplotlib.pyplot as plt
import pandas as pd
from metpy.calc import dewpoint_from_relative_humidity, wet_bulb_temperature
from metpy.units import units
import numpy as np
import datetime
import xarray as xr
import os
import argparse


from matplotlib.dates import DateFormatter

def ingest_aqt(st, global_attrs, var_attrs, odir='.' ):
    """
        Ingest from CROCUS AQTs using the Sage Data Client. 

        Ingests a whole day of AQT data and saves it as a NetCDF to odir
    
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
    df_aq = sage_data_client.query(start=start,
                                   end=end, 
                                        filter={
                                            "plugin" : global_attrs['plugin'],
                                            "vsn" : global_attrs['WSN'],
                                            "sensor" : "vaisala-aqt530"
                                        }
    )
     # Rename specific column names
    pm25 = df_aq[df_aq['name']=='aqt.particle.pm2.5']
    pm10 = df_aq[df_aq['name']=='aqt.particle.pm1']
    pm100 = df_aq[df_aq['name']=='aqt.particle.pm10']
    no = df_aq[df_aq['name']=='aqt.gas.no']
    o3 = df_aq[df_aq['name']=='aqt.gas.ozone']
    no2 = df_aq[df_aq['name']=='aqt.gas.no2']
    co = df_aq[df_aq['name']=='aqt.gas.co']
    aqtemp = df_aq[df_aq['name']=='aqt.env.temp']
    aqhum = df_aq[df_aq['name']=='aqt.env.humidity']
    aqpres = df_aq[df_aq['name']=='aqt.env.pressure']

    # Convert instrument timestamp to Pandas Datatime object
    pm25['time'] = pd.DatetimeIndex(pm25['timestamp'].values)

    # Remove all meta data descriptions besides the index
    aqvals = pm25.loc[:, pm25.columns.intersection(["time"])]

    # Add all parameter to the output dataframe
    aqvals['pm2.5'] = pm25.value.to_numpy().astype(float)
    aqvals['pm1.0'] = pm10.value.to_numpy().astype(float)
    aqvals['pm10.0'] = pm100.value.to_numpy().astype(float)

    aqvals['no'] = no.value.to_numpy().astype(float)
    aqvals['o3'] = o3.value.to_numpy().astype(float)
    aqvals['no2'] = no2.value.to_numpy().astype(float)
    aqvals['co'] = co.value.to_numpy().astype(float)
    aqvals['temperature'] =  aqtemp.value.to_numpy().astype(float)
    aqvals['humidity'] =  aqhum.value.to_numpy().astype(float)
    aqvals['pressure'] =  aqpres.value.to_numpy().astype(float)

    # calculate dewpoint from relative humidity
    dp = dewpoint_from_relative_humidity(aqvals.temperature.to_numpy() * units.degC, 
                                         aqvals.humidity.to_numpy() * units.percent
    )
    aqvals['dewpoint'] = dp
    
    # Define the index
    aqvals = aqvals.set_index("time")
    
    end_fname = st.strftime('-%Y%m%d-%H%M%S.nc')
    start_fname = odir + '/crocus-' + global_attrs['site_ID'] + '-' + 'aqt-'+ global_attrs['datalevel']
    fname = start_fname + end_fname
    valsxr = xr.Dataset.from_dataframe(aqvals)
    valsxr = valsxr.sortby('time')
    
    # Assign the global attributes
    valsxr = valsxr.assign_attrs(global_attrs)
    # Assign the individual parameter attributes
    for varname in var_attrs.keys():
        valsxr[varname] = valsxr[varname].assign_attrs(var_attrs[varname])
    # Check if file exists and remove if necessary
    try:
        os.remove(fname)
    except OSError:
        pass
    
    # ---------
    # Apply QC
    #----------
    # Check for aerosol water vapor uptake and mask out
    cond = (0 < valsxr.humidity) & (valsxr.humidity < 98)
    valsxr = valsxr.where(cond, drop=False) 
    
    # Ensure time is saved properly
    valsxr["time"] = pd.to_datetime(valsxr.time)

    if valsxr['pm2.5'].shape[0] > 0:
        valsxr.to_netcdf(fname, format='NETCDF4')
    else:
        print('not saving... no data')

if __name__ == '__main__':
    
    # Site attributes
    
    wxt_global_NEIU = {'conventions': "CF 1.10",
                       'site_ID' : "NEIU",
                      'CAMS_tag' : "CMS-WXT-002",
                      'datastream' : "CMS_wxt536_NEIU_a1",
                      'datalevel' : "a1",
                       "plugin" : "registry.sagecontinuum.org/jrobrien/waggle-aqt:0.23.5.04",
                       'WSN' : 'W08D',
                      'latitude' : 41.9804526,
                      'longitude' : -87.7196038}
    
    wxt_global_NU = {'conventions': "CF 1.10",
                      'WSN':'W099',
                       'site_ID' : "NU",
                      'CAMS_tag' : "CMS-WXT-005",
                      'datastream' : "CMS_wxt536_NU_a1",
                      'plugin' : "registry.sagecontinuum.org/jrobrien/waggle-aqt:0.23.5.04",
                      'datalevel' : "a1",
                      'latitude' : 42.051469749,
                      'longitude' : -87.677667183}
    
    wxt_global_CSU = {'conventions': "CF 1.10",
                      'WSN':'W08E',
                       'site_ID' : "CSU",
                      'CAMS_tag' : "CMS-WXT-003",
                      'datastream' : "CMS_wxt536_CSU_a1",
                      'plugin' : "registry.sagecontinuum.org/jrobrien/waggle-aqt:0.23.5.04",
                      'datalevel' : "a1",
                      'latitude' : 41.71991216,
                      'longitude' : -87.612834722}
    
    #put these in a dictionary for accessing
    
    global_sites = {'NU' : wxt_global_NU, 
                    'CSU': wxt_global_CSU,
                    'NEIU' : wxt_global_NEIU}
    
    
    #Variable attributes
    
    var_attrs_aqt = {'pm2.5' : {'standard_name' : 'mole_concentration_of_pm2p5_ambient_aerosol_particles_in_air',
                                'units' : 'ug/m^3'},
                    'pm10.0' : {'standard_name' : 'mole_concentration_of_pm10p0_ambient_aerosol_particles_in_air',
                                'units' : 'ug/m^3'},
                    'pm1.0' : {'standard_name' : 'mole_concentration_of_pm1p0_ambient_aerosol_particles_in_air',
                               'units' : 'ug/m^3'},
                    'no' : {'standard_name' : 'mole_fraction_of_nitrogen_monoxide_in_air',
                            'units' : 'Parts Per Million'},
                    'o3' : {'standard_name' : 'mole_fraction_of_ozone_in_air',
                            'units' : 'Parts Per Million'},
                    'co' : {'standard_name' : 'mole_fraction_of_carbon_monoxide_in_air',
                            'units' : 'Parts Per Million'},
                    'no2' : {'standard_name' : 'mole_fraction_of_nitrogen_dioxide_in_air',
                            'units' : 'Parts Per Million'},
                    'temperature': {'standard_name' : 'air_temperature',
                            'units' : 'celsius'},
                    'humidity': {'standard_name' : 'relative_humidity',
                            'units' : 'percent'},
                    'dewpoint': {'standard_name' : 'dew_point_temperature',
                            'units' : 'celsius'},
                    'pressure': {'standard_name' : 'air_pressure',
                            'units' : 'hPa'}}

    # Set the default day, month, year to the current day
    current =  datetime.datetime.now(datetime.timezone.utc)
    
    #Parsing the command line
    
    parser = argparse.ArgumentParser(description='Optional app description')
    
    parser.add_argument('--ndays', type=int, default=1
                    help='number of days to ingest')
    
    parser.add_argument('--y', type=int, default=current.year,
                    help='Year start')
    
    parser.add_argument('--m', type=int, default=current.month,
                    help='Month start')
    
    parser.add_argument('--d', type=int, default=current.day,
                    help='day start')
    
    parser.add_argument('--site', type=str,
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
            ingest_aqt(this_date,  site_args, var_attrs_aqt, odir=args.odir)
            print("Succeed")
        except Exception as e:
            print("Fail", e)
