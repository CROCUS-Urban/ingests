import pydsd
import xarray as xr
import os
import numpy as np
import argparse
import requests
import sage_data_client

from netCDF4 import num2date, date2num
from ArgonneParsivelReader import read_adm_parsivel
from datetime import datetime, timedelta
from distributed import Client, LocalCluster

def filter_spectrum_with_parsivel_matrix(
    dsd,
    over_fall_speed=0.5,
    under_fall_speed=0.5,
    replace=False,
    maintain_smallest=False,
):
    """ Filter a drop spectrum using fall speed matrix for Parsivels.  This requires that velocity is set on the object
    for both raw spectra and calculated terminal fall speed. If terminal fall speed is not available, this can be calculated
    using pydsd.
    Parameters
    ----------
    over_fall_speed: float, default 0.5
        Filter out drops more than this factor of terminal fall speed.
    under_fall_speed: float, default 0.5
        Filter out drops more than this factor under terminal fall speed.
    maintain_smallest: boolean, default False
        For D<1, set V<2.5 bins all to positive to make sure small drops aren't dropped in PCM matrix.


    Returns
    -------
    filtered_spectrum_data_array: np.ndarray
        Filtered Drop Spectrum Array

    Example
    -------
    filter_spectrum_with_parsivel_matrix(dsd, over_fall_speed=.5, under_fall_speed=.5, replace=True)
    """
    terminal_fall_speed = dsd.velocity["data"]
    spectra_velocity = dsd.spectrum_fall_velocity["data"]

    pcm_matrix = np.zeros((len(terminal_fall_speed), len(spectra_velocity)))
    for idx in np.arange(0, len(terminal_fall_speed)):
        pcm_matrix[idx] = np.logical_and(
            spectra_velocity > (terminal_fall_speed[idx] * (1 - under_fall_speed)),
            spectra_velocity < (terminal_fall_speed[idx] * (1 + over_fall_speed)),
        )

    # print(pcm_matrix)
    pcm_matrix = pcm_matrix.astype(int).T
    if maintain_smallest:
        dbins_under_1 = np.sum(dsd.diameter["data"] <= 1)
        vbins_under_25 = np.sum(spectra_velocity < 2.5)
        print(vbins_under_25, dbins_under_1)
        pcm_matrix[0:vbins_under_25, 0:dbins_under_1] = 1


    if replace:
        dsd.fields["raw"]["data"] = (
            dsd.fields["raw"]["data"] * pcm_matrix
        )
        dsd.fields["raw"]["history"] = (
            dsd.fields["raw"].get("history", "")
            + f"Filtered for speeds above {over_fall_speed} of Vt and below {under_fall_speed} of Vt"
        )
    else:
        return dsd.fields["raw"]["data"] * pcm_matrix


def process_parsivel(day, radar_frequency=None, node="W09A", username="", password=""):
    """
    Process raw output from the Parsivel on the Argonne Deployable Mast.

    Parameters
    ----------
    fi: str
        The name of the file to process.    
    radar_frequency: float
        If radar moments are to be processed into a b1-level product, then the radar frequency in Hz.
        Set to None to skip processing radar moments to create an a1-level product with the PSDs and curve fits.
    node: str
        WSN for node
    username: str
        Waggle username
    password: str
        Waggle password
    """
    start = day.strftime('%Y-%m-%dT%H:%M:%SZ')
    end = (day + timedelta(days=1)).strftime('%Y-%m-%dT%H:%M:%SZ')
    print(start)
    df_files = sage_data_client.query(
            start=start,
            end=end, 
            filter={
                "name" : 'upload',
                "plugin": "registry.sagecontinuum.org/jrobrien/waggle-parsivel-io:0.25.02.04.*",
                "vsn" : node,
            }
        )
    print(df_files)
    ds_list = []
    #for filename in df_files["value"]:
    def get_psd(filename):
        response = requests.get(filename, auth=(username, password))
        base, name = os.path.split(filename)
        if response.status_code == 200:
            # Save the file locally
            with open(name, "wb") as file:
                file.write(response.content)

        base, name = os.path.split(filename)

        my_dsd = read_adm_parsivel(name)
        print("PSD read in")
        # MRR2 Frequency is 24 Ghz
        # W-band is 95 Ghz

        if len(my_dsd.Nd["data"]) == 0:
            print("Empty file, skipping.")
            return None
        
        my_dsd.Nd["data"] = np.where(my_dsd.Nd["data"] == -9.999, np.nan,
                my_dsd.Nd["data"])
     
        my_dsd.calculate_dsd_parameterization()
        out_ds = xr.Dataset()
        out_ds["time"] = ('time', my_dsd.time["data"])
        out_ds["bin_edges"] = ('bin_edges', my_dsd.bin_edges["data"])
        out_ds["bin_edges"].attrs = my_dsd.bin_edges
        del out_ds["bin_edges"].attrs["data"]
        out_ds["velocity"] = ('bins', my_dsd.velocity["data"])
        out_ds["velocity"].attrs = my_dsd.velocity
        del out_ds["velocity"].attrs["data"]
        out_ds["Nd"] = (['time', 'bins'], my_dsd.Nd["data"])
        out_ds["Nd"].attrs = my_dsd.Nd
        del out_ds["Nd"].attrs["data"]
        out_ds["num_particles"] = (['time'], my_dsd.num_particles["data"])
        out_ds["num_particles"].attrs = my_dsd.num_particles
        del out_ds["num_particles"].attrs["data"]
        out_ds["spectrum_fall_velocity"] = (['time', 'bins'], my_dsd.spectrum_fall_velocity["data"])
        out_ds["spectrum_fall_velocity"].attrs = my_dsd.spectrum_fall_velocity
        del out_ds["spectrum_fall_velocity"].attrs["data"]
        out_ds["rain_rate"] = (['time'], my_dsd.rain_rate["data"])
        del my_dsd.rain_rate["data"]
        out_ds["rain_rate"].attrs = my_dsd.rain_rate
        
        if radar_frequency is not None:
            my_dsd.set_scattering_temperature_and_frequency(
                    scattering_freq=float(radar_frequency))
            my_dsd.calculate_radar_parameters()
            print("Scattering done")
            params_list = ["Zh", "Zdr", "delta_co", "Kdp",
                    "Ai", "Adr", "D0", "Dmax", "Dm",
                    "Nt", "Nw", "N0", "W", "mu", "Lambda",
                    "sensor_status", "error_code", "num_particles_validated",
                    "power_supply_voltage", "sensor_head_heating_current",
                    "sensor_heating_temperature", "temperature_right_head",
                    "temperature_left_head", "sensor_time"]
            for param in params_list:
                out_ds[param] = (['time'], my_dsd.fields[param]["data"])
                out_ds[param].attrs = my_dsd.fields[param]
                del out_ds[param].attrs["data"]
        else:
            params_list = ["D0", "Dmax", "Dm", "Nt", "Nw",
                    "N0", "W", "mu", "Lambda",
                    "sensor_status", "error_code", "num_particles_validated",
                    "power_supply_voltage", "sensor_head_heating_current",
                    "sensor_heating_temperature", "temperature_right_head",
                    "temperature_left_head", "sensor_time"]
            for param in params_list:
                out_ds[param] = (['time'], my_dsd.fields[param]["data"])
                out_ds[param].attrs = my_dsd.fields[param]
                del out_ds[param].attrs["data"]
        out_ds['bins'] = (['bins'],
                        (out_ds['bin_edges'][1:].values+out_ds['bin_edges'][:-1].values)/2)
        out_ds['bins'].attrs["long_name"] = "Bin mid points"
        out_ds['bins'].attrs["units"] = "mm"
        out_ds.attrs["site"] = "Argonne Deployable Mast"
        out_ds.attrs["mentors"] = "Liz Wawrzyniak, Joseph O'Brien, Bobby Jackson, Bhupendra Raut"
        out_ds.attrs['mentor_emails'] = "ewawrzyniak@anl.gov, obrienj@anl.gov, rjackson@anl.gov, braut@anl.gov"
        out_ds.attrs['mentor_institution'] = 'Argonne National Laboratory'
        out_ds.attrs['mentor_orcids'] = "0000-0003-4655-6912, 0000-0003-2518-1234"
        out_ds.attrs['contributors'] = "Scott Collis, Paytsar Muradyan, Max Grover, Matt Tuftedal"
        out_ds["time"] = out_ds["time"].astype("datetime64[s]")
        os.remove(name)
        return out_ds

    with Client(LocalCluster(n_workers=16)) as c:
        futures = c.map(get_psd, df_files["value"])
        ds_list = c.gather(futures)
        ds_list = [x for x in ds_list if x is not None]

    out_ds = xr.concat(ds_list, dim='time').sortby("time")
    return out_ds

site_dict = {"W09A": "adm", "W09F": "atmos"}

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog='ParsivelIngest',
        description='Parsivel data ingest')
    parser.add_argument('--date', default=datetime.now().strftime('%Y%m%d'), 
                        help='Day to process in [YYYYMMDD] format, default is today')
    parser.add_argument('--output_path', default=os.getcwd(), help='Path to output directory')
    parser.add_argument('--node', default="W09A", help='Waggle node number containing data')
    parser.add_argument('--frequency', default=None,
                         help="Radar frequency for generating radar moments." + 
                              "This will make the data level b1 instead of a1.")
    parser.add_argument('--waggle_username', default="", 
                        help='Waggle username.')
    parser.add_argument('--waggle_password', default="", 
                        help='Waggle password.')
    args = parser.parse_args()
    day = datetime.strptime(args.date, '%Y%m%d')
    username = args.waggle_username
    password = args.waggle_password
    out_ds = process_parsivel(day, args.frequency, args.node, username, password)
    
    if args.frequency is None:
        data_level = "a1"
    else:
        data_level = "b1"
    
    # Plugin starts uploading data from previous day at 2355Z.
    day = day.strftime('%Y%m%d')
    file_date = f'{day}.000000'
    node = args.node
    site = site_dict[node]
    del out_ds["sensor_time"].attrs["units"]
    print(out_ds)
    out_file = os.path.join(args.output_path, f'crocus.{site}.parsivel.{file_date}.{data_level}.nc')
    out_ds.to_netcdf(out_file)

    













