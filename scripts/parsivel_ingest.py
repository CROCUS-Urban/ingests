import pydsd
import xarray as xr
import glob
import sys
import os
import numpy as np
import argparse

from netCDF4 import num2date, date2num
from ArgonneParsivelReader import read_adm_parsivel
from datetime import datetime


def process_parsivel(fi, radar_frequency=None):
    """
    Process raw output from the Parsivel on the Argonne Deployable Mast.

    Parameters
    ----------
    fi: str
        The name of the file to process.    
    radar_frequency: float
        If radar moments are to be processed into a b1-level product, then the radar frequency in Hz.
        Set to None to skip processing radar moments to create an a1-level product with the PSDs and curve fits.
    """
    my_dsd = read_adm_parsivel(fi)
    print("PSD read in")
    # MRR2 Frequency is 24 Ghz
    # W-band is 95 Ghz
    
    my_dsd.Nd["data"] = my_dsd.Nd["data"].filled(0)
    params_list = ["Zh", "Zdr", "delta_co", "Kdp", "Ai", "Adr", "D0", "Dmax", "Dm", "Nt", "Nw", "N0", "W", "mu", "Lambda"]
    
    my_dsd.calculate_dsd_parameterization()
    out_ds = xr.Dataset()
    out_ds["time"] = ('time', my_dsd.time["data"])
    out_ds["bin_edges"] = ('bin_edges', my_dsd.bin_edges["data"])
    out_ds["bin_edges"].attrs = my_dsd.bin_edges
    del out_ds["bin_edges"].attrs["data"]
    out_ds["Nd"] = (['time', 'bins'], my_dsd.Nd["data"])
    out_ds["Nd"].attrs = my_dsd.Nd
    del out_ds["Nd"].attrs["data"]
    out_ds["rain_rate"] = (['time'], my_dsd.rain_rate["data"])
    del my_dsd.rain_rate["data"]
    out_ds["rain_rate"].attrs = my_dsd.rain_rate
    if radar_frequency is not None:
        my_dsd.set_scattering_temperature_and_frequency(scattering_freq=24e6)
        my_dsd.calculate_radar_parameters()
        print("Scattering done")
        params_list = ["Zh", "Zdr", "delta_co", "Kdp", "Ai", "Adr", "D0", "Dmax", "Dm", "Nt", "Nw", "N0", "W", "mu", "Lambda"]
        for param in params_list:
            out_ds[param] = (['time'], my_dsd.fields[param]["data"])
            out_ds[param].attrs = my_dsd.fields[param]
            del out_ds[param].attrs["data"]
    else:
        params_list = ["D0", "Dmax", "Dm", "Nt", "Nw", "N0", "W", "mu", "Lambda"]
        for param in params_list:
            out_ds[param] = (['time'], my_dsd.fields[param]["data"])
            out_ds[param].attrs = my_dsd.fields[param]
            del out_ds[param].attrs["data"]
    out_ds['bins'] = (['bins'],
                      (out_ds['bin_edges'][1:].values+out_ds['bin_edges'][:-1].values)/2)
    out_ds['bins'].attrs["long_name"] = "Bin mid points"
    out_ds['bins'].attrs["units"] = "mm"
    out_ds.attrs["site"] = "Argonne Deployable Mast"
    out_ds.attrs["mentors"] = "Liz Wawrzyniak, Joseph O'Brien, Bobby Jackson"
    out_ds.attrs['mentor_emails'] = "ewawrzyniak@anl.gov, obrien@anl.gov, rjackson@anl.gov"
    out_ds.attrs['mentor_institution'] = 'Argonne National Laboratory'
    out_ds.attrs['mentor_orcids'] = "0000-0003-4655-6912, 0000-0003-2518-1234"
    out_ds.attrs['contributors'] = "Scott Collis, Paytsar Muradyan, Max Grover, Matt Tuftedal"
    return out_ds

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog='ParsivelIngest',
        description='Parsivel data ingest')
    parser.add_argument('file_path', help='Path to parsivel .txt file')
    parser.add_argument('--output_path', default=os.getcwd(), help='Path to output directory')
    parser.add_argument('--frequency', default=None,
                         help="Radar frequency for generating radar moments." + 
                              "This will make the data level b1 instead of a1.")
    args = parser.parse_args()
    out_ds = process_parsivel(args.file_path, args.frequency)
    if args.frequency is None:
        data_level = "a1"
    else:
        data_level = "b1"
    init_time = datetime.fromtimestamp(out_ds.time.values[0])
    out_ds["time"] = out_ds["time"].astype("datetime64[s]")
    file_date = init_time.strftime('%Y%m%d.%H%M%S')
    out_file = os.path.join(args.output_path, f'ADM.parsivel.{file_date}.{data_level}.nc')
    out_ds.to_netcdf(out_file)

    













