"""
Data Steps
====================================
You can find here steps that take action on data.

..
    Copyright 2019, Neuraxio Inc.

    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at

        http://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.

"""
import random
from typing import Iterable

import numpy as np

from neuraxle.base import BaseStep, MetaStepMixin, NonFittableMixin, ExecutionContext, NonTransformableMixin
from neuraxle.data_container import DataContainer
from neuraxle.pipeline import Pipeline
from neuraxle.steps.flow import TrainOnlyWrapper
from neuraxle.steps.output_handlers import InputAndOutputTransformerMixin


class DataShuffler(NonFittableMixin, InputAndOutputTransformerMixin, BaseStep):
    """
    Data Shuffling step that shuffles data inputs, and expected_outputs at the same time.

    .. code-block:: python

        p = Pipeline([
            TrainOnlyWrapper(DataShuffler(seed=42, increment_seed_after_each_fit=True, increment_seed_after_each_fit=False)),
            EpochRepeater(ForecastingPipeline(), epochs=EPOCHS, repeat_in_test_mode=False)
        ])

    .. warning::
        You probably always want to wrap this step by a :class:`TrainOnlyWrapper`

    .. seealso::
        :class:`EpochRepeater`,
        :class:`TrainOnlyWrapper`,
        :class:`InputAndOutputTransformerMixin`,
        :class:`BaseStep`
    """

    def __init__(self, seed=None, increment_seed_after_each_fit=True):
        InputAndOutputTransformerMixin.__init__(self)
        BaseStep.__init__(self)
        if seed is None:
            seed = 42
        self.seed = seed
        self.increment_seed_after_each_fit = increment_seed_after_each_fit

    def transform(self, data_inputs):
        """
        Shuffle data inputs, and expected outputs.

        :param data_inputs: (data inputs, expected outputs) tuple to shuffle
        :return:
        """
        if self.increment_seed_after_each_fit:
            self.seed += 1

        di, eo = data_inputs
        data = list(zip(di, eo))
        random.Random(self.seed).shuffle(data)

        data_inputs_shuffled, expected_outputs_shuffled = list(zip(*data))

        return list(data_inputs_shuffled), list(expected_outputs_shuffled)


class EpochRepeater(MetaStepMixin, BaseStep):
    """
    Repeat wrapped step fit, or transform for the number of epochs passed in the constructor.

    .. code-block:: python

        p = Pipeline([
            TrainOnlyWrapper(DataShuffler(seed=42, increment_seed_after_each_fit=True, increment_seed_after_each_fit=False)),
            EpochRepeater(ForecastingPipeline(), epochs=EPOCHS, repeat_in_test_mode=False)
        ])

    .. seealso::
        :class:`DataShuffler`,
        :class:`MetaStepMixin`,
        :class:`TrainOnlyWrapper`,
        :class:`TestOnlyWrapper`,
        :class:`BaseStep`
    """

    def __init__(self, wrapped, epochs, fit_only=False, repeat_in_test_mode=False):
        BaseStep.__init__(self)
        MetaStepMixin.__init__(self, wrapped)
        self.repeat_in_test_mode = repeat_in_test_mode
        self.fit_only = fit_only
        self.epochs = epochs

    def _fit_transform_data_container(self, data_container: DataContainer, context: ExecutionContext) -> (
            'BaseStep', DataContainer):
        """
        Fit transform wrapped step self.epochs times using wrapped step handle fit transform method.

        :param data_container: data container
        :type data_container: DataContainer
        :param context: execution context
        :type context: ExecutionContext
        :return: (fitted self, data container)
        :rtype: (BaseStep, DataContainer)
        """
        if not self.fit_only:
            for _ in range(self.epochs - 1):
                self.wrapped = self.wrapped.handle_fit(data_container.copy(), context)

        self.wrapped, data_container = self.wrapped.handle_fit_transform(data_container, context)
        return self, data_container

    def fit_transform(self, data_inputs, expected_outputs=None) -> ('BaseStep', Iterable):
        """
        Fit transform wrapped step self.epochs times.

        :param data_inputs: data inputs to fit on
        :param expected_outputs: expected_outputs to fit on
        :return: fitted self
        """
        if not self.fit_only:
            epochs = self._get_epochs()
            for _ in range(epochs):
                self.wrapped = self.wrapped.fit(data_inputs, expected_outputs)

        self.wrapped, outputs = self.wrapped.fit_transform(data_inputs, expected_outputs)

        return self, outputs

    def _fit_data_container(self, data_container: DataContainer, context: ExecutionContext) -> 'BaseStep':
        """
        Fit wrapped step self.epochs times using wrapped step handle fit method.

        :param data_container: data container
        :type data_container: DataContainer
        :param context: execution context
        :type context: ExecutionContext
        :return: (fitted self, data container)
        :rtype: (BaseStep, DataContainer)
        """
        epochs = self._get_epochs()

        for _ in range(epochs):
            self.wrapped = self.wrapped.handle_fit(data_container.copy(), context)
        return self

    def fit(self, data_inputs, expected_outputs=None) -> 'BaseStep':
        """
        Fit wrapped step self.epochs times.

        :param data_inputs: data inputs to fit on
        :param expected_outputs: expected_outputs to fit on
        :return: fitted self
        """
        epochs = self._get_epochs()

        for _ in range(epochs):
            self.wrapped = self.wrapped.fit(data_inputs, expected_outputs)
        return self

    def _get_epochs(self):
        epochs = self.epochs
        if self._should_repeat_fit():
            epochs = 1
        return epochs

    def _should_repeat_fit(self):
        return self.is_train or not self.is_train and self.repeat_in_test_mode


