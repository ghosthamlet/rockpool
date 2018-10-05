"""
Test torch-based IAF layers
"""


def test_ffiaf_torch():
    # - Test FFIAFTorch
    from NetworksPython.layers import FFIAFTorch
    from NetworksPython.timeseries import TSContinuous
    import numpy as np

    nSizeIn = 384
    nSize = 512

    tDur = 0.01
    tDt = 0.001

    mfW = np.random.randn(nSizeIn,nSize)
    fl = FFIAFTorch(mfW, tDt=tDt, bRecord=False)
    
    mfIn = 0.005 * np.array([
        np.sin(np.linspace(0,10*tDur,int(tDur/tDt)) + fPhase) for fPhase in np.linspace(0,3, nSizeIn)
    ]).T
    vtIn = np.arange(mfIn.shape[0]) * tDt
    tsIn = TSContinuous(vtIn, mfIn)

    # - Compare states and time before and after
    vStateBefore = np.copy(fl.vState)
    fl.evolve(tsIn, tDuration=0.08)
    assert fl.t == 0.08
    assert (vStateBefore != fl.vState).any()

    fl.reset_all()
    assert fl.t == 0
    assert (vStateBefore == fl.vState).all()


def test_ffiaf_spkin_torch():
    # - Test FFIAFSpkInTorch
    from NetworksPython.layers import FFIAFSpkInTorch
    from NetworksPython.timeseries import TSEvent
    import numpy as np

    nSizeIn = 384
    nSize = 512

    tDur = 0.01
    tDt = 0.001
    nSpikesIn = 50

    mfW = np.random.randn(nSizeIn,nSize)
    fl = FFIAFSpkInTorch(mfW, tDt=tDt, bRecord=False)

    mfIn = 0.005 * np.array([
        np.sin(np.linspace(0,10*tDur,int(tDur/tDt)) + fPhase) for fPhase in np.linspace(0,3, nSizeIn)
    ]).T
    vtIn = np.sort(np.random.rand(nSpikesIn)) * tDur
    vnChIn = np.random.randint(nSizeIn, size=nSpikesIn)
    tsIn = TSEvent(vtIn, vnChIn, nNumChannels=nSizeIn)

    # - Compare states and time before and after
    vStateBefore = np.copy(fl.vState)
    fl.evolve(tsIn, tDuration=0.08)
    assert fl.t == 0.08
    assert (vStateBefore != fl.vState).any()

    fl.reset_all()
    assert fl.t == 0
    assert (vStateBefore == fl.vState).all()

def test_reciaf_torch():
    # - Test RecIAFTorch

    from NetworksPython.layers import RecIAFTorch
    from NetworksPython.timeseries import TSContinuous
    import numpy as np

    nSize = 512

    tDur = 0.01
    tDt = 0.001

    mfW = 0.001*np.random.randn(nSize,nSize)
    rl = RecIAFTorch(mfW, tDt=tDt, vfBias=0.0101, bRecord=False)

    mfIn = 0.0001 * np.array([
        np.sin(np.linspace(0,10*tDur,int(tDur/tDt)) + fPhase) for fPhase in np.linspace(0,3, nSize)
    ]).T
    vtIn = np.arange(mfIn.shape[0]) * tDt
    tsIn = TSContinuous(vtIn, mfIn)

    # - Compare states and time before and after
    vStateBefore = np.copy(rl.vState)
    rl.evolve(tsIn, tDuration=0.08)
    assert rl.t == 0.08
    assert (vStateBefore != rl.vState).any()

    rl.reset_all()
    assert rl.t == 0
    assert (vStateBefore == rl.vState).all()

def test_reciaf_spkin_torch():
    # - Test RecIAFSpkInTorch
    from NetworksPython.layers import RecIAFSpkInTorch
    from NetworksPython.timeseries import TSEvent
    import numpy as np

    nSizeIn = 384
    nSize = 512

    tDur = 0.01
    tDt = 0.001
    nSpikesIn = 50

    mfIn = 0.005 * np.array([
        np.sin(np.linspace(0,10*tDur,int(tDur/tDt)) + fPhase) for fPhase in np.linspace(0,3, nSizeIn)
    ]).T
    vtIn = np.sort(np.random.rand(nSpikesIn)) * tDur
    vnChIn = np.random.randint(nSizeIn, size=nSpikesIn)
    tsIn = TSEvent(vtIn, vnChIn, nNumChannels=nSizeIn)

    mfWIn = 0.1*np.random.randn(nSizeIn, nSize)
    mfWRec = 0.001*np.random.randn(nSize, nSize)
    rl = RecIAFSpkInTorch(mfWIn, mfWRec, tDt=tDt, bRecord=False)
    

    # - Compare states and time before and after
    vStateBefore = np.copy(rl.vState)
    rl.evolve(tsIn, tDuration=0.08)
    assert rl.t == 0.08
    assert (vStateBefore != rl.vState).any()

    rl.reset_all()
    assert rl.t == 0
    assert (vStateBefore == rl.vState).all()