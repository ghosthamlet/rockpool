import json

import numpy as np
from ...timeseries import TSContinuous, TSEvent
from ..layer import Layer
from typing import Optional, Union, Tuple, List
from AuditoryProcessing.preprocessing import *

class Filter(Layer):
    """ Filter - Class: define a filtering layer with continuous time series output
    """
## - Constructor
    def __init__(
        self,
        mfW: np.ndarray,
        filterName: str,
        fs: float,
        tDt: float = None ,
        strName: str = "unnamed",
        downSampleFs: float = None,
        nfft: int = 512,
        winLen: float = 0.025,
        winStep: float = 0.01
    ):
        """
        FFIAFBrian - Construct a spiking feedforward layer with IAF neurons, with a Brian2 back-end
                     Inputs are continuous currents; outputs are spiking events

        :param mfW:             np.array MxN weight matrix.
        :param filterName:      str with the filtering method
        :param fs:              float sampling frequency of input signal
        traceback.print_exc()
        :param vfBias:          np.array Nx1 bias vector
        :param tDt:             float Time-step. Default: 0.1 ms
        :param fNoiseStd:       float Noise std. dev. per second. Default: 0
        :param strName:         str Name for the layer. Default: 'unnamed'
        :param downSampleFs:    float frequency to downsample the output of the filters. Default: 'unnamed'
        :param winLen:          float length of analysis window in seconds. Default: 0.025
        :param winStep:         float step between successive windows in seconds. Default: 0.01
        """

        # - Call super constructor (`asarray` is used to strip units)
        super().__init__(
            mfW=np.asarray(mfW),
            tDt=np.asarray(tDt),
            strName=strName,
        )

        self.fs = fs
        self.nNumTraces = mfW.shape[1]
        self.filterName = filterName
        self.filtFunct = function_Filterbank(self.filterName)
        self.mfW = mfW
        self._nTimeStep = 0
        self.winLen = winLen
        self.winStep = winStep
        if downSampleFs != None:
            self.downSampleFs = downSampleFs
        else:
            self.downSampleFs = fs
        if tDt == None:
            self.tDt = 1/fs
        else:
            self.tDt = tDt
        self.nfft = nfft


    def reset_all(self):
        self.mfW = np.copy(self.mfW)
        self._nTimeStep = 0

    def evolve(
        self,
        tsInput: Optional[TSContinuous] = None,
        tDuration: Optional[float] = None,
        nNumTimeSteps: Optional[int] = None,
        bVerbose: bool = False
    ) ->TSContinuous:

        # - Prepare time base
        vtTimeBase, mfInputStep, nNumTimeSteps = self._prepare_input(
            tsInput, tDuration, nNumTimeSteps
        )

        if "sos" in self.filterName or "butter" in self.filterName:
            filtOutput = self.filtFunct(mfInputStep.T[0], self.fs, self.nNumTraces, downSampleFs=self.downSampleFs)
            self._nTimeStep += mfInputStep.shape[0] - 1

            return TSContinuous(
                vtTimeBase,
                filtOutput,
                name="filteredInput",
            )

        elif "mfcc" in self.filterName or "fft" in self.filterName:
            filtOutput = self.filtFunct(mfInputStep.T[0], self.fs, self.nNumTraces, \
                                        winlen=self.winLen, winstep=self.winStep, nfft=self.nfft)

            self._nTimeStep += mfInputStep.shape[0] - 1
            vtTimeBase = np.arange(len(filtOutput)) * self.winLen
            if tDuration == None:
                vtTimeBase = np.linspace(tsInput.t_start, tsInput.t_stop, len(filtOutput))

            return TSContinuous(
                vtTimeBase,
                filtOutput,
                name="filteredInput",
            )

    def to_dict(self):

        config = {}
        config["mfW"] = self.mfW.tolist()
        config["filterName"] = self.filterName
        config["fs"] = self.fs
        config["tDt"] = self.tDt if type(self.tDt) is float else self.tDt.tolist()
        config["strName"] = self.strName
        config["ClassName"] = "Filter"

        return config

    @staticmethod
    def load_from_dict(config):

        return Filter(
            mfW = np.array(config["mfW"]),
            tDt = config['tDt'],
            filterName=config["filterName"],
            fs = config["fs"],
            strName = config['strName'],
        )

    @staticmethod
    def load_from_file(filename):
        with open(filename, "r") as f:
            config = json.load(f)

        return Filter(
            mfW = np.array(config["mfW"]),
            tDt = config['tDt'],
            filterName=config["filterName"],
            fs = config["fs"],
            strName = config['strName'],
        )