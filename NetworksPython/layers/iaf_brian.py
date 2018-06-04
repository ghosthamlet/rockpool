###
# iaf_brian.py - Class implementing an IAF simple feed-forward layer in Brian
###


# - Imports
import brian2 as b2
import brian2.numpy_ as np
from brian2.units.stdunits import *
from brian2.units.allunits import *

from TimeSeries import TimeSeries

from .layer import Layer

from .recurrent.timedarray_shift import TimedArray as TAShift

# - Configure exports
__all__ = ['FFIAFBrian', 'eqNeuronIAF', 'eqSynapseExp']

# - Equations for an integrate-and-fire neuron
eqNeuronIAF = b2.Equations('''
    dv/dt = (v_rest - v + r_m * I_total) / tau_m    : volt (unless refractory)  # Neuron membrane voltage
    I_total = I_inp(t, i) + I_bias                  : amp                       # Total input current
    I_bias                                          : amp                       # Per-neuron bias current
    v_rest                                          : volt                      # Rest potential
    tau_m                                           : second                    # Membrane time constant
    r_m                                             : ohm                       # Membrane resistance
    v_thresh                                        : volt                      # Firing threshold potential
    v_reset                                         : volt                      # Reset potential
''')

# - Equations for an exponential synapse
eqSynapseExp = b2.Equations('''
    dI_syn/dt = -I_syn / tau_s                      : amp                       # Synaptic current
    tau_s                                           : second                    # Synapse time constant
''')