class TrainShuffled(Pipeline):
    def __init__(self, wrapped, seed=None):
        Pipeline.__init__(self, [
            TrainOnlyWrapper(DataShuffler(seed=seed)),
            wrapped
        ])


class ZipData(NonFittableMixin, NonTransformableMixin, BaseStep):
    """
    Zip two data sources together. Pass the name of the sub data containers to merge in the current data container.

    Code example:

    .. code-block:: python

        data_container_header_values = DataContainer(data_inputs=data_inputs_headers, expected_outputs=expected_outputs_headers)
        data_container_3d = DataContainer(data_inputs=data_inputs_3d, expected_outputs=expected_outputs_3d) \
            .add_sub_data_container('header_values', data_container_2d)

        p = Pipeline([
            ZipData(["header_values"])
        ])

        data_container_3d = p.handle_transform(data_container_3d, ExecutionContext())


    .. seealso::
        :class:`neuraxle.base.NonFittableMixin`,
        :class:`neuraxle.base.NonTransformableMixin`,
        :class:`neuraxle.base.BaseStep`
        :class:`neuraxle.data_container.DataContainer`
    """
    def __init__(self, data_sources):
        BaseStep.__init__(self)
        NonTransformableMixin.__init__(self)
        NonFittableMixin.__init__(self)

        self.data_sources = data_sources

    def _fit_transform_data_container(self, data_container: DataContainer, context: ExecutionContext) -> ('BaseStep', DataContainer):
        return self, self._zip_sub_data_containers(data_container)

    def _transform_data_container(self, data_container: DataContainer, context: ExecutionContext) -> DataContainer:
        return self._zip_sub_data_containers(data_container)

    def _zip_sub_data_containers(self, data_container):
        sub_data_containers_to_zip = []
        for name, sub_data_container in data_container.sub_data_containers:
            if name in self.data_sources:
                sub_data_containers_to_zip.append(sub_data_container)

        for data_container_to_zip in sub_data_containers_to_zip:
            data_container = self._zip_data_container(data_container, data_container_to_zip)

        return data_container

    def _zip_data_container(self, data_container, data_container_to_zip):
        data_inputs = self._zip_np_arrays(data_container.data_inputs, data_container_to_zip.data_inputs)
        data_container.set_data_inputs(data_inputs)

        expected_outputs = self._zip_np_arrays(data_container.expected_outputs, data_container_to_zip.expected_outputs)
        data_container.set_expected_outputs(expected_outputs)

        return data_container

    def _zip_np_arrays(self, np_array, np_array_to_zip):
        while len(np_array_to_zip.shape) < len(np_array.shape):
            np_array_to_zip = np.expand_dims(np_array_to_zip, axis=-1)

        target_shape = tuple(list(np_array.shape[:-1]) + [np_array_to_zip.shape[-1]])
        np_array_to_zip = np.broadcast_to(np_array_to_zip, target_shape)

        return np.concatenate((np_array, np_array_to_zip), axis=-1)