import json

import numpy as np
from ...timeseries import TSContinuous, TSEvent
import multiprocessing
import importlib

from ..layer import Layer


from typing import Optional, Union
import time

if importlib.util.find_spec("nest") is None:
    raise ModuleNotFoundError("No module named 'nest'.")


def s2ms(t):
    return t * 1000.0


def ms2s(t):
    return t / 1000.0


def V2mV(v):
    return v * 1000.0


def mV2V(v):
    return v / 1000.0


COMMAND_GET = 0
COMMAND_SET = 1
COMMAND_RESET = 2
COMMAND_EVOLVE = 3


# - FFIAFNest- Class: define a spiking feedforward layer with spiking outputs
class FFIAFNest(Layer):
    """ FFIAFNest - Class: define a spiking feedforward layer with spiking outputs
    """

    class NestProcess(multiprocessing.Process):
        """ Class for running NEST in its own process """

        def __init__(
            self,
            requestQ,
            resultQ,
            mfW: np.ndarray,
            vfBias: Union[float, np.ndarray],
            tDt: float,
            vtTauN: Union[float, np.ndarray],
            vfCapacity: Union[float, np.ndarray],
            vfVThresh: Union[float, np.ndarray],
            vfVReset: Union[float, np.ndarray],
            vfVRest: Union[float, np.ndarray],
            tRefractoryTime,
            bRecord: bool = False,
            numCores: int = 1,
        ):
            """ initialize the process"""

            multiprocessing.Process.__init__(self, daemon=True)

            self.requestQ = requestQ
            self.resultQ = resultQ

            # - Record neuron parameters
            self.tDt = s2ms(tDt)
            self.vfVThresh = V2mV(vfVThresh)
            self.vfVReset = V2mV(vfVReset)
            self.vfVRest = V2mV(vfVRest)
            self.vtTauN = s2ms(vtTauN)
            self.vfBias = V2mV(vfBias)
            self.vfCapacity = vfCapacity
            self.mfW = V2mV(mfW)
            self.tRefractoryTime = s2ms(tRefractoryTime)
            self.bRecord = bRecord
            self.nSize = np.shape(mfW)[1]
            self.numCores = numCores

        def run(self):
            """ start the process. Initializes the network, defines IPC commands and waits for commands. """

            #### INITIALIZE NEST ####
            import nest

            numCPUs = multiprocessing.cpu_count()
            # if self.numCores >= numCPUs:
            #    self.numCores = numCPUs

            nest.ResetKernel()
            nest.hl_api.set_verbosity("M_FATAL")
            nest.SetKernelStatus(
                {
                    "resolution": self.tDt,
                    "local_num_threads": self.numCores,
                    "print_time": True,
                }
            )

            self._pop = nest.Create("iaf_psc_exp", self.nSize)

            params = []
            for n in range(self.nSize):
                p = {}

                if type(self.vtTauN) is np.ndarray:
                    p["tau_m"] = self.vtTauN[n]
                else:
                    p["tau_m"] = self.vtTauN

                if type(self.vfVThresh) is np.ndarray:
                    p["V_th"] = self.vfVThresh[n]
                else:
                    p["V_th"] = self.vfVThresh

                if type(self.vfVReset) is np.ndarray:
                    p["V_reset"] = self.vfVReset[n]
                else:
                    p["V_reset"] = self.vfVReset

                if type(self.vfVReset) is np.ndarray:
                    p["E_L"] = self.vfVRest[n]
                    p["V_m"] = self.vfVRest[n]
                else:
                    p["E_L"] = self.vfVRest
                    p["V_m"] = self.vfVRest

                if type(self.tRefractoryTime) is np.ndarray:
                    p["t_ref"] = self.tRefractoryTime[n]
                else:
                    p["t_ref"] = self.tRefractoryTime

                if type(self.vfBias) is np.ndarray:
                    p["I_e"] = self.vfBias[n]
                else:
                    p["I_e"] = self.vfBias

                if type(self.vfCapacity) is np.ndarray:
                    p["C_m"] = self.vfCapacity[n]
                else:
                    p["C_m"] = self.vfCapacity

                params.append(p)

            nest.SetStatus(self._pop, params)

            # - Add spike detector to record layer outputs
            self._sd = nest.Create("spike_detector")
            nest.Connect(self._pop, self._sd)

            # - Add stimulation device
            self._scg = nest.Create("step_current_generator", self.mfW.shape[0])
            nest.Connect(self._scg, self._pop, "all_to_all", {"weight": self.mfW.T})

            if self.bRecord:
                # - Monitor for recording network potential
                self._mm = nest.Create(
                    "multimeter", 1, {"record_from": ["V_m"], "interval": 1.0}
                )
                nest.Connect(self._mm, self._pop)

            ######### DEFINE IPC COMMANDS ######

            def getParam(name):
                """ IPC command for getting a parameter """
                vms = nest.GetStatus(self._pop, name)
                return vms

            def setParam(name, value):
                """ IPC command for setting a parameter """
                params = []

                for n in range(self.nSize):
                    p = {}
                    if type(value) is np.ndarray:
                        p[name] = value[n]
                    else:
                        p[name] = value

                    params.append(p)

                nest.SetStatus(self._pop, params)

            def reset():
                """
                reset_all - IPC command which resets time and state
                """

                nest.ResetNetwork()
                nest.SetKernelStatus({"time": 0.0})

            def evolve(vtTimeBase, mfInputStep, nNumTimeSteps: Optional[int] = None):
                """ IPC command running the network for nNumTimeSteps with mfInputStep as input """

                # NEST time starts with 1 (not with 0)

                vtTimeBase = s2ms(vtTimeBase) + 1

                nest.SetStatus(
                    self._scg,
                    [
                        {
                            "amplitude_times": vtTimeBase,
                            "amplitude_values": V2mV(mfInputStep[:, i]),
                        }
                        for i in range(len(self._scg))
                    ],
                )

                startTime = nest.GetKernelStatus("time")

                if startTime == 0:
                    # weird behavior of NEST; the recording stops a timestep before the simulation stops. Therefore
                    # the recording has one entry less in the first batch
                    nest.Simulate(nNumTimeSteps * self.tDt + 1.0)
                else:
                    nest.Simulate(nNumTimeSteps * self.tDt)

                # - record states
                if self.bRecord:
                    events = nest.GetStatus(self._mm, "events")[0]
                    vbUseEvent = events["times"] >= startTime

                    senders = events["senders"][vbUseEvent]
                    times = events["times"][vbUseEvent]
                    vms = events["V_m"][vbUseEvent]

                    mfRecordStates = []
                    u_senders = np.unique(senders)
                    for i, nid in enumerate(u_senders):
                        ind = np.where(senders == nid)[0]
                        _times = times[ind]

                        order = np.argsort(_times)
                        _vms = vms[ind][order]
                        mfRecordStates.append(_vms)

                    mfRecordStates = np.array(mfRecordStates)

                # - Build response TimeSeries
                events = nest.GetStatus(self._sd, "events")[0]
                vbUseEvent = events["times"] >= startTime
                vtEventTimeOutput = ms2s(events["times"][vbUseEvent])
                vnEventChannelOutput = events["senders"][vbUseEvent]

                # sort spiking response
                order = np.argsort(vtEventTimeOutput)
                vtEventTimeOutput = vtEventTimeOutput[order]
                vnEventChannelOutput = vnEventChannelOutput[order]

                # transform from NEST id to index
                vnEventChannelOutput -= np.min(self._pop)

                if self.bRecord:
                    return [
                        vtEventTimeOutput,
                        vnEventChannelOutput,
                        mV2V(mfRecordStates),
                    ]
                else:
                    return [vtEventTimeOutput, vnEventChannelOutput, None]

            IPC_switcher = {
                COMMAND_GET: getParam,
                COMMAND_SET: setParam,
                COMMAND_RESET: reset,
                COMMAND_EVOLVE: evolve,
            }

            # wait for an IPC command

            while True:
                req = self.requestQ.get()

                func = IPC_switcher.get(req[0])

                result = func(*req[1:])

                if not result is None:
                    self.resultQ.put(result)

    ## - Constructor
    def __init__(
        self,
        mfW: np.ndarray,
        vfBias: Union[float, np.ndarray] = 0.0,
        tDt: float = 0.0001,
        vtTauN: Union[float, np.ndarray] = 0.02,
        vfCapacity: Union[float, np.ndarray] = 100.0,
        vfVThresh: Union[float, np.ndarray] = -0.055,
        vfVReset: Union[float, np.ndarray] = -0.065,
        vfVRest: Union[float, np.ndarray] = -0.065,
        tRefractoryTime=0.001,
        strName: str = "unnamed",
        bRecord: bool = False,
        nNumCores=1,
    ):
        """
        FFIAFNest - Construct a spiking feedforward layer with IAF neurons, with a NEST back-end
                     Inputs are continuous currents; outputs are spiking events

        :param mfW:             np.array MxN weight matrix.
        :param vfBias:          np.array Nx1 bias vector. Default: 10mA

        :param tDt:             float Time-step. Default: 0.1 ms

        :param vtTauN:          np.array Nx1 vector of neuron time constants. Default: 20ms

        :param vfCapacity:       np.array Nx1 vector of neuron membrance capacity. Default: 100 pF

        :param vfVThresh:       np.array Nx1 vector of neuron thresholds. Default: -55mV
        :param vfVReset:        np.array Nx1 vector of neuron reset potential. Default: -65mV
        :param vfVRest:         np.array Nx1 vector of neuron resting potential. Default: -65mV

        :param tRefractoryTime: float Refractory period after each spike. Default: 0ms

        :param strName:         str Name for the layer. Default: 'unnamed'

        :param bRecord:         bool Record membrane potential during evolutions
        """

        if type(mfW) is list:
            mfW = np.asarray(mfW)

        if type(vfBias) is list:
            vfBias = np.asarray(vfBias)

        if type(vtTauN) is list:
            vtTauN = np.asarray(vtTauN)

        if type(vfCapacity) is list:
            vfCapacity = np.asarray(vfCapacity)

        if type(vfVThresh) is list:
            vfVThresh = np.asarray(vfVThresh)

        if type(vfVReset) is list:
            vfVReset = np.asarray(vfVReset)

        if type(vfVRest) is list:
            vfVRest = np.asarray(vfVRest)

        # - Call super constructor (`asarray` is used to strip units)
        super().__init__(mfW=np.asarray(mfW), tDt=np.asarray(tDt), strName=strName)

        self.nNumCores = nNumCores

        self.requestQ = multiprocessing.Queue()
        self.resultQ = multiprocessing.Queue()

        self.nestProcess = self.NestProcess(
            self.requestQ,
            self.resultQ,
            mfW,
            vfBias,
            tDt,
            vtTauN,
            vfCapacity,
            vfVThresh,
            vfVReset,
            vfVRest,
            tRefractoryTime,
            bRecord,
            nNumCores,
        )

        self.nestProcess.start()

        # - Record neuron parameters
        self._vfVThresh = vfVThresh
        self._vfVReset = vfVReset
        self._vfVRest = vfVRest
        self._vtTauN = vtTauN
        self._vfBias = vfBias
        self._vfCapacity = vfCapacity
        self.mfW = mfW
        self._tRefractoryTime = tRefractoryTime
        self.bRecord = bRecord

    def reset_state(self):
        """ .reset_state() - Method: reset the internal state of the layer
            Usage: .reset_state()
        """

        self.requestQ.put([COMMAND_SET, "V_m", V2mV(self._vfVRest)])

    def randomize_state(self):
        """ .randomize_state() - Method: randomize the internal state of the layer
            Usage: .randomize_state()
        """
        fRangeV = abs(self._vfVThresh - self._vfVReset)
        randV = np.random.rand(self._nSize) * fRangeV + self._vfVReset

        self.requestQ.put([COMMAND_SET, "V_m", V2mV(randV)])

    def reset_time(self):
        """
        reset_time - Reset the internal clock of this layer
        """

        print("WARNING: This function resets the whole network")

        self.requestQ.put([COMMAND_RESET])
        self._nTimeStep = 0

    def reset_all(self):
        """
        reset_all - resets time and state
        """

        self.requestQ.put([COMMAND_RESET])
        self._nTimeStep = 0

    # --- State evolution

    def evolve(
        self,
        tsInput: Optional[TSContinuous] = None,
        tDuration: Optional[float] = None,
        nNumTimeSteps: Optional[int] = None,
        bVerbose: bool = False,
    ) -> TSEvent:
        """
        evolve : Function to evolve the states of this layer given an input

        :param tsSpkInput:      TSContinuous  Input spike trian
        :param tDuration:       float    Simulation/Evolution time
        :param nNumTimeSteps    int      Number of evolution time steps
        :param bVerbose:        bool     Currently no effect, just for conformity
        :return:                TSEvent  output spike series

        """
        # - Prepare time base
        vtTimeBase, mfInputStep, nNumTimeSteps = self._prepare_input(
            tsInput, tDuration, nNumTimeSteps
        )

        self.requestQ.put([COMMAND_EVOLVE, vtTimeBase, mfInputStep, nNumTimeSteps])

        if self.bRecord:
            vtEventTimeOutput, vnEventChannelOutput, self.mfRecordStates = (
                self.resultQ.get()
            )
        else:
            vtEventTimeOutput, vnEventChannelOutput, _ = self.resultQ.get()

        # - Start and stop times for output time series
        tStart = self._nTimeStep * np.asscalar(self.tDt)
        tStop = (self._nTimeStep + nNumTimeSteps) * np.asscalar(self.tDt)

        # - Update layer time step
        self._nTimeStep += nNumTimeSteps

        return TSEvent(
            np.clip(vtEventTimeOutput, tStart, tStop),
            vnEventChannelOutput,
            name="Layer spikes",
            num_channels=self.nSize,
            t_start=tStart,
            t_stop=tStop,
        )

    def terminate(self):
        self.requestQ.close()
        self.resultQ.close()
        self.requestQ.cancel_join_thread()
        self.resultQ.cancel_join_thread()
        self.nestProcess.terminate()
        self.nestProcess.join()

    ### --- Properties

    @property
    def cOutput(self):
        return TSEvent

    @property
    def tRefractoryTime(self):
        return self._tRefractoryTime

    @property
    def vState(self):
        self.requestQ.put([COMMAND_GET, "V_m"])
        vms = np.array(self.resultQ.get())
        return mV2V(vms)

    @vState.setter
    def vState(self, vNewState):

        self.requestQ.put([COMMAND_SET, "V_m", V2mV(vNewState)])

    @property
    def vtTauN(self):
        return self._vtTauN

    @vtTauN.setter
    def vtTauN(self, vtNewTauN):

        self.requestQ.put([COMMAND_SET, "tau_m", s2ms(vtNewTauN)])

    @property
    def vfBias(self):
        return self._vfBias

    @vfBias.setter
    def vfBias(self, vfNewBias):

        self.requestQ.put([COMMAND_SET, "I_e", V2mV(vfNewBias)])

    @property
    def vfVThresh(self):
        return self._vfVThresh

    @vfVThresh.setter
    def vfVThresh(self, vfNewVThresh):

        self.requestQ.put([COMMAND_SET, "V_th", V2mV(vfNewVThresh)])

    @property
    def vfVReset(self):
        return self._vfVReset

    @vfVReset.setter
    def vfVReset(self, vfNewVReset):

        self.requestQ.put([COMMAND_SET, "V_reset", V2mV(vfNewVReset)])

    @property
    def vfVRest(self):
        return self._vfVReset

    @vfVReset.setter
    def vfVRest(self, vfNewVRest):

        self.requestQ.put([COMMAND_SET, "E_L", V2mV(vfNewVRest)])

    @property
    def t(self):
        return self._nTimeStep * np.asscalar(self.tDt)

    @Layer.tDt.setter
    def tDt(self, _):
        raise ValueError("The `tDt` property cannot be set for this layer")

    def to_dict(self):

        config = {}
        config["strName"] = self.strName
        config["mfWIn"] = self.mfW.tolist()
        config["tDt"] = self.tDt if type(self.tDt) is float else self.tDt.tolist()
        config["vfVThresh"] = (
            self.vfVThresh if type(self.vfVThresh) is float else self.vfVThresh.tolist()
        )
        config["vfVReset"] = (
            self.vfVReset if type(self.vfVReset) is float else self.vfVReset.tolist()
        )
        config["vfVRest"] = (
            self.vfVRest if type(self.vfVRest) is float else self.vfVRest.tolist()
        )
        config["vfCapacity"] = (
            self._vfCapacity
            if type(self._vfCapacity) is float
            else self._vfCapacity.tolist()
        )
        config["tRef"] = (
            self.tRefractoryTime
            if type(self.tRefractoryTime) is float
            else self.tRefractoryTime.tolist()
        )
        config["tauN"] = (
            self.vtTauN if type(self.vtTauN) is float else self.vtTauN.tolist()
        )
        config["nNumCores"] = self.nNumCores
        config["bRecord"] = self.bRecord
        config["bias"] = (
            self.vfBias if type(self.vfBias) is float else self.vfBias.tolist()
        )
        config["ClassName"] = "FFIAFNest"

        return config

    def save(self, config, filename):
        with open(filename, "w") as f:
            json.dump(config, f)

    @staticmethod
    def load_from_dict(config):

        return FFIAFNest(
            mfW=config["mfWIn"],
            vfBias=config["bias"],
            tDt=config["tDt"],
            vtTauN=config["tauN"],
            vfCapacity=config["vfCapacity"],
            vfVThresh=config["vfVThresh"],
            vfVReset=config["vfVReset"],
            vfVRest=config["vfVRest"],
            tRefractoryTime=config["tRef"],
            strName=config["strName"],
            bRecord=config["bRecord"],
            nNumCores=config["nNumCores"],
        )

    @staticmethod
    def load_from_file(filename):
        with open(filename, "r") as f:
            config = json.load(f)

        return FFIAFNest(
            mfW=config["mfWIn"],
            vfBias=config["bias"],
            tDt=config["tDt"],
            vtTauN=config["tauN"],
            vfCapacity=config["vfCapacity"],
            vfVThresh=config["vfVThresh"],
            vfVReset=config["vfVReset"],
            vfVRest=config["vfVRest"],
            tRefractoryTime=config["tRef"],
            strName=config["strName"],
            bRecord=config["bRecord"],
            nNumCores=config["nNumCores"],
        )