## - FFIAFBrian - Class: define a spiking recurrent layer with exponential current synaptic outputs
class FFIAFBrian(Layer):
    """ FFIAFBrian - Class: define a spiking recurrent layer with exponential current synaptic outputs
    """

    ## - Constructor
    def __init__(self,
                 mfW: np.ndarray = None,
                 vfBias: np.ndarray = 10*mA,

                 tDt: float = 0.1*ms,
                 fNoiseStd: float = 1*mV,

                 vtTauN: np.ndarray = 20*ms,
                 tTauSynO: float = 5 * ms,

                 vfVThresh: np.ndarray = -55*mV,
                 vfVReset: np.ndarray = -65*mV,
                 vfVRest: np.ndarray = -65*mV,

                 tRefractoryTime = 0*ms,

                 eqNeurons = eqNeuronIAF,
                 eqSynapses = eqSynapseExp,

                 strIntegrator: str = 'rk4',

                 strName: str = 'unnamed'
                 ):
        """
        RecIAFBrian - Construct a spiking recurrent layer with IAF neurons, with a Brian2 back-end

        :param mfW:             np.array NxN weight matrix. Default: [100x100] unit-lambda matrix
        :param vfBias:          np.array Nx1 bias vector. Default: 10.5mA

        :param vtTauN:          np.array Nx1 vector of neuron time constants. Default: 5ms
        :param tTauSynO:        float Output synaptic time constants. Default: 5ms

        :param vfVThresh:       np.array Nx1 vector of neuron thresholds. Default: -55mV
        :param vfVReset:        np.array Nx1 vector of neuron thresholds. Default: -65mV
        :param vfVRest:         np.array Nx1 vector of neuron thresholds. Default: -65mV

        :param tRefractoryTime: float Refractory period after each spike. Default: 0ms

        :param eqNeurons:       Brian2.Equations set of neuron equations. Default: IAF equation set
        :param eqSynapses:      Brian2.Equations set of synapse equations for receiver. Default: exponential

        :param strIntegrator:   str Integrator to use for simulation. Default: 'exact'

        :param strName:         str Name for the layer. Default: 'unnamed'
        """

        # - Call super constructor
        super().__init__(mfW = mfW,
                         tDt = np.asarray(tDt),
                         fNoiseStd = np.asarray(fNoiseStd),
                         strName = strName)

        # - Set up layer neurons
        self._ngLayer = b2.NeuronGroup(self.nSize, eqNeurons,
                                       threshold = 'v > v_thresh',
                                       reset = 'v = v_reset',
                                       refractory = tRefractoryTime,
                                       method = strIntegrator,
                                       dt = tDt,
                                       name = 'reservoir_neurons')
        self._ngLayer.v = vfVRest
        self._ngLayer.r_m = 1 * ohm

        # - Set up layer receiver nodes
        self._ngReceiver = b2.NeuronGroup(self.nSize, eqSynapses,
                                          refractory = False,
                                          method = strIntegrator,
                                          dt = tDt,
                                          name = 'receiver_neurons')

        # - Add layer -> receiver synapses
        self._sgReceiver = b2.Synapses(self._ngLayer, self._ngReceiver,
                                       on_pre = 'I_syn_post += 1*amp',
                                       method = strIntegrator,
                                       dt = tDt,
                                       name = 'receiver_synapses')
        self._sgReceiver.connect('i == j')

        # - Add current monitors to record reservoir outputs
        self._stmLayer = b2.StateMonitor(self._ngLayer, 'v', True, name = 'layer_membrane_voltage')
        self._stmReceiver = b2.StateMonitor(self._ngReceiver, 'I_syn', True, name = 'receiver_synaptic_currents')
        self._spmLayer = b2.SpikeMonitor(self._ngLayer, record = True, name = 'layer_spikes')

        # - Call Network constructor
        self._net = b2.Network(self._ngLayer, self._ngReceiver, self._sgReceiver,
                               self._stmLayer, self._stmReceiver, self._spmLayer,
                               name = 'ff_spiking_layer')

        # - Record reservoir parameters
        self.vfVThresh = vfVThresh
        self.vfVReset = vfVReset
        self.vfVRest = vfVRest
        self.vtTauN = vtTauN
        self.tRefractoryTime = tRefractoryTime
        self.tTauSynO = tTauSynO
        self.vfBias = vfBias

        # - Store "reset" state
        self._net.store('reset')


    def reset_state(self):
        """ .reset_state() - Method: reset the internal state of the layer
            Usage: .reset_state()
        """
        self._ngLayer.v = self.vfVRest
        self._ngLayer.I_syn = 0
        self._ngReceiver.I_syn = 0

    def randomize_state(self):
        """ .randomize_state() - Method: randomize the internal state of the layer
            Usage: .randomize_state()
        """
        fRangeV = abs(self.vfVThresh - self.vfVReset)
        self._ngLayer.v = (np.random.rand(self.nSize) * fRangeV + self.vfVReset) * volt
        self._ngLayer.I_syn = np.random.rand(self.nSize) * amp
        self._ngReceiver.I_syn = 0 * amp

    def reset_time(self):
        """
        reset_time - Reset the internal clock of this layer
        """
        self._net.restore('reset')


    ### --- State evolution

    def evolve(self,
               tsInput: TimeSeries = None,
               tDuration: float = None):
        """
        evolve - Evolve the state of this layer

        :param tsInput:     TimeSeries TxM or Tx1 input to this layer
        :param tDuration:   float Duration of evolution, in seconds

        :return: TimeSeries Output of this layer during evolution period
        """

        # - Discretise input, prepare time base
        vtTimeBase, mfInputStep, tDuration = self._prepare_input(tsInput, tDuration)

        # - Weight inputs
        mfNeuronInputStep = mfInputStep @ self.mfW

        # - Generate a noise trace
        mfNoiseStep = np.random.randn(np.size(vtTimeBase), self.nSize) * self.fNoiseStd

        # - Specifiy network input currents, construct TimedArray
        taI_inp = TAShift(np.asarray(mfNeuronInputStep + mfNoiseStep) * amp,
                          self.tDt * second, tOffset = self.t * second,
                          name  = 'external_input')

        # - Perform simulation
        self._net.run(tDuration * second, namespace = {'I_inp': taI_inp}, level = 0)

        # - Build response TimeSeries
        vtTimeBaseOutput = self._stmReceiver.t_
        vbUseTime = self._stmReceiver.t_ >= vtTimeBase[0]
        vtTimeBaseOutput = vtTimeBaseOutput[vbUseTime]
        mfA = self._stmReceiver.I_syn_.T
        mfA = mfA[vbUseTime, :]

        return TimeSeries(vtTimeBaseOutput, mfA, strName = 'Receiver current')


    ### --- Properties

    @property
    def vState(self):
        return self._ngLayer.v_

    @vState.setter
    def vState(self, vNewState):
        self._ngLayer.v = np.asarray(self._expand_to_net_size(vNewState, 'vNewState')) * volt

    @property
    def vtTauN(self):
        return self._ngLayer.tau_m_

    @vtTauN.setter
    def vtTauN(self, vtNewTauN):
        self._ngLayer.tau_m = np.asarray(self._expand_to_net_size(vtNewTauN, 'vtNewTauN')) * second

    @property
    def tTauSynO(self):
        return self._ngReceiver.tau_s_[0]

    @tTauSynO.setter
    def tTauSynO(self, tNewTauO):
        self._ngReceiver.tau_s = np.asarray(tNewTauO) * second

    @property
    def vfBias(self):
        return self._ngLayer.I_bias_

    @vfBias.setter
    def vfBias(self, vfNewBias):
        self._ngLayer.I_bias = np.asarray(self._expand_to_net_size(vfNewBias, 'vfNewBias')) * amp

    @property
    def vfVThresh(self):
        return self._ngLayer.v_thresh_

    @vfVThresh.setter
    def vfVThresh(self, vfNewVThresh):
        self._ngLayer.v_thresh = np.asarray(self._expand_to_net_size(vfNewVThresh, 'vfNewVThresh')) * volt

    @property
    def vfVRest(self):
        return self._ngLayer.v_rest_

    @vfVRest.setter
    def vfVRest(self, vfNewVRest):
        self._ngLayer.v_rest = np.asarray(self._expand_to_net_size(vfNewVRest, 'vfNewVRest')) * volt

    @property
    def vfVReset(self):
        return self._ngLayer.v_reset_

    @vfVReset.setter
    def vfVReset(self, vfNewVReset):
        self._ngLayer.v_reset = np.asarray(self._expand_to_net_size(vfNewVReset, 'vfNewVReset')) * volt

    @property
    def t(self):
        return self._net.t_

    @Layer.tDt.setter
    def tDt(self, _):
        raise ValueError('The `tDt` property cannot be set for this layer')