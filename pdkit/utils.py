#!/usr/bin/env python3
# Copyright 2018 Birkbeck College. All rights reserved.
#
# Licensed under the MIT license. See file LICENSE for details.
#
# Author(s): J.S. Pons, Cosmin Stamate

import sys
import functools

import pandas as pd
import numpy as np

from scipy.fftpack import rfft, fftfreq
from scipy.signal import butter, lfilter, correlate


def load_cloudupdrs_data(filename, time_difference=1000000000.0):
    '''
       This method loads data in the cloudupdrs format
       
       Usually the data will be saved in a csv file and it should look like this:
       
      .. code-block:: json
      
         timestamp0, x0, y0, z0
         timestamp1, x1, y1, z1
         timestamp0, x2, y2, z2
         .
         .
         .
         timestampn, xn, yn, zn
       
      where x, y, z are the components of the acceleration

      :param str filename: The path to load data from
      :param float time_difference: Convert times. The default is from from nanoseconds to seconds.
    '''
    # data_m = pd.read_table(filename, sep=',', header=None)
    data_m = np.genfromtxt(filename, delimiter=',', invalid_raise=False)
    date_times = pd.to_datetime((data_m[:, 0] - data_m[0, 0]))
    time_difference = (data_m[:, 0] - data_m[0, 0]) / time_difference
    magnitude_sum_acceleration = \
        np.sqrt(data_m[:, 1] ** 2 + data_m[:, 2] ** 2 + data_m[:, 3] ** 2)
    data = {'td': time_difference, 'x': data_m[:, 1], 'y': data_m[:, 2], 'z': data_m[:, 3],
            'mag_sum_acc': magnitude_sum_acceleration}
    data_frame = pd.DataFrame(data, index=date_times, columns=['td', 'x', 'y', 'z', 'mag_sum_acc'])
    return data_frame


def load_mpower_data(filename, time_difference=1000000000.0):
    '''
        This method loads data in the [mpower]_ format \
        
        The format is like: 
       .. code-block:: json
            
            [
               {
                  "timestamp":19298.67999479167,
                  "x": ... ,
                  "y": ...,
                  "z": ...,
               },
               {...},
               {...}
            ]

       :param str filename: The path to load data from
       :param float time_difference: Convert times. The default is from from nanoseconds to seconds.
    '''
    raw_data = pd.read_json(filename)
    date_times = pd.to_datetime(raw_data.timestamp * time_difference - raw_data.timestamp[0] * time_difference)
    time_difference = (raw_data.timestamp - raw_data.timestamp[0])
    time_difference = time_difference.values
    magnitude_sum_acceleration = \
        np.sqrt(raw_data.x.values ** 2 + raw_data.y.values ** 2 + raw_data.z.values ** 2)
    data = {'td': time_difference, 'x': raw_data.x.values, 'y': raw_data.y.values,
            'z': raw_data.z.values, 'mag_sum_acc': magnitude_sum_acceleration}
    data_frame = pd.DataFrame(data, index=date_times, columns=['td', 'x', 'y', 'z', 'mag_sum_acc'])
    return data_frame


def load_data(filename, format_file='cloudupdrs'):
    '''
        This is a general load data method where the format of data to load can be passed as a parameter,

        :param str filename: The path to load data from
        :param str format_file: format of the file. Default is CloudUPDRS. Set to mpower for mpower data.
    '''
    if format_file == 'mpower':
        return load_mpower_data(filename)
    else:
        return load_cloudupdrs_data(filename)


def numerical_integration(signal, sampling_frequency):
    '''
        Numerically integrate a signal with it's sampling frequency.

        :param array signal: A 1-dimensional array or list (the signal).
        :param float sampling_frequency: The sampling frequency for the signal.
    '''
        
    integrate = sum(signal[1:]) / sampling_frequency + sum(signal[:-1])
    integrate /= sampling_frequency * 2
    
    return integrate

def autocorrelation(signal):
    ''' 
        The correlation of a signal with a delayed copy of itself.
        More info here: https://en.wikipedia.org/wiki/Autocorrelation#Estimation

        :param array signal: A 1-dimensional array or list (the signal).
    '''

    signal = np.array(signal)
    n = len(signal)
    variance = signal.var()
    signal -= signal.mean()
    
    r = np.correlate(signal, signal, mode = 'full')[-n:]
    result = r / (variance * (np.arange(n, 0, -1)))
    
    return result


def peakdet(signal, delta, x = None):
    '''
        Find the local maxima and minima ("peaks") in a 1-dimensional signal.
        Converted from MATLAB script at http://billauer.co.il/peakdet.html

        :param array signal: A 1-dimensional array or list (the signal).
        :param float delta: The peak threashold. A point is considered a maximum peak if it has the maximal value, and was preceded (to the left) by a value lower by delta.
        :param array x: indices in local maxima and minima are replaced with the corresponding values in x.
    '''
    
    maxtab = []
    mintab = []

    if x is None:
        x = np.arange(len(signal))

    v = np.asarray(signal)

    if len(v) != len(x):
        sys.exit('Input vectors v and x must have same length')

    if not np.isscalar(delta):
        sys.exit('Input argument delta must be a scalar')

    if delta <= 0:
        sys.exit('Input argument delta must be positive')

    mn, mx = np.inf, -np.inf
    mnpos, mxpos = np.nan, np.nan

    lookformax = True

    for i in np.arange(len(v)):
        this = v[i]
        if this > mx:
            mx = this
            mxpos = x[i]
        if this < mn:
            mn = this
            mnpos = x[i]

        if lookformax:
            if this < mx - delta:
                maxtab.append((mxpos, mx))
                mn = this
                mnpos = x[i]
                lookformax = False
        else:
            if this > mn + delta:
                mintab.append((mnpos, mn))
                mx = this
                mxpos = x[i]
                lookformax = True

    return np.array(maxtab), np.array(mintab)