# - RecIAFSpkInNest- Class: Spiking recurrent layer with spiking in- and outputs
class RecIAFSpkInNest(Layer):
    """ RecIAFSpkInNest- Class: Spiking recurrent layer with spiking in- and outputs
    """

    class NestProcess(multiprocessing.Process):
        """ Class for running NEST in its own process """

        def __init__(
            self,
            requestQ,
            resultQ,
            mfWIn: np.ndarray,
            mfWRec: np.ndarray,
            mfDelayIn: Union[float, np.ndarray],
            mfDelayRec: Union[float, np.ndarray],
            vfBias: Union[float, np.ndarray],
            tDt: float,
            vtTauN: Union[float, np.ndarray],
            vtTauS: Union[float, np.ndarray],
            vfCapacity: Union[float, np.ndarray],
            vfVThresh: Union[float, np.ndarray],
            vfVReset: Union[float, np.ndarray],
            vfVRest: Union[float, np.ndarray],
            tRefractoryTime,
            bRecord: bool = False,
            numCores: int = 1,
        ):
            """ initializes the process """

            multiprocessing.Process.__init__(self, daemon=True)

            self.requestQ = requestQ
            self.resultQ = resultQ

            # - Record neuron parameters
            self.tDt = s2ms(tDt)
            self.vfVThresh = V2mV(vfVThresh)
            self.vfVReset = V2mV(vfVReset)
            self.vfVRest = V2mV(vfVRest)
            self.vtTauN = s2ms(vtTauN)
            self.vtTauS = s2ms(vtTauS)
            self.vfBias = V2mV(vfBias)
            self.vfCapacity = vfCapacity
            self.mfWIn = V2mV(mfWIn)
            self.mfWRec = V2mV(mfWRec)
            self.mfDelayIn = s2ms(mfDelayIn)
            self.mfDelayRec = s2ms(mfDelayRec)
            self.tRefractoryTime = s2ms(tRefractoryTime)
            self.bRecord = bRecord
            self.nSize = np.shape(mfWRec)[0]
            self.numCores = numCores

        def run(self):
            """ start the process. Initializes the network, defines IPC commands and waits for commands. """

            #### INITIALIZE NEST ####
            import nest

            numCPUs = multiprocessing.cpu_count()
            # if self.numCores >= numCPUs:
            #    self.numCores = numCPUs

            nest.ResetKernel()
            nest.hl_api.set_verbosity("M_FATAL")
            nest.SetKernelStatus(
                {
                    "resolution": self.tDt,
                    "local_num_threads": self.numCores,
                    "print_time": True,
                }
            )

            self._pop = nest.Create("iaf_psc_exp", self.nSize)

            params = []
            for n in range(self.nSize):
                p = {}

                if type(self.vtTauS) is np.ndarray:
                    p["tau_syn_ex"] = self.vtTauS[n]
                    p["tau_syn_in"] = self.vtTauS[n]
                else:
                    p["tau_syn_ex"] = self.vtTauS
                    p["tau_syn_in"] = self.vtTauS

                if type(self.vtTauN) is np.ndarray:
                    p["tau_m"] = self.vtTauN[n]
                else:
                    p["tau_m"] = self.vtTauN

                if type(self.vfVThresh) is np.ndarray:
                    p["V_th"] = self.vfVThresh[n]
                else:
                    p["V_th"] = self.vfVThresh

                if type(self.vfVReset) is np.ndarray:
                    p["V_reset"] = self.vfVReset[n]
                else:
                    p["V_reset"] = self.vfVReset

                if type(self.vfVReset) is np.ndarray:
                    p["E_L"] = self.vfVRest[n]
                    p["V_m"] = self.vfVRest[n]
                else:
                    p["E_L"] = self.vfVRest
                    p["V_m"] = self.vfVRest

                if type(self.tRefractoryTime) is np.ndarray:
                    p["t_ref"] = self.tRefractoryTime[n]
                else:
                    p["t_ref"] = self.tRefractoryTime

                if type(self.vfBias) is np.ndarray:
                    p["I_e"] = self.vfBias[n]
                else:
                    p["I_e"] = self.vfBias

                if type(self.vfCapacity) is np.ndarray:
                    p["C_m"] = self.vfCapacity[n]
                else:
                    p["C_m"] = self.vfCapacity

                params.append(p)

            nest.SetStatus(self._pop, params)

            # - Add spike detector to record layer outputs
            self._sd = nest.Create("spike_detector")
            nest.Connect(self._pop, self._sd)

            # - Add stimulation device
            self._sg = nest.Create("spike_generator", self.mfWIn.shape[0])

            # - Create input connections
            pres = []
            posts = []

            for pre, row in enumerate(self.mfWIn):
                for post, w in enumerate(row):
                    if w == 0:
                        continue
                    pres.append(self._sg[pre])
                    posts.append(self._pop[post])

            nest.Connect(pres, posts, "one_to_one")
            conns = nest.GetConnections(self._sg, self._pop)
            connsPrePost = np.array(nest.GetStatus(conns, ["source", "target"]))

            if not len(connsPrePost) == 0:
                connsPrePost[:, 0] -= np.min(self._sg)
                connsPrePost[:, 1] -= np.min(self._pop)

                weights = [self.mfWIn[conn[0], conn[1]] for conn in connsPrePost]
                if type(self.mfDelayIn) is np.ndarray:
                    delays = [self.mfDelayIn[conn[0], conn[1]] for conn in connsPrePost]
                else:
                    delays = np.array([self.mfDelayIn] * len(weights))

                delays = np.clip(delays, self.tDt, np.max(delays))

                nest.SetStatus(
                    conns, [{"weight": w, "delay": d} for w, d in zip(weights, delays)]
                )

            t1 = time.time()
            # - Create recurrent connections
            pres = []
            posts = []

            for pre, row in enumerate(self.mfWRec):
                for post, w in enumerate(row):
                    if w == 0:
                        continue
                    pres.append(self._pop[pre])
                    posts.append(self._pop[post])

            nest.Connect(pres, posts, "one_to_one")

            conns = nest.GetConnections(self._pop, self._pop)
            connsPrePost = nest.GetStatus(conns, ["source", "target"])

            if not len(connsPrePost) == 0:
                connsPrePost -= np.min(self._pop)

                weights = [self.mfWRec[conn[0], conn[1]] for conn in connsPrePost]
                if type(self.mfDelayRec) is np.ndarray:
                    delays = [
                        self.mfDelayRec[conn[0], conn[1]] for conn in connsPrePost
                    ]
                else:
                    delays = np.array([self.mfDelayRec] * len(weights))

                delays = np.clip(delays, self.tDt, np.max(delays))

                nest.SetStatus(
                    conns, [{"weight": w, "delay": d} for w, d in zip(weights, delays)]
                )

            if self.bRecord:
                # - Monitor for recording network potential
                self._mm = nest.Create(
                    "multimeter", 1, {"record_from": ["V_m"], "interval": 1.0}
                )
                nest.Connect(self._mm, self._pop)

            ######### DEFINE IPC COMMANDS ######

            def getParam(name):
                """ IPC command for getting a parameter """
                vms = nest.GetStatus(self._pop, name)
                return vms

            def setParam(name, value):
                """ IPC command for setting a parameter """
                params = []

                for n in range(self.nSize):
                    p = {}
                    if type(value) is np.ndarray:
                        p[name] = value[n]
                    else:
                        p[name] = value

                    params.append(p)

                nest.SetStatus(self._pop, params)

            def reset():
                """
                reset_all - IPC command which resets time and state
                """
                nest.ResetNetwork()
                nest.SetKernelStatus({"time": 0.0})

            def evolve(
                vtEventTimes, vnEventChannels, nNumTimeSteps: Optional[int] = None
            ):
                """ IPC command running the network for nNumTimeSteps with mfInputStep as input """

                if len(vnEventChannels > 0):
                    # convert input index to NEST id
                    vnEventChannels += np.min(self._sg)

                    # NEST time starts with 1 (not with 0)
                    nest.SetStatus(
                        self._sg,
                        [
                            {"spike_times": s2ms(vtEventTimes[vnEventChannels == i])}
                            for i in self._sg
                        ],
                    )

                startTime = nest.GetKernelStatus("time")

                if startTime == 0:
                    # weird behavior of NEST; the recording stops a timestep before the simulation stops. Therefore
                    # the recording has one entry less in the first batch
                    nest.Simulate(nNumTimeSteps * self.tDt + 1.0)
                else:
                    nest.Simulate(nNumTimeSteps * self.tDt)

                # - record states
                if self.bRecord:
                    events = nest.GetStatus(self._mm, "events")[0]
                    vbUseEvent = events["times"] >= startTime

                    senders = events["senders"][vbUseEvent]
                    times = events["times"][vbUseEvent]
                    vms = events["V_m"][vbUseEvent]

                    mfRecordStates = []
                    u_senders = np.unique(senders)
                    for i, nid in enumerate(u_senders):
                        ind = np.where(senders == nid)[0]
                        _times = times[ind]
                        order = np.argsort(_times)
                        _vms = vms[ind][order]
                        mfRecordStates.append(_vms)

                    mfRecordStates = np.array(mfRecordStates)

                # - Build response TimeSeries
                events = nest.GetStatus(self._sd, "events")[0]
                vbUseEvent = events["times"] >= startTime
                vtEventTimeOutput = ms2s(events["times"][vbUseEvent])
                vnEventChannelOutput = events["senders"][vbUseEvent]

                # sort spiking response
                order = np.argsort(vtEventTimeOutput)
                vtEventTimeOutput = vtEventTimeOutput[order]
                vnEventChannelOutput = vnEventChannelOutput[order]

                # transform from NEST id to index
                vnEventChannelOutput -= np.min(self._pop)

                if self.bRecord:
                    return [
                        vtEventTimeOutput,
                        vnEventChannelOutput,
                        mV2V(mfRecordStates),
                    ]
                else:
                    return [vtEventTimeOutput, vnEventChannelOutput, None]

            IPC_switcher = {
                COMMAND_GET: getParam,
                COMMAND_SET: setParam,
                COMMAND_RESET: reset,
                COMMAND_EVOLVE: evolve,
            }

            # wait for an IPC command

            while True:
                req = self.requestQ.get()

                func = IPC_switcher.get(req[0])

                result = func(*req[1:])

                if not result is None:
                    self.resultQ.put(result)

    ## - Constructor
    def __init__(
        self,
        mfWIn: np.ndarray,
        mfWRec: np.ndarray,
        mfDelayIn=0.0001,
        mfDelayRec=0.0001,
        vfBias: np.ndarray = 0.0,
        tDt: float = 0.0001,
        vtTauN: np.ndarray = 0.02,
        vtTauS: np.ndarray = 0.05,
        vfVThresh: np.ndarray = -0.055,
        vfVReset: np.ndarray = -0.065,
        vfVRest: np.ndarray = -0.065,
        vfCapacity: Union[float, np.ndarray] = 100.0,
        tRefractoryTime=0.001,
        strName: str = "unnamed",
        bRecord: bool = False,
        nNumCores: int = 1,
    ):
        """
        RecIAFSpkInNest - Construct a spiking recurrent layer with IAF neurons, with a NEST back-end
                           in- and outputs are spiking events

        :param mfWIn:           np.array MxN input weight matrix.
        :param mfWRec:          np.array NxN recurrent weight matrix.
        :param vfBias:          np.array Nx1 bias vector. Default: 10.5mA

        :param tDt:             float Time-step. Default: 0.1 ms

        :param vtTauN:          np.array Nx1 vector of neuron time constants. Default: 20ms
        :param vtTauS:          np.array Nx1 vector of synapse time constants. Default: 20ms

        :param vfVThresh:       np.array Nx1 vector of neuron thresholds. Default: -55mV
        :param vfVReset:        np.array Nx1 vector of neuron reset potential. Default: -65mV
        :param vfVRest:         np.array Nx1 vector of neuron resting potential. Default: -65mV

        :param vfCapacity:       np.array Nx1 vector of neuron membrance capacity. Default: 100 pF
        :param tRefractoryTime: float Refractory period after each spike. Default: 0ms

        :param strName:         str Name for the layer. Default: 'unnamed'

        :param bRecord:         bool Record membrane potential during evolutions
        """
        if type(mfWIn) is list:
            mfWIn = np.asarray(mfWIn)

        if type(mfWRec) is list:
            mfWRec = np.asarray(mfWRec)

        if type(mfDelayIn) is list:
            mfDelayIn = np.asarray(mfDelayIn)

        if type(mfDelayRec) is list:
            mfDelayRec = np.asarray(mfDelayRec)

        if type(vfBias) is list:
            vfBias = np.asarray(vfBias)

        if type(vtTauN) is list:
            vtTauN = np.asarray(vtTauN)

        if type(vtTauS) is list:
            vtTauS = np.asarray(vtTauS)

        if type(vfCapacity) is list:
            vfCapacity = np.asarray(vfCapacity)

        if type(vfVThresh) is list:
            vfVThresh = np.asarray(vfVThresh)

        if type(vfVReset) is list:
            vfVReset = np.asarray(vfVReset)

        if type(vfVRest) is list:
            vfVRest = np.asarray(vfVRest)

        # - Call super constructor (`asarray` is used to strip units)

        # TODO this does not make much sense (mfW <- mfWIn)
        super().__init__(mfW=np.asarray(mfWIn), tDt=tDt, strName=strName)

        self.nNumCores = nNumCores

        self.requestQ = multiprocessing.Queue()
        self.resultQ = multiprocessing.Queue()

        self.nestProcess = self.NestProcess(
            self.requestQ,
            self.resultQ,
            mfWIn,
            mfWRec,
            mfDelayIn,
            mfDelayRec,
            vfBias,
            tDt,
            vtTauN,
            vtTauS,
            vfCapacity,
            vfVThresh,
            vfVReset,
            vfVRest,
            tRefractoryTime,
            bRecord,
            nNumCores,
        )

        self.nestProcess.start()

        # - Record neuron parameters
        self._vfVThresh = vfVThresh
        self._vfVReset = vfVReset
        self._vfVRest = vfVRest
        self._vtTauN = vtTauN
        self._vtTauS = vtTauS
        self._vfBias = vfBias
        self.vfCapacity = vfCapacity
        self.mfWIn = mfWIn
        self.mfWRec = mfWRec
        self._tRefractoryTime = tRefractoryTime
        self.bRecord = bRecord

    def reset_state(self):
        """ .reset_state() - Method: reset the internal state of the layer
            Usage: .reset_state()
        """

        self.requestQ.put([COMMAND_SET, "V_m", V2mV(self.vfVRest)])

    def randomize_state(self):
        """ .randomize_state() - Method: randomize the internal state of the layer
            Usage: .randomize_state()
        """
        fRangeV = abs(self._vfVThresh - self._vfVReset)
        randV = np.random.rand(self.nSize) * fRangeV + self._vfVReset

        self.requestQ.put([COMMAND_SET, "V_m", V2mV(randV)])

    def reset_time(self):
        """
        reset_time - Reset the internal clock of this layer
        """

        print("WARNING: This function resets the whole network")

        self.requestQ.put([COMMAND_RESET])
        self._nTimeStep = 0

    def reset_all(self):
        """
        reset_all - resets time and state
        """

        self.requestQ.put([COMMAND_RESET])
        self._nTimeStep = 0

    # --- State evolution

    def evolve(
        self,
        tsInput: Optional[TSContinuous] = None,
        tDuration: Optional[float] = None,
        nNumTimeSteps: Optional[int] = None,
        bVerbose: bool = False,
    ) -> TSEvent:
        """
        evolve : Function to evolve the states of this layer given an input

        :param tsSpkInput:      TSContinuous  Input spike trian
        :param tDuration:       float    Simulation/Evolution time
        :param nNumTimeSteps    int      Number of evolution time steps
        :param bVerbose:        bool     Currently no effect, just for conformity
        :return:                TSEvent  output spike series

        """

        # - Prepare time base
        nNumTimeSteps = self._determine_timesteps(tsInput, tDuration, nNumTimeSteps)

        # - Generate discrete time base
        vtTimeBase = self._gen_time_trace(self.t, nNumTimeSteps)

        # - Set spikes for spike generator
        if tsInput is not None:
            vtEventTimes, vnEventChannels = tsInput(
                vtTimeBase[0], vtTimeBase[-1] + self.tDt
            )

        else:
            vtEventTimes = np.array([])
            vnEventChannels = np.array([])

        self.requestQ.put(
            [COMMAND_EVOLVE, vtEventTimes, vnEventChannels, nNumTimeSteps]
        )

        if self.bRecord:
            vtEventTimeOutput, vnEventChannelOutput, self.mfRecordStates = (
                self.resultQ.get()
            )
        else:
            vtEventTimeOutput, vnEventChannelOutput, _ = self.resultQ.get()

        # - Start and stop times for output time series
        tStart = self._nTimeStep * self.tDt
        tStop = (self._nTimeStep + nNumTimeSteps) * self.tDt

        # - Update layer time step
        self._nTimeStep += nNumTimeSteps

        return TSEvent(
            np.clip(vtEventTimeOutput, tStart, tStop),
            vnEventChannelOutput,
            name="Layer spikes",
            num_channels=self.nSize,
            t_start=tStart,
            t_stop=tStop,
        )

    def terminate(self):
        self.requestQ.close()
        self.resultQ.close()
        self.requestQ.cancel_join_thread()
        self.resultQ.cancel_join_thread()
        self.nestProcess.terminate()
        self.nestProcess.join()

    ### --- Properties

    @property
    def cInput(self):
        return TSEvent

    @property
    def cOutput(self):
        return TSEvent

    @property
    def tRefractoryTime(self):
        return self._tRefractoryTime

    @property
    def vState(self):
        self.requestQ.put([COMMAND_GET, "V_m"])
        vms = np.array(self.resultQ.get())
        return mV2V(vms)

    @vState.setter
    def vState(self, vNewState):

        self.requestQ.put([COMMAND_SET, "V_m", V2mV(vNewState)])

    @property
    def vtTauN(self):
        return self._vtTauN

    @vtTauN.setter
    def vtTauN(self, vtNewTauN):

        self.requestQ.put([COMMAND_SET, "tau_m", s2ms(vtNewTauN)])

    @property
    def vtTauS(self):
        return self._vtTauS

    @vtTauS.setter
    def vtTauS(self, vtNewTauS):

        self.requestQ.put([COMMAND_SET, "tau_syn_ex", s2ms(vtNewTauS)])
        self.requestQ.put([COMMAND_SET, "tau_syn_in", s2ms(vtNewTauS)])

    @property
    def vfBias(self):
        return self._vfBias

    @vfBias.setter
    def vfBias(self, vfNewBias):

        self.requestQ.put([COMMAND_SET, "I_e", V2mV(vfNewBias)])

    @property
    def vfVThresh(self):
        return self._vfVThresh

    @vfVThresh.setter
    def vfVThresh(self, vfNewVThresh):

        self.requestQ.put([COMMAND_SET, "V_th", V2mV(vfNewVThresh)])

    @property
    def vfVReset(self):
        return self._vfVReset

    @vfVReset.setter
    def vfVReset(self, vfNewVReset):

        self.requestQ.put([COMMAND_SET, "V_reset", V2mV(vfNewVReset)])

    @property
    def vfVRest(self):
        return self._vfVReset

    @vfVReset.setter
    def vfVRest(self, vfNewVRest):

        self.requestQ.put([COMMAND_SET, "E_L", V2mV(vfNewVRest)])

    @property
    def t(self):
        return self._nTimeStep * self.tDt

    @Layer.tDt.setter
    def tDt(self):
        raise ValueError("The `tDt` property cannot be set for this layer")

    def to_dict(self):

        config = {}
        config["strName"] = self.strName
        config["mfWIn"] = self.mfWIn.tolist()
        config["mfWRec"] = self.mfWRec.tolist()
        config["vfBias"] = (
            self.vfBias if type(self.vfBias) is float else self.vfBias.tolist()
        )
        config["tDt"] = self.tDt if type(self.tDt) is float else self.tDt.tolist()
        config["vfVThresh"] = (
            self.vfVThresh if type(self.vfVThresh) is float else self.vfVThresh.tolist()
        )
        config["vfVReset"] = (
            self.vfVReset if type(self.vfVReset) is float else self.vfVReset.tolist()
        )
        config["vfVRest"] = (
            self.vfVRest if type(self.vfVRest) is float else self.vfVRest.tolist()
        )
        config["vfCapacity"] = (
            self.vfCapacity
            if type(self.vfCapacity) is float
            else self.vfCapacity.tolist()
        )
        config["tRef"] = (
            self.tRefractoryTime
            if type(self.tRefractoryTime) is float
            else self.tRefractoryTime.tolist()
        )
        config["nNumCores"] = self.nNumCores
        config["tauN"] = (
            self.vtTauN if type(self.vtTauN) is float else self.vtTauN.tolist()
        )
        config["tauS"] = (
            self.vtTauS if type(self.vtTauS) is float else self.vtTauS.tolist()
        )
        config["bRecord"] = self.bRecord
        config["ClassName"] = "RecIAFSpkInNest"

        return config

    def save(self, config, filename):
        with open(filename, "w") as f:
            json.dump(config, f)

    @staticmethod
    def load_from_dict(config):

        return RecIAFSpkInNest(
            mfWIn=config["mfWIn"],
            mfWRec=config["mfWRec"],
            vfBias=config["vfBias"],
            tDt=config["tDt"],
            vtTauN=config["tauN"],
            vtTauS=config["tauS"],
            vfCapacity=config["vfCapacity"],
            vfVThresh=config["vfVThresh"],
            vfVReset=config["vfVReset"],
            vfVRest=config["vfVRest"],
            tRefractoryTime=config["tRef"],
            strName=config["strName"],
            bRecord=config["bRecord"],
            nNumCores=config["nNumCores"],
        )

    @staticmethod
    def load_from_file(filename):
        with open(filename, "r") as f:
            config = json.load(f)

        return RecIAFSpkInNest(
            mfWIn=config["mfWIn"],
            mfWRec=config["mfWRec"],
            vfBias=config["vfBias"],
            tDt=config["tDt"],
            vtTauN=config["tauN"],
            vtTauS=config["tauS"],
            vfCapacity=config["vfCapacity"],
            vfVThresh=config["vfVThresh"],
            vfVReset=config["vfVReset"],
            vfVRest=config["vfVRest"],
            tRefractoryTime=config["tRef"],
            strName=config["strName"],
            bRecord=config["bRecord"],
            nNumCores=config["nNumCores"],
        )