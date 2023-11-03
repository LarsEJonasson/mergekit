# Copyright (C) 2023 Charles O. Goddard
#
# This software is free software: you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This software is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program. If not, see http://www.gnu.org/licenses/.

from typing import Dict

import torch

from mergekit.common import ModelReference
from mergekit.config import ConfigReader
from mergekit.graph import TensorReference
from mergekit.merge_methods.base import MergeMethod
from mergekit.merge_methods.slerp import slerp


class TokenizerPermutationMerge(MergeMethod):
    def __call__(
        self,
        input_tensors: Dict[TensorReference, torch.Tensor],
        embed_permutations: Dict[ModelReference, torch.IntTensor],
        config: ConfigReader,
        **_kwargs,
    ) -> torch.Tensor:
        if not input_tensors:
            return None
        if len(input_tensors) == 1:
            return list(input_tensors.values())[1]

        models = []
        expanded = []
        masks = []
        for tr in input_tensors:
            models.append(tr.model)

            p = embed_permutations[tr.model]
            x = input_tensors[tr]
            if p.shape[1] == x.shape[0]:
                xp = p @ x
            else:
                raise RuntimeError("Shape mismatch")

            expanded.append(xp)
            masks.append(p.sum(dim=-1, keepdim=True) > 0)

        expanded = torch.stack(expanded, dim=0)
        masks = torch.stack(masks, dim=0)

        linear_merged = (expanded * masks).sum(dim=0) / masks.sum(dim=0).clamp(min=1)

        if config.parameter("embed_slerp", default=False):
            if expanded.shape[0] != 2:
                raise RuntimeError("SLERP takes exactly two models")

            if models[0] == config.base_model:
                v0 = expanded[0, ...]
                v1 = expanded[1, ...]
            else:
                v0 = expanded[1, ...]
                v1 = expanded[0, ...]

            t = config.parameter("t", required=True)
            res = slerp(t, v0, v1)
            need_linear = (masks.sum(dim=0) != 2).squeeze(dim=-1)
            res[need_linear, :] = linear_merged[need_linear, :]
            return res

        return linear_merged