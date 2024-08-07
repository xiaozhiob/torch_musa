"""Test index operators."""

# pylint: disable=missing-function-docstring, redefined-outer-name, unused-import, unexpected-keyword-arg
import copy
from functools import reduce
import pytest
import torch
import torch_musa
from torch_musa import testing

torch.manual_seed(41)


def get_indices(inputs):
    indices = []
    values = []
    for input_self in inputs:
        indice = []  # tuple of LongTensor, and its length must match the input's dim
        # the number of items must not exceed input items
        num_item = min(10, input_self.numel())
        shape = input_self.shape
        for dim in tuple(range(input_self.dim())):
            max_idx = shape[dim]
            if max_idx == 0:
                continue
            indice.append(torch.randint(max_idx, (num_item,)))

        indices.append(tuple(indice))
        if num_item == 0:
            values.append(torch.rand(1, 1))
        else:
            values.append(torch.randn(num_item))
    return [indices, values]


input_data = testing.get_raw_data() + [
    torch.rand(10, 10, 2, 2, 1) > 0.5,
]

[indices, values] = get_indices(input_data)

input_datas = []
for i, data in enumerate(input_data):
    input_datas.append({"input": data, "indices": indices[i], "values": values[i]})

dtypes = [
    torch.uint8,
    torch.bfloat16,
    torch.float16,
    torch.float32,
    torch.int32,
    torch.int64,
    torch.bool,
]

ind_dtypes = [torch.int64]  # cpu only support int64 indices


# test index_put
@testing.test_on_nonzero_card_if_multiple_musa_device(1)
@pytest.mark.parametrize("input_data", input_datas)
@pytest.mark.parametrize("dtype", dtypes)
@pytest.mark.parametrize("ind_dtype", ind_dtypes)
# since the indices generated by `get_indices` may
# have duplicate elements, we only test accumulate case here
def test_index_put(input_data, dtype, ind_dtype):
    if testing.get_musa_arch() < 22 and dtype == torch.bfloat16:
        return

    input_data["input"] = input_data["input"].to(dtype)
    input_data["indices"] = [x.to(ind_dtype) for x in input_data["indices"]]
    input_data["values"] = input_data["values"].to(dtype)
    input_data["accumulate"] = True
    test = testing.OpTest(func=torch.index_put, input_args=input_data)
    test.check_result()
    test.check_grad_fn()
    inplace_input = copy.deepcopy(input_data)
    test = testing.InplaceOpChek(
        func_name=torch.index_put.__name__ + "_",
        self_tensor=inplace_input["input"],
        input_args={
            "indices": inplace_input["indices"],
            "values": inplace_input["values"],
            "accumulate": True,
        },
    )
    test.check_address()
    test.check_res()


