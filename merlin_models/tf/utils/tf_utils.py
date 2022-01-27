#
# Copyright (c) 2021, NVIDIA CORPORATION.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
from typing import Union

import tensorflow as tf

from merlin_models.tf.typing import TabularData


def get_output_sizes_from_schema(schema, batch_size=0, max_sequence_length=None):
    sizes = {}
    for feature in schema.feature:
        name = feature.name
        if feature.HasField("value_count"):
            sizes[name] = tf.TensorShape(
                [
                    batch_size,
                    max_sequence_length if max_sequence_length else feature.value_count.max,
                ]
            )
        elif feature.HasField("shape"):
            sizes[name] = tf.TensorShape([batch_size] + [d.size for d in feature.shape.dim])
        else:
            sizes[name] = tf.TensorShape([batch_size, 1])

    return sizes


def calculate_batch_size_from_input_shapes(input_shapes):
    return [i for i in input_shapes.values() if not isinstance(i, tuple)][0][0]


def maybe_serialize_keras_objects(
    self,
    config,
    maybe_serialize_keys,
):
    for key in maybe_serialize_keys:
        maybe_value = getattr(self, key, None)
        if maybe_value:
            if isinstance(maybe_value, dict):
                config[key] = {
                    k: tf.keras.utils.serialize_keras_object(v) for k, v in maybe_value.items()
                }
            elif isinstance(maybe_value, (list, tuple)):
                config[key] = [tf.keras.utils.serialize_keras_object(v) for v in maybe_value]
            else:
                config[key] = tf.keras.utils.serialize_keras_object(maybe_value)

    return config


def maybe_deserialize_keras_objects(
    config, to_deserialize, deserialize_fn=tf.keras.utils.deserialize_keras_object
):
    if isinstance(to_deserialize, list):
        to_deserialize = {k: deserialize_fn for k in to_deserialize}

    custom_objects = {}

    for key, fn in to_deserialize.items():
        maybe_val = config.get(key, None)
        if maybe_val:
            if isinstance(maybe_val, list):
                config[key] = [fn(v, custom_objects=custom_objects) for v in maybe_val]
            else:
                config[key] = fn(maybe_val, custom_objects=custom_objects)

    return config


def extract_topk(ks, scores, labels):
    max_k = tf.reduce_max(ks)
    topk_scores, topk_indices = tf.math.top_k(scores, max_k)
    topk_labels = gather_torch_like(labels, topk_indices, max_k)
    return topk_scores, topk_indices, topk_labels


def tranform_label_to_onehot(labels, vocab_size):
    return tf.one_hot(tf.reshape(labels, (-1,)), vocab_size)


def create_output_placeholder(scores, ks):
    return tf.Variable(tf.zeros([tf.shape(scores)[0], len(ks)], tf.float32))


def gather_torch_like(labels, indices, max_k):
    # gather_indices = []
    gather_indices = tf.TensorArray(tf.int32, size=tf.shape(indices)[0])
    for i in range(tf.shape(indices)[0]):
        gather_indices = gather_indices.write(
            i,
            tf.concat(
                [i * tf.ones((max_k, 1), tf.int32), tf.expand_dims(indices[i, :], -1)], axis=1
            ),
        )
    all_indices = gather_indices.stack()
    labels = tf.reshape(tf.gather_nd(labels, all_indices), tf.shape(indices))
    return labels


def batch_ref(inputs: Union[tf.Tensor, TabularData]):
    """Get hash-code of a tensor or a dictionary of tensors."""

    if isinstance(inputs, tf.Tensor):
        return hash(inputs.ref())

    refs = []
    keys = sorted(inputs.keys())
    for key in keys:
        refs.append(inputs[key].ref())

    return hash(tuple(refs))