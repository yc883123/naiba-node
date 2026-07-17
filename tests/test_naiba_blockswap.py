"""
naiba_wan_blockswap 阶段二验证脚本（开发期，可经 .gitignore 排除）

使用 mock 的 ComfyUI 接口验证：
1. 连续 ON_LOAD 10 次，pre/post hook 数量保持不变（幂等安装）
2. 同一 UNet 的优化/未优化两分支：未优化分支 forward 不发生 CPU/GPU 搬运（no-op）
3. ON_CLEANUP 引用计数归零时移除全部 hooks 并从注册表弹出
4. 模型卸载再加载后 hooks 数量不增加（不泄漏闭包/hooks）
5. 主块/VACE 块数量限制到模型实际数量内
"""

import sys
import os
import types
import torch
import torch.nn as nn

# 将节点所在目录加入 sys.path（测试脚本位于 tests/ 子目录）
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import naiba_wan_blockswap as M
from comfy.patcher_extension import CallbacksMP


# --------------------------- mock 基础设施 ---------------------------
class FakeBlock(nn.Module):
    def __init__(self):
        super().__init__()
        self.linear = nn.Linear(4, 4)

    def forward(self, x):
        return self.linear(x)


class FakeUNet(nn.Module):
    def __init__(self, n_blocks, n_vace=0):
        super().__init__()
        self.blocks = nn.ModuleList([FakeBlock() for _ in range(n_blocks)])
        if n_vace:
            self.vace_blocks = nn.ModuleList([FakeBlock() for _ in range(n_vace)])

    def forward(self, x, t=None, context=None, transformer_options=None, **kwargs):
        to = transformer_options if transformer_options is not None else {}
        h = x
        for b in self.blocks:
            h = b(h)
        if hasattr(self, "vace_blocks"):
            for b in self.vace_blocks:
                h = b(h)
        return h


class FakePatcher:
    def __init__(self, unet, offload_device):
        self.model = types.SimpleNamespace(diffusion_model=unet)
        self.offload_device = offload_device
        self.model_options = {"transformer_options": {}}
        self._callbacks = {}

    def clone(self):
        new = FakePatcher(self.model.diffusion_model, self.offload_device)
        new.model_options = {"transformer_options": dict(self.model_options["transformer_options"])}
        # ComfyUI clone 会复制 callbacks；此处基类无 blockswap 回调，留空即可
        new._callbacks = {}
        return new

    def add_callback_with_key(self, ct, key, cb):
        self._callbacks.setdefault(ct, {}).setdefault(key, []).append(cb)

    def remove_callbacks_with_key(self, ct, key):
        self._callbacks.get(ct, {}).pop(key, None)

    def fire(self, ct, *args):
        for cbs in self._callbacks.get(ct, {}).values():
            for cb in cbs:
                cb(self, *args)


def count_handles(unet):
    ctrl = M._CONTROLLER_REGISTRY.get(id(unet))
    return 0 if ctrl is None else len(ctrl.handles)


def make_counter():
    calls = []

    def counting_to(self, *a, **k):
        calls.append((id(self), a, k))
        return nn.Module.to(self, *a, **k)

    return calls, counting_to


# --------------------------- 测试 ---------------------------
def main():
    device = torch.device("cpu")  # 用 CPU 模拟（无 cuda 时自动关闭非阻塞）
    n_blocks, n_vace = 5, 3
    unet = FakeUNet(n_blocks, n_vace)
    base = FakePatcher(unet, offload_device=device)

    node = M.NaibaWanBlockSwap()
    out = node.optimize(base, blocks_to_swap=3, vace_blocks_to_swap=2, prefetch_blocks=1)
    model_clone = out[0]

    expected = 2 + 2 * n_blocks + 2 * n_vace  # unet pre/post + 每块的 pre/post

    # 1) 连续 ON_LOAD 10 次，hook 数量不变
    for _ in range(10):
        model_clone.fire(CallbacksMP.ON_LOAD, device, 0, False, False)
    assert count_handles(unet) == expected, f"ON_LOAD x10 hook 数量异常: {count_handles(unet)} != {expected}"
    ctrl = M._CONTROLLER_REGISTRY.get(id(unet))
    assert ctrl.refcount == 10, f"refcount 应为 10，实际 {ctrl.refcount}"
    print(f"[OK] ON_LOAD x10 后 hook 数量稳定 = {count_handles(unet)} (refcount={ctrl.refcount})")

    # 2) 未优化分支 forward 不发生搬运（no-op）
    calls, counting_to = make_counter()
    for b in list(unet.blocks) + (list(unet.vace_blocks) if hasattr(unet, "vace_blocks") else []):
        b.to = types.MethodType(counting_to, b)
    # 未优化分支：transformer_options 无 block_swap_config
    with torch.no_grad():
        unet(torch.randn(2, 4), transformer_options={})
    assert len(calls) == 0, f"未优化分支 forward 不应发生搬运，实际 {len(calls)} 次 .to()"
    print(f"[OK] 未优化分支 forward 无搬运 (to_calls={len(calls)})")

    # 2b) 优化分支 forward 发生搬运（配置存在时 hooks 生效）
    calls, counting_to = make_counter()
    for b in list(unet.blocks) + (list(unet.vace_blocks) if hasattr(unet, "vace_blocks") else []):
        b.to = types.MethodType(counting_to, b)
    opt_cfg = model_clone.model_options["transformer_options"]["block_swap_config"]
    assert opt_cfg is not None and opt_cfg.get("blocks_to_swap") == 3
    with torch.no_grad():
        unet(torch.randn(2, 4), transformer_options={"block_swap_config": opt_cfg})
    assert len(calls) > 0, "优化分支 forward 应发生块交换搬运"
    print(f"[OK] 优化分支 forward 触发块交换 (to_calls={len(calls)})")

    # 3) ON_CLEANUP 引用计数归零时移除全部 hooks
    for _ in range(10):
        model_clone.fire(CallbacksMP.ON_CLEANUP)
    assert id(unet) not in M._CONTROLLER_REGISTRY, "归零后注册表应弹出"
    print("[OK] ON_CLEANUP x10 后 hooks 已移除且注册表弹出")

    # 4) 卸载再加载后 hooks 数量不增加（重新安装回到期望值，无泄漏）
    model_clone.fire(CallbacksMP.ON_LOAD, device, 0, False, False)
    assert count_handles(unet) == expected, f"重载后 hook 数量异常: {count_handles(unet)}"
    print(f"[OK] 卸载再加载后 hook 数量 = {count_handles(unet)}（无泄漏）")

    # 5) 数量限制：blocks_to_swap 超出实际数量时被钳制
    base2 = FakePatcher(FakeUNet(5, n_vace), device)
    out2 = node.optimize(base2, blocks_to_swap=99, vace_blocks_to_swap=99, prefetch_blocks=99)
    mc2 = out2[0]
    mc2.fire(CallbacksMP.ON_LOAD, device, 0, False, False)
    cfg2 = mc2.model_options["transformer_options"]["block_swap_config"]
    assert cfg2["blocks_to_swap"] == 5, cfg2["blocks_to_swap"]
    assert cfg2["vace_blocks_to_swap"] == n_vace, cfg2["vace_blocks_to_swap"]
    assert cfg2["prefetch_blocks"] == 5, cfg2["prefetch_blocks"]
    print(f"[OK] 数量限制正确: blocks={cfg2['blocks_to_swap']}, vace={cfg2['vace_blocks_to_swap']}, prefetch={cfg2['prefetch_blocks']}")

    print("\n=== 阶段二验证全部通过 ===")


if __name__ == "__main__":
    main()