@testing.test_on_nonzero_card_if_multiple_musa_device(1)
@pytest.mark.parametrize(
    "config",
    [
        # input_shape, value_shape, index_shapes, is_nhwc(optional)
        # not adjacent cases
        [(16, 16, 16, 16), (3, 4, 16, 16), ((3, 4), None, (3, 1))],
        [(16, 16, 16, 16), (1, 4, 1, 16), ((3, 4), None, (3, 1))],
        [(8, 12, 16, 20, 24), (2, 4, 8, 16, 24), (None, (2, 4), None, (4,))],
        [(8, 12, 16, 20, 24), (1, 4, 1, 16, 1), (None, (2, 4), None, (4,))],
        [(8, 12, 16, 20), (1, 6, 8, 16), (None, (6,), None, (6,)), (True, True)],
        # channels_last cases
        [
            (8, 12, 16, 20),
            (
                2,
                4,
                12,
                16,
                20,
            ),
            ((2, 4),),
            (True, False),
        ],
        [(8, 12, 16, 20), (20,), ((2, 4),), (True, False)],
        [(8, 12, 16, 20), (6, 12, 16, 20), ((6,),), (True, True)],
        [(8, 12, 16, 20), (6, 12, 16, 20), ((6,),), (False, True)],
        [
            (8, 12, 16, 20),
            (
                16,
                1,
            ),
            ((6,),),
            (True, False),
        ],
        # (maybe) vectorized cases
        [(16, 10240), (4, 10240), ((4,),)],
        [(16, 18, 7), (8, 18, 7), ((8,),)],
        [(16, 16, 16, 4, 2), (2, 3, 16, 4, 2), ((3,), (2, 3))],
        [(16, 16, 16, 16, 2, 2), (2, 4, 16, 16, 2, 2), ((4,), (2, 4))],
        [(16, 16, 16, 16, 2, 2), (16, 16, 2, 2), ((4,), (2, 4))],
        [(16, 16, 16, 4, 5, 6, 7), (2, 1, 4, 5, 6, 7), ((4,), (2, 4), (4,))],
        [(16, 16, 16, 4, 5, 6, 7, 2), (2, 4, 4, 5, 6, 7, 2), ((4,), (2, 4), (4,))],
        [(12146, 256, 7, 7), (3858, 256, 7, 7), ((3858,),)],
        [(12146, 255, 7, 7), (3858, 255, 7, 7), ((3858,),)],
        [
            (16, 16, 16, 16),
            (16, 2, 3, 16, 16),
            (
                None,
                (2, 3),
            ),
        ],
        [(16, 16, 16, 16, 4), (16, 2, 3, 16, 4), (None, (2, 3), (2, 3))],
        [(16, 16, 16, 16, 4), (16, 2, 3, 16, 4), (None, (2, 3), (1, 3))],
        [(16, 16, 16, 16, 4), (16, 4), (None, (2, 3), (1, 3))],
        [(16, 16, 16, 16, 4), (16, 16, 2, 3, 16, 4), (None, None, (2, 3))],
        [(16, 16, 16, 16, 4), (2, 3, 16, 4), (None, None, (2, 3))],
        [(16, 16, 16, 16, 4), (1, 1, 16, 4), (None, None, (2, 3))],
    ],
)
@pytest.mark.parametrize("dtype", dtypes + [torch.int8])
@pytest.mark.parametrize("ind_dtype", [torch.int32, torch.int64])
def test_index_put_by_slicing(config, dtype, ind_dtype):
    if testing.get_musa_arch() < 22 and dtype == torch.bfloat16:
        return

    def func(self, indices, values):
        self[indices] = values
        return self

    is_nhwc = [False, False] if len(config) < 4 else config[3]
    indices = []

    for i, index_shape in enumerate(config[2]):
        if index_shape:
            index_num = reduce((lambda x, y: x * y), index_shape)
            indices.append(
                torch.randperm(config[0][i])[:index_num]
                .to(ind_dtype)
                .reshape(index_shape)
            )
        else:
            indices.append(slice(None))
    self = (
        torch.rand(config[0]) > 0.5
        if dtype == torch.bool
        else torch.randn(config[0]).to(dtype)
    )
    values = (
        torch.rand(config[1]) > 0.5
        if dtype == torch.bool
        else torch.randn(config[1]).to(dtype)
    )
    input_data = {
        "self": self.to(memory_format=torch.channels_last) if is_nhwc[0] else self,
        "indices": indices,
        "values": (
            values.to(memory_format=torch.channels_last) if is_nhwc[1] else values
        ),
    }
    test = testing.OpTest(func=func, input_args=input_data)
    test.check_result()


@testing.test_on_nonzero_card_if_multiple_musa_device(1)
@pytest.mark.parametrize("tensor_dtype", dtypes)
@pytest.mark.parametrize("ind_dtype", ind_dtypes)
def test_index_put_different_device_indices(tensor_dtype, ind_dtype):
    if testing.get_musa_arch() < 22 and tensor_dtype == torch.bfloat16:
        return
    input_data = torch.randperm(20).reshape(1, 20).to(tensor_dtype)
    value = torch.randperm(5).to(tensor_dtype)
    indices_0_cpu = torch.tensor([[0]], device="cpu", dtype=ind_dtype)
    indices_1_musa = torch.tensor([[3, 2, 0, 17, 19]], device="musa", dtype=ind_dtype)

    input_musa = input_data.to("musa")
    target_device = input_musa.device
    input_musa[indices_0_cpu, indices_1_musa] = value.to("musa")
    musa_result = input_musa.cpu()

    input_cpu_golden = input_data.clone()
    indices_1_cpu = torch.tensor([[3, 2, 0, 17, 19]], device="cpu", dtype=ind_dtype)
    input_cpu_golden[indices_0_cpu, indices_1_cpu] = value
    cpu_result = input_cpu_golden

    assert (musa_result == cpu_result).all()
    assert musa_result.dtype == cpu_result.dtype
    assert musa_result.shape == cpu_result.shape
    assert input_musa.device == target_device


@testing.test_on_nonzero_card_if_multiple_musa_device(1)
@pytest.mark.parametrize("input_data", input_datas)
@pytest.mark.parametrize("dtype", dtypes)
def test_index_put_bool_index(input_data, dtype):
    if testing.get_musa_arch() < 22 and dtype == torch.bfloat16:
        return
    data = input_data["input"].to(dtype)
    inds = torch.randn(data.shape)
    inds = inds.ge(0)
    if inds.sum() == 0:  # for random inds are all less than 0.
        return
    musa_data = data.musa()

    data[inds] = 1.0
    musa_data[inds] = 1.0
    assert torch.allclose(data, musa_data.cpu())