def compute_interpeak(data, sample_rate):
    """
    Compute number of samples between signal peaks using the real part of FFT.
    Parameters
    ----------
    data : list or numpy array
        time series data
    sample_rate : float
        sample rate of accelerometer reading (Hz)
    Returns
    -------
    interpeak : integer
        number of samples between peaks
    Examples
    --------
    >>> import numpy as np
    >>> from mhealthx.signals import compute_interpeak
    >>> data = np.random.random(10000)
    >>> sample_rate = 100
    >>> interpeak = compute_interpeak(data, sample_rate)
    """

    # Real part of FFT:
    freqs = fftfreq(data.size, d=1.0/sample_rate)
    f_signal = rfft(data)

    # Maximum non-zero frequency:
    imax_freq = np.argsort(f_signal)[-2]
    freq = np.abs(freqs[imax_freq])

    # Inter-peak samples:
    interpeak = np.int(np.round(sample_rate / freq))

    return interpeak

def butter_lowpass_filter(data, sample_rate, cutoff=10, order=4):
    """
    Low-pass filter data by the [order]th order zero lag Butterworth filter
    whose cut frequency is set to [cutoff] Hz.
    After http://stackoverflow.com/questions/25191620/
    creating-lowpass-filter-in-scipy-understanding-methods-and-units
    Parameters
    ----------
    data : numpy array of floats
        time-series data
    sample_rate : integer
        data sample rate
    cutoff : float
        filter cutoff
    order : integer
        order
    Returns
    -------
    y : numpy array of floats
        low-pass-filtered data
    Examples
    --------
    >>> from mhealthx.signals import butter_lowpass_filter
    >>> data = np.random.random(100)
    >>> sample_rate = 10
    >>> cutoff = 5
    >>> order = 4
    >>> y = butter_lowpass_filter(data, sample_rate, cutoff, order)
    """
    

    nyquist = 0.5 * sample_rate
    normal_cutoff = cutoff / nyquist
    b, a = butter(order, normal_cutoff, btype='low', analog=False)

    y = lfilter(b, a, data)

    return y


def crossings_nonzero_pos2neg(data):
    """
    Find indices of zero crossings from positive to negative values.
    From: http://stackoverflow.com/questions/3843017/
                 efficiently-detect-sign-changes-in-python
    Parameters
    ----------
    data : numpy array of floats
    Returns
    -------
    crossings : numpy array of integers
        crossing indices to data
    Examples
    --------
    >>> import numpy as np
    >>> from mhealthx.signals import crossings_nonzero_pos2neg
    >>> data = np.random.random(100)
    >>> crossings = crossings_nonzero_pos2neg(data)
    """
    import numpy as np

    if isinstance(data, np.ndarray):
        pass
    elif isinstance(data, list):
        data = np.asarray(data)
    else:
        raise IOError('data should be a numpy array')

    pos = data > 0

    crossings = (pos[:-1] & ~pos[1:]).nonzero()[0]

    return crossings

def autocorrelate(data, unbias=2, normalize=2):
    """
    Compute the autocorrelation coefficients for time series data.
    Here we use scipy.signal.correlate, but the results are the same as in
    Yang, et al., 2012 for unbias=1:
    "The autocorrelation coefficient refers to the correlation of a time
    series with its own past or future values. iGAIT uses unbiased
    autocorrelation coefficients of acceleration data to scale the regularity
    and symmetry of gait.
    The autocorrelation coefficients are divided by fc(0) in Eq. (6),
    so that the autocorrelation coefficient is equal to 1 when t=0 ::
        NFC(t) = fc(t) / fc(0)
    Here NFC(t) is the normalised autocorrelation coefficient, and fc(t) are
    autocorrelation coefficients."
    Parameters
    ----------
    data : numpy array
        time series data
    unbias : integer or None
        unbiased autocorrelation: divide by range (1) or by weighted range (2)
    normalize : integer or None
        normalize: divide by 1st coefficient (1) or by maximum abs. value (2)
    plot_test : Boolean
        plot?
    Returns
    -------
    coefficients : numpy array
        [normalized, unbiased] autocorrelation coefficients
    N : integer
        number of coefficients
    Examples
    --------
    >>> import numpy as np
    >>> from mhealthx.signals import autocorrelate
    >>> data = np.random.random(100)
    >>> unbias = 2
    >>> normalize = 2
    >>> plot_test = True
    >>> coefficients, N = autocorrelate(data, unbias, normalize, plot_test)
    """

    # Autocorrelation:
    coefficients = correlate(data, data, 'full')
    size = np.int(coefficients.size/2)
    coefficients = coefficients[size:]
    N = coefficients.size

    # Unbiased:
    if unbias:
        if unbias == 1:
            coefficients /= (N - np.arange(N))
        elif unbias == 2:
            coefficient_ratio = coefficients[0]/coefficients[-1]
            coefficients /= np.linspace(coefficient_ratio, 1, N)
        else:
            raise IOError("unbias should be set to 1, 2, or None")

    # Normalize:
    if normalize:
        if normalize == 1:
            coefficients /= np.abs(coefficients[0])
        elif normalize == 2:
            coefficients /= np.max(np.abs(coefficients))
        else:
            raise IOError("normalize should be set to 1, 2, or None")

    return coefficients, N
