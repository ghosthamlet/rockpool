# Change log

All notable changes between Rockpool releases will be documented in this file.

## [v1.0.8] -- 2020-01-17

### Added
- Introduced new `TimeSeries` class method `concatenate_t()`, which permits construction of a new time series by concatenating a set of existing time series, in the time dimension 
- `Network` class now provides a `to_dict()` method for export. `Network` now also can treat sub-`Network`s as layers.
- Training methods for spiking LIF Jax-backed layers in `rockpool.layers.training`. Tutorial demonstrating SGD training of a feed-forward LIF network. Improvements in JAX LIF layers.
- Added `filter_bank` layers, providing `layer` subclasses which act as filter banks with spike-based output
- Added a `filter_width` parameter for butterworth filters
- Added a convenience function `start_at_zero()` to delay `TimeSeries` so that it starts at 0
- Added a change log in `CHANGELOG.md`

### Changed
- Improved `TSEvent.raster()` to make it more intuitive. Rasters are now produced in line with time bases that can be created easily with `numpy.arange()`
- Updated `conda_merge_request.sh` to work for conda feedstock
- `TimeSeries.concatenate()` renamed to `concatenate_t()`
- `RecRateEuler` warns if `tau` is too small instead of silently changing `dt`

### Fixed or improved
- Fixed issue in `Layer`, where internal property was used when accessing `._dt`. This causes issues with layers that have an unusual internal type for `._dt` (e.g. if data is stored in a JAX variable on GPU)
- Reduce memory footprint of `.TSContinuous` by approximately half
- Reverted regression in layer class `.RecLIFJax_IO`, where `dt` was by default set to `1.0`, instead of being determined by `tau_...`
- Fixed incorrect use of `Optional[]` type hints
- Allow for small numerical differences in comparison between weights in NEST test `test_setWeightsRec`
- Improvements in inline documentation
- Increasing memory efficiency of `FFExpSyn._filter_data` by reducing kernel size
- Implemented numerically stable timestep count for TSEvent rasterisation
- Fixed bugs in `RidgeRegrTrainer`
- Fix plotting issue in time series
- Fix bug of RecRateEuler not handling `dt` argument in `__init__()`
- Fixed scaling between torch and nest weight parameters
- Move `contains()` method from `TSContinuous` to `TimeSeries` parent class
- Fix warning in `RRTrainedLayer._prepare_training_data()` when times of target and input are not aligned
- Brian layers: Replace `np.asscalar` with `float`

---
## [v1.0.7.post1] -- 2019-11-28

### Added
- New `.Layer` superclass `.RRTrainedLayer`. This superclass implements ridge regression for layers that support ridge regression training
- `.TimeSeries` subclasses now add axes labels on plotting
- New spiking LIF JAX layers, with documentation and tutorials `.RecLIFJax`, `.RecLIFJax_IO`, `.RecLIFCurrentInJax`, `.RecLIFCurrentInJAX_IO`
- Added `save` and `load` facilities to `.Network` objects
- `._matching_channels()` now accepts an arbitrary list of event channels, which is used when analysing a periodic time series

### Changed
- Documentation improvements
- :py:meth:`.TSContinuous.plot` method now supports ``stagger`` and ``skip`` arguments
- `.Layer` and `.Network` now deal with a `.Layer.size_out` attribute. This is used to determine whether two layers are compatible to connect, rather than using `.size`
- Extended unit test for periodic event time series to check non-periodic time series as well

### Fixed
- Fixed bug in `TSEvent.plot()`, where stop times were not correctly handled
- Fix bug in `Layer._prepare_input_events()`, where if only a duration was provided, the method would return an input raster with an incorrect number of time steps
- Fixed bugs in handling of periodic event time series `.TSEvent`
- Bug fix: `.Layer._prepare_input_events` was failing for `.Layer` s with spiking input
- `TSEvent.__call__()` now correctly handles periodic event time series

---
## [v1.0.6] -- 2019-11-01

- CI build and deployment improvements

---
## [v1.0.5] -- 2019-10-30

- CI Build and deployment improvements

---
## [v1.0.4] -- 2019-10-28

- Remove deployment dependency on docs
- Hotfix: Fix link to `Black`
- Add links to gitlab docs

---
## [v1.0.3] -- 2019-10-28

-  Hotfix for incorrect license text
-  Updated installation instructions
-  Included some status indicators in readme and docs
- Improved CI
-  Extra meta-data detail in `setup.py`
-  Added more detail for contributing
-  Update README.md

---
## [v1.0.2] -- 2019-10-25

- First public release