# test index
@testing.test_on_nonzero_card_if_multiple_musa_device(1)
@pytest.mark.parametrize(
    "config",
    [
        # input_shape, index_shapes, is_nhwc(optional)
        [(16, 16, 16, 16), ((3, 4), None, (3, 1))],
        [(8, 12, 16, 20, 24), (None, (2, 4), None, (4,))],
        [(8, 12, 16, 20), ((2, 4),), True],
        [(8, 12, 16, 20), ((2, 4),), False],
        [(16, 16, 16, 16, 4), (None, None, (2, 3))],
    ],
)
@pytest.mark.parametrize("tensor_dtype", dtypes)
@pytest.mark.parametrize("ind_dtype", ind_dtypes)
def test_index_tensor(config, tensor_dtype, ind_dtype):
    if testing.get_musa_arch() < 22 and tensor_dtype == torch.bfloat16:
        return

    def func(self, indices):
        out = self[indices]
        return out

    is_nhwc = False if len(config) < 3 else config[2]
    indices = []
    for i, index_shape in enumerate(config[1]):
        if index_shape:
            index_num = reduce((lambda x, y: x * y), index_shape)
            indices.append(
                torch.randperm(config[0][i])[:index_num]
                .to(ind_dtype)
                .reshape(index_shape)
            )
        else:
            indices.append(slice(None))
    self = (
        torch.rand(config[0]) > 0.5
        if tensor_dtype == torch.bool
        else torch.randn(config[0]).to(tensor_dtype)
    )
    input_data = {
        "self": self.to(memory_format=torch.channels_last) if is_nhwc else self,
        "indices": indices,
    }
    test = testing.OpTest(func=func, input_args=input_data)
    test.check_result()


@testing.test_on_nonzero_card_if_multiple_musa_device(1)
@pytest.mark.parametrize("tensor_dtype", dtypes)
def test_index_tensor_bool_index(tensor_dtype):
    if testing.get_musa_arch() < 22 and tensor_dtype == torch.bfloat16:
        return
    input_data = torch.randperm(40).reshape(2, 20).to(tensor_dtype)
    inds = torch.randn(input_data.shape)
    inds = inds.ge(0.5)
    input_musa = input_data.to("musa")
    musa_result = input_musa[inds]

    input_cpu_golden = input_data.clone()
    cpu_result = input_cpu_golden[inds]

    assert (musa_result.cpu() == cpu_result).all()
    assert musa_result.dtype == cpu_result.dtype
    assert musa_result.shape == cpu_result.shape
    assert musa_result.device == input_musa.device


# test index_select
input_datas = [
    {
        "input": torch.zeros(
            10,
        ),
        "dim": 0,
        "index": torch.randint(10, (5,)),
    },
    {"input": torch.zeros(10, 5), "dim": 1, "index": torch.randint(5, (3,))},
    {"input": torch.zeros(10, 5, 3), "dim": 2, "index": torch.randint(3, (2,))},
    {"input": torch.zeros(10, 5, 1, 3), "dim": 1, "index": torch.randint(1, (1,))},
    {"input": torch.zeros(10, 5, 1, 3, 5), "dim": 4, "index": torch.randint(5, (3,))},
    {
        "input": torch.zeros(10, 5, 1, 3, 2, 6),
        "dim": 1,
        "index": torch.randint(5, (3,)),
    },
    {
        "input": torch.zeros(10, 5, 1, 3, 1, 2, 7),
        "dim": 3,
        "index": torch.randint(3, (2,)),
    },
    {
        "input": torch.zeros(10, 5, 1, 3, 1, 2, 3, 8),
        "dim": 7,
        "index": torch.randint(8, (3,)),
    },
]
dtypes = testing.get_all_support_types()
dtypes.extend([torch.uint8, torch.int16, torch.float16, torch.float64])


@testing.test_on_nonzero_card_if_multiple_musa_device(1)
@pytest.mark.parametrize("input_data", input_datas)
@pytest.mark.parametrize("dtype", dtypes)
def test_index_select(input_data, dtype):
    input_data["input"] = input_data["input"].to(dtype)
    test = testing.OpTest(func=torch.index_select, input_args=input_data)
    test.check_result()
    test.check_grad_fn()


@pytest.mark.skipif(
    testing.get_musa_arch() < 22, reason="bf16 is not supported on arch older than qy2"
)
@testing.test_on_nonzero_card_if_multiple_musa_device(1)
@pytest.mark.parametrize("input_data", input_datas)
def test_index_select_bf16(input_data):
    input_data["input"] = input_data["input"].to(torch.bfloat16)
    test = testing.OpTest(func=torch.index_select, input_args=input_data)
    test.check_result(bf16=True)
    test.check_grad_fn()
