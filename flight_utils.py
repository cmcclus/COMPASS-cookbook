import netCDF4
import pathlib as path
import pandas as pd
import numpy as np
import os
from datetime import datetime, timedelta
from fnmatch import fnmatch
from typing import Iterable

# vars_to_read is the default set of variables that get read when calling read_nc below when
# variables are not specified (i.e. when called like "utils.read_nc(netcdf_obj)"). 
vars_to_read = ['Time','GGALT','LATC','LONC', # 4-D Position
                'UIC','VIC','WIC',            # winds
                'ATX','PSFC','EWX',           # other state params
               ]

def sfm_to_datetime(sfm: Iterable[float], tunits: str) -> list[datetime]:
    """
    sfm_to_datetime converts an iterable of seconds from midnight with units of tunits to a list

    :param sfm: An iterable/array of times with units of seconds from UTC midnight
    :param tunits: A string defining the units of sfm. Expected to be in the form of "seconds from YYYY-MM-DD 00:00:00 +0000"

    :return: Returns a list of Python datetimes.
    """

    deltas = np.array([timedelta(seconds=float(s)) for s in sfm])
    tunits_split = tunits.split(' ')
    #t0_iso_str = tunits_split[2]+"T"+tunits_split[3]+tunits_split[4]
    t0_iso_str = tunits_split[2][0:10]+"T00:00:00+0000"
    t0_dt = datetime.fromisoformat(t0_iso_str)
    
    dts = [t0_dt + delta for delta in deltas]
    return dts

def find_flight_fnames(dir_path: str) -> list[str]:
    """
    find_flight_fnames just searches a directory for all *.nc files and returns a list of them.

    :param dir_path: a path to the directory containing flight netcdf files

    :return: Returns a list of flight netcdf files.
    """
    flight_fnames = sorted([fname for fname in os.listdir(dir_path) if fnmatch(fname, "*.nc")])
    return flight_fnames

def open_flight_nc(file_path: str) -> netCDF4._netCDF4.Dataset:
    """
    open_flight_nc simply checks to see if the file at the provided path string exists and opens it.

    :param file_path: A path string to a flight data file, e.g. "./test/test_flight.nc"

    :return: Returns netCDF4._netCDF4.Dataset object.
    """

    fp_path = path.Path(file_path)
    if not fp_path.is_file():
        raise FileNotFoundError('testing excptions')

    return netCDF4.Dataset(file_path)

def read_flight_nc_25hz(nc: netCDF4._netCDF4.Dataset, read_vars: list[str] = vars_to_read) -> pd.DataFrame:
    """
    read_flight_nc reads a set of variables into memory.

    NOTE: a high-rate, usually 25 Hz, flight data file is assumed.

    :param nc: netCDF4._netCDF4.Dataset object opened by open_flight_nc.
    :param read_vars: An optional list of strings of variable names to be read into memory. A default
                      list, vars_to_read, is specified above. Passing in a similar list will read in those variables
                      instead.

    :return: Returns a pandas data frame.
    """

    data = [] # an empty list to accumulate Dataframes of each variable to be read in

    hz = 25
    sub_seconds = np.arange(0,25,1)/25.

    for var in read_vars:
        try:
            if var == "Time":
                # time is provided every second, so need to calculate 25 Hz times efficiently
                tunits = getattr(nc[var],'units')
                time = nc[var][:]

                time_25hz = np.zeros((len(time),hz)) # 2-D
                for i,inc in enumerate(sub_seconds):
                    time_25hz[:,i] = time + inc
                output = np.ravel(time_25hz) # ravel to 1-D
                data.append(pd.DataFrame({var: output}))
                dt_list = sfm_to_datetime(output, tunits)
                data.append(pd.DataFrame({'datetime': dt_list}))
            else:
                ndims = len(np.shape(nc[var][:]))
                if ndims == 2:
                    # 2-D, 25 Hz variables can just be raveled into 1-D time series
                    output = np.ravel(nc[var][:])
                    data.append(pd.DataFrame({var: output}))
                elif ndims == 1:
                    # 1-D variables in 25 Hz data files exist (e.g. GGALT is sampled at 20 Hz, but by default,
                    # this is filtered to 1Hz instead of fudged to 25 Hz). Do interpolation to 25 Hz so all time series
                    # have same length.
                    output_1d = nc[var][:]
                    output_2d = np.zeros((len(output_1d),hz))*float("NaN")
                    for i in range(len(output_1d)-1):
                        output_2d[i,:] = output_1d[i] + sub_seconds*(output_1d[i+1]-output_1d[i]) # divide by 1s omitted
                    output = np.ravel(output_2d)
                    data.append(pd.DataFrame({var: output}))
                else:
                    raise RuntimeError(f"Variable {var} is {ndims}-dimensional. Only 1-D or 2-D variables are handled.")
        except Exception as e:
            #print(f"Issue reading {var}: {e}")
            pass
              

    # concatenate the list of dataframes into a single dataframe and return it
    return pd.concat(data, axis=1, ignore_index=False)

def read_flight_nc_1hz(nc: netCDF4._netCDF4.Dataset, read_vars: list[str] = vars_to_read) -> pd.DataFrame:
    """
    read_flight_nc reads a set of variables into memory.

    NOTE: a low-rate, 1 Hz, flight data file is assumed

    :param nc: netCDF4._netCDF4.Dataset object opened by open_flight_nc.
    :param read_vars: An optional list of strings of variable names to be read into memory. A default
                      list, vars_to_read, is specified above. Passing in a similar list will read in those variables
                      instead.

    :return: Returns a pandas data frame.
    """

    data = [] # an empty list to accumulate Dataframes of each variable to be read in
    for var in read_vars:
        try:
            if var == "Time":
                # time is provided every second, so need to calculate 25 Hz times efficiently
                tunits = getattr(nc[var],'units')
                time = nc[var][:]
                data.append(pd.DataFrame({var: time}))
                dt_list = sfm_to_datetime(time, tunits)
                data.append(pd.DataFrame({'datetime': dt_list}))
            else:
                output = nc[var][:]
                data.append(pd.DataFrame({var: output}))
        except Exception as e:
            #print(f"Issue reading {var}: {e}")
            pass
    

    # concatenate the list of dataframes into a single dataframe and return it
    return pd.concat(data, axis=1, ignore_index=False)

def read_flight_nc(nc: netCDF4._netCDF4.Dataset, read_vars: list[str] = vars_to_read) -> pd.DataFrame:
    """
    read_flight_nc simply figures out if the flight netcdf object is 1 hz or 25 hz and calls the appropriate reader.

    :param nc: A netcdf object for a flight netcdf file.
    :param read_vars: A list of variable names to be read in the netcdf object. Optional. Default is "vars_to_read" specified
                      above.

    :return: Returns Pandas DataFrame
    """
    dim_names = list(nc.dimensions.keys())
    if 'sps25' in dim_names:
        df = read_flight_nc_25hz(nc, read_vars)
    else:
        df = read_flight_nc_1hz(nc, read_vars)
    return df

def read_all_flights(data_dir: str, 
                     field_campaigns: list[str], 
                     read_vars: list[str] = vars_to_read) -> dict[str,dict[str,pd.DataFrame]]:
    """
    open_all_flights 

    :param nc: A netcdf object for a flight netcdf file.
    :param read_vars: A list of variable names to be read in the netcdf object. Optional. Default is "vars_to_read" specified
                      above.

    :return: Returns Pandas DataFrame
    """
    all_campaign_nc = {} # a dictionary of dictionaries with keys of field campaigns
    for campaign in field_campaigns:
        print(campaign)
        flight_dict = {} # a dictionary of Pandas DataFrames with keys of file names
        campaign_dir = data_dir + "/" + campaign + "/lrt"
        flight_fnames = find_flight_fnames(campaign_dir)
        for fname in flight_fnames:
            #print(fname)
            flight_nc = open_flight_nc(campaign_dir + "/" + fname)
            flight_dict[fname] = read_flight_nc(flight_nc, read_vars)
        all_campaign_nc[campaign] = flight_dict
    return all_campaign_nc


class flight_obj:
    """
    flight_obj's are classes that hold flight data (i.e. variables indicated by read_vars) from a provided file path string.
    The __init__ takes a file path string and a list of vars to read (vars_to_read by default).
    The __init__ assigns:
    self.file_path: str; the file path passed in
    self.read_vars_attempted: list[str]; the originally passed in list of vars to read
    self.nc: netCDF4._netCDF4.Dataset; the opened netcdf object
    self.df: pd.DataFrame; a dataframe holding the read in data
    self.rate: str; a string indicating the rate of the data read in
    self.read_vars: list[str]; list of the vars that were successfully read in
    """
    def __init__(self, file_path: str, read_vars: list[str] = vars_to_read):
        # assign input vars
        self.file_path = path.Path(file_path)
        self.read_vars_attempted = read_vars

        # open netcdf file if the file exists, assign to self.nc
        if self.file_path.is_file():
            self.nc = netCDF4.Dataset(self.file_path)
        else:
            raise FileNotFoundError(f"File {self.file_path} did not exist!")

        # read in the variables, assign DataFrame to self.df,
        #                               rate to self.rate,
        #                               vars read in to self.read_vars
        dim_names = list(self.nc.dimensions.keys())
        if 'sps25' in dim_names:
            self.df = read_flight_nc_25hz(self.nc, self.read_vars_attempted)
            self.rate = "25Hz"
        else:
            self.df = read_flight_nc_1hz(self.nc, self.read_vars_attempted)
            self.rate = "1Hz"
        self.read_vars = list(self.df.keys())

