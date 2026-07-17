"""
NaibaWanBlockSwap - WAN模型Block Swap节点
将transformer block在GPU和CPU之间交换以降低显存占用
完全独立实现，不导入任何内置节点类

阶段三（restore safe embedding offload）：
- UNet 顶层 forward 用 ContextVar 设置“本次执行配置”，避免并行 forward 互相覆盖
- 为 text_embedding / img_emb 添加成对动作：forward 前移到 device_to，forward 后移回
  offload_device，异常也通过 finally 恢复（通过包装 unet.forward 实现，因 ComfyUI
  不会自动为 diffusion_model 应用 WrappersMP.DIFFUSION_MODEL 包装）
- embedding 移动仅在当前执行配置开启对应选项时生效，不影响共享分支
- 预取复用同一 controller：仅预取实际交换的后续块；通过“已在设备上则跳过”去重，
  避免重复 .to(device)；非阻塞传输依赖默认 CUDA stream 的顺序保证拷贝先于计算
- CPU / DirectML 等非 cuda 设备自动关闭非阻塞传输与预取
"""

import comfy.model_management
import contextvars
import gc
import threading
import types
import weakref
import torch
from comfy.patcher_extension import CallbacksMP
from comfy.model_patcher import ModelPatcher
from tqdm import tqdm


# ---------------------------------------------------------------------------
# 模块级控制器注册表
# 底层 UNet（base_model.diffusion_model）由多个 ModelPatcher 分支共享，
# 因此以 id(unet) 为键集中管理 hooks 与引用计数，保证同一 UNet 只安装一套 hooks。
# 控制器仅持有 unet 的弱引用，卸载后不阻止其被 GC。
# ---------------------------------------------------------------------------
_CONTROLLER_REGISTRY: "dict[int, _BlockSwapController]" = {}
_REGISTRY_LOCK = threading.Lock()

# 用于 add_callback_with_key 的固定 key，避免同一 patcher 重复注册回调
_CALLBACK_KEY = "naiba_wan_blockswap"

# 本次 forward 的执行配置（ContextVar）：保证并行 forward 之间互不覆盖
_EXEC_CONFIG_VAR = contextvars.ContextVar("naiba_wan_blockswap_exec_cfg", default=None)

# 每个线程保存最近一次 set 的 token，便于在 forward 结束后 reset（异常路径也安全）
_thread_local = threading.local()


class _BlockSwapController:
    """集中管理某个共享 UNet 的 block swap hooks 与引用计数（幂等安装）。"""

    __slots__ = ("unet_ref", "unet_id", "handles", "refcount", "installed", "_orig_forward")

    def __init__(self, unet):
        self.unet_ref = weakref.ref(unet)
        self.unet_id = id(unet)
        self.handles = []           # 所有 RemovableHandle（含 forward 包装复原句柄）
        self.refcount = 0           # 当前加载的使用者数量
        self.installed = False      # 是否已安装 hooks
        self._orig_forward = None   # 被包装前的原始 unet.forward


def _get_or_create_controller(unet) -> "_BlockSwapController":
    uid = id(unet)
    ctrl = _CONTROLLER_REGISTRY.get(uid)
    if ctrl is None or ctrl.unet_ref() is None:
        ctrl = _BlockSwapController(unet)
        _CONTROLLER_REGISTRY[uid] = ctrl
    return ctrl


def _is_on_device(module, device) -> bool:
    """判断模块参数是否已经位于目标设备，用于预取去重，避免重复 .to(device)。"""
    try:
        p = next(module.parameters())
    except StopIteration:
        try:
            b = next(module.buffers())
        except StopIteration:
            return True
    return p.device == device


def _install_hooks(unet, controller: "_BlockSwapController"):
    """在共享 UNet 上安装一套通用 hooks（幂等）。hooks 通过 ContextVar 读取本次 forward 配置。"""
    handles = []
    uid = controller.unet_id

    # UNet 顶层 hook：从本次推理的 transformer_options 读取配置，决定 block hooks 是否生效
    def _unet_pre_hook(module, args, kwargs):
        ctrl = _CONTROLLER_REGISTRY.get(uid)
        if ctrl is None:
            return
        to = kwargs.get("transformer_options", {}) if kwargs else {}
        if not isinstance(to, dict):
            to = {}
        cfg = to.get("block_swap_config")
        # 无配置（未经过 Block Swap 节点的共享分支）-> no-op
        token = _EXEC_CONFIG_VAR.set(cfg if cfg is not None else None)
        d = getattr(_thread_local, "tokens", None)
        if d is None:
            d = {}
            _thread_local.tokens = d
        d[uid] = token

    def _unet_post_hook(module, args, kwargs, output):
        ctrl = _CONTROLLER_REGISTRY.get(uid)
        if ctrl is None:
            return
        d = getattr(_thread_local, "tokens", {})
        token = d.pop(uid, None)
        if token is not None:
            try:
                _EXEC_CONFIG_VAR.reset(token)
            except Exception:
                pass

    handles.append(unet.register_forward_pre_hook(_unet_pre_hook, with_kwargs=True))
    handles.append(unet.register_forward_hook(_unet_post_hook, with_kwargs=True))

    # 主 blocks hooks
    for b, block in enumerate(unet.blocks):
        pre, post = _make_block_hooks(uid, b, is_vace=False)
        handles.append(block.register_forward_pre_hook(pre))
        handles.append(block.register_forward_hook(post))

    # VACE blocks hooks
    if hasattr(unet, 'vace_blocks'):
        for b, block in enumerate(unet.vace_blocks):
            pre, post = _make_block_hooks(uid, b, is_vace=True)
            handles.append(block.register_forward_pre_hook(pre))
            handles.append(block.register_forward_hook(post))

    # 包装 unet.forward：实现 embedding 的成对移动与 finally 恢复（仅当前配置开启时生效）
    if not getattr(unet, "_naiba_bs_wrapped", False):
        controller._orig_forward = unet.forward
        unet.forward = types.MethodType(_unet_forward_wrapper, unet)
        unet._naiba_bs_wrapped = True

    controller.handles = handles
    controller.installed = True


def _unet_forward_wrapper(self, *args, **kwargs):
    """
    包装 unet.forward，实现 embedding 的“前向移动到 device_to，结束后移回 offload_device”，
    异常也通过 finally 恢复。仅在当前执行配置开启对应选项时生效（未开启则完全 no-op）。
    """
    to = kwargs.get("transformer_options", {}) if kwargs else {}
    cfg = to.get("block_swap_config") if isinstance(to, dict) else None

    moved = []  # (attr_name, offload_device, use_non_blocking)
    try:
        if cfg:
            dev = cfg.get("main_device")
            off = cfg.get("offload_device")
            nb = cfg.get("use_non_blocking", False)
            if cfg.get("offload_txt_emb") and hasattr(self, "text_embedding"):
                self.text_embedding.to(dev, non_blocking=nb)
                moved.append(("text_embedding", off, nb))
            if cfg.get("offload_img_emb") and hasattr(self, "img_emb"):
                self.img_emb.to(dev, non_blocking=nb)
                moved.append(("img_emb", off, nb))
        return controller_original_forward(self, *args, **kwargs)
    finally:
        # 无论正常结束还是异常，都移回 offload_device
        for name, off, nb in moved:
            mod = getattr(self, name, None)
            if mod is not None:
                try:
                    mod.to(off, non_blocking=nb)
                except Exception:
                    pass
        # 异常路径下确保 ContextVar 也被清理
        d = getattr(_thread_local, "tokens", {})
        token = d.pop(id(self), None)
        if token is not None:
            try:
                _EXEC_CONFIG_VAR.reset(token)
            except Exception:
                pass


def controller_original_forward(self, *args, **kwargs):
    """调用被包装前的原始 unet.forward（由 controller._orig_forward 在 install 时保存的绑定方法）。

    注意：_orig_forward 已是绑定到 unet 的方法，故直接以 *args 调用，不要再传入 self。
    """
    ctrl = _CONTROLLER_REGISTRY.get(id(self))
    if ctrl is not None and ctrl._orig_forward is not None:
        return ctrl._orig_forward(*args, **kwargs)
    # 退化情况：直接调用未包装的 forward
    return torch.nn.Module.forward(self, *args, **kwargs)


def _make_block_hooks(uid: int, block_idx: int, is_vace: bool):
    """生成块级 pre/post hook。通过 ContextVar 读取本次 forward 配置，不闭包引用任何 model_patcher。"""
    def _pre(module, inp):
        cfg = _EXEC_CONFIG_VAR.get()
        if not cfg:
            return  # 无配置 -> 完全 no-op，不影响共享分支

        if is_vace:
            vace_len = _get_vace_length(uid)
            should_swap = (cfg["vace_blocks_to_swap"] > 0 and
                           block_idx >= vace_len - cfg["vace_blocks_to_swap"])
        else:
            should_swap = (cfg["blocks_to_swap"] > 0 and block_idx >= cfg["swap_start_idx"])

        if should_swap:
            dev = cfg["main_device"]
            # 预取去重：仅当尚未在设备上时移动，避免重复 .to(device)
            if not _is_on_device(module, dev):
                module.to(dev, non_blocking=cfg["use_non_blocking"])
            # 预取后续 block（仅主 blocks；仅预取实际会交换的块，且去重）
            if not is_vace and cfg["prefetch_blocks"] > 0:
                unet = _CONTROLLER_REGISTRY.get(uid)
                unet_obj = unet.unet_ref() if unet is not None else None
                if unet_obj is not None:
                    for offset in range(1, cfg["prefetch_blocks"] + 1):
                        prefetch_idx = block_idx + offset
                        if prefetch_idx < len(unet_obj.blocks) and prefetch_idx >= cfg["swap_start_idx"]:
                            pb = unet_obj.blocks[prefetch_idx]
                            if not _is_on_device(pb, dev):
                                pb.to(dev, non_blocking=cfg["use_non_blocking"])

    def _post(module, inp, out):
        cfg = _EXEC_CONFIG_VAR.get()
        if not cfg:
            return

        if is_vace:
            vace_len = _get_vace_length(uid)
            should_swap = (cfg["vace_blocks_to_swap"] > 0 and
                           block_idx >= vace_len - cfg["vace_blocks_to_swap"])
        else:
            should_swap = (cfg["blocks_to_swap"] > 0 and block_idx >= cfg["swap_start_idx"])

        if should_swap:
            off = cfg["offload_device"]
            if not _is_on_device(module, off):
                module.to(off, non_blocking=cfg["use_non_blocking"])

    return _pre, _post


def _get_vace_length(uid: int) -> int:
    """安全地获取当前 UNet 的 vace_blocks 长度（用于判断 VACE 块是否需交换）。"""
    ctrl = _CONTROLLER_REGISTRY.get(uid)
    unet = ctrl.unet_ref() if ctrl is not None else None
    if unet is not None and hasattr(unet, 'vace_blocks'):
        return len(unet.vace_blocks)
    return 0


def ensure_installed(unet, config: dict, device_to, offload_device) -> "_BlockSwapController":
    """幂等地为共享 UNet 安装 hooks。重复调用只更新 config/device 并 +1 引用计数。"""
    with _REGISTRY_LOCK:
        controller = _get_or_create_controller(unet)
        if not controller.installed:
            _install_hooks(unet, controller)
        # 块放置（将冷块放到 offload_device，热块放到 device_to），每次 ON_LOAD 都刷新
        _place_blocks(unet, config, device_to, offload_device)
        controller.refcount += 1
        return controller


def release(unet) -> None:
    """引用计数 -1；归零时移除全部 hooks 并从注册表弹出，释放对 UNet 的引用。"""
    with _REGISTRY_LOCK:
        uid = id(unet)
        ctrl = _CONTROLLER_REGISTRY.get(uid)
        if ctrl is None or ctrl.unet_ref() is None:
            _CONTROLLER_REGISTRY.pop(uid, None)
            return
        if ctrl.refcount > 0:
            ctrl.refcount -= 1
        if ctrl.refcount <= 0:
            # 复原被包装的 unet.forward
            if ctrl._orig_forward is not None and getattr(unet, "_naiba_bs_wrapped", False):
                try:
                    unet.forward = ctrl._orig_forward
                except Exception:
                    pass
                unet._naiba_bs_wrapped = False
            for h in ctrl.handles:
                try:
                    h.remove()
                except Exception:
                    pass
            ctrl.handles = []
            ctrl.installed = False
            _CONTROLLER_REGISTRY.pop(uid, None)


def _place_blocks(unet, config: dict, device_to, offload_device) -> None:
    """根据配置将冷块移动到 offload_device，热块移动到 device_to（幂等放置）。"""
    eff_nb = config.get("use_non_blocking", False)
    blocks_actual = config.get("blocks_to_swap", 0)
    swap_start = config.get("swap_start_idx", 0)
    total = len(unet.blocks)

    if blocks_actual > 0:
        for b, block in tqdm(enumerate(unet.blocks), total=total, desc="Block Swap初始化"):
            if b >= swap_start:
                block.to(offload_device, non_blocking=eff_nb)
            else:
                block.to(device_to, non_blocking=eff_nb)

    vace_actual = config.get("vace_blocks_to_swap", 0)
    if hasattr(unet, 'vace_blocks') and vace_actual > 0:
        total_vace = len(unet.vace_blocks)
        vace_start = total_vace - vace_actual
        for b, block in tqdm(enumerate(unet.vace_blocks), total=total_vace, desc="VACE Block Swap初始化"):
            if b >= vace_start:
                block.to(offload_device, non_blocking=eff_nb)
            else:
                block.to(device_to, non_blocking=eff_nb)


class NaibaWanBlockSwap:
    """
    WAN模型Block Swap节点
    通过将transformer block从GPU交换到CPU内存来减少显存占用
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model": ("MODEL",),
                "blocks_to_swap": ("INT", {
                    "default": 20,
                    "min": 0,
                    "max": 48,
                    "step": 1,
                    "tooltip": "要交换的transformer block数量。14B模型有40个block，1.3B/5B模型有30个block，LongCat-video有48个block"
                }),
            },
            "optional": {
                "offload_img_emb": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "将img_emb卸载到CPU内存（forward前移回device，结束后移回offload_device，异常亦恢复）"
                }),
                "offload_txt_emb": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "将txt_emb卸载到CPU内存（forward前移回device，结束后移回offload_device，异常亦恢复）"
                }),
                "use_non_blocking": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "使用非阻塞内存传输，占用更多RAM但速度更快（非 cuda 设备自动关闭）"
                }),
                "force_fp16_bias": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "已弃用：旧版用于强制将bias转换为float16解决dtype不匹配，现已无害化，保留仅为兼容旧工作流"
                }),
                "vace_blocks_to_swap": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 15,
                    "step": 1,
                    "tooltip": "要交换的VACE block数量。VACE模型有15个block，设为0表示不交换VACE块"
                }),
                "prefetch_blocks": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 40,
                    "step": 1,
                    "tooltip": "预取块数量。在处理当前block时提前加载后续N个block到GPU，可抵消block swap的速度损失，通常设为1-2（非 cuda 设备自动关闭）"
                }),
            },
        }

    RETURN_TYPES = ("MODEL",)
    RETURN_NAMES = ("model",)
    CATEGORY = "naiba-node"
    DESCRIPTION = "WAN模型Block Swap节点，将transformer block在GPU/CPU间交换以降低显存占用"
    SEARCH_ALIASES = ["naiba", "wan", "block swap", "blockswap", "显存优化", "内存优化"]
    FUNCTION = "optimize"

    def optimize(self, model: ModelPatcher, blocks_to_swap: int,
                 offload_img_emb: bool = False, offload_txt_emb: bool = False,
                 use_non_blocking: bool = False, force_fp16_bias: bool = False,
                 vace_blocks_to_swap: int = 0, prefetch_blocks: int = 0):
        """
        应用Block Swap优化
        """
        # 阶段一：保留 force_fp16_bias 以兼容旧工作流，命中 True 时给出弃用提示，但不再修改任何共享参数
        if force_fp16_bias:
            print("[NaibaWanBlockSwap] 警告: force_fp16_bias 已弃用且不再执行任何 dtype 改写，"
                  "以避免破坏共享底层模型参数。该选项将在未来版本移除。")

        # 阶段一：修正提前返回条件（embedding 开关现已安全启用，不应再返回）
        if blocks_to_swap == 0 and vace_blocks_to_swap == 0 and not offload_img_emb and not offload_txt_emb:
            return (model,)

        def swap_blocks_callback(model_patcher: ModelPatcher, device_to, lowvram_model_memory, force_patch_weights, full_load):
            """
            ON_LOAD 回调：只更新设备/config 并做块放置，不再重复安装 hooks。
            """
            if not hasattr(model_patcher.model, 'diffusion_model'):
                print("[NaibaWanBlockSwap] 警告: 模型没有diffusion_model属性，跳过block swap")
                return

            unet = model_patcher.model.diffusion_model

            if not hasattr(unet, 'blocks'):
                print("[NaibaWanBlockSwap] 警告: 模型没有blocks属性，跳过block swap")
                return

            total_blocks = len(unet.blocks)
            print(f"[NaibaWanBlockSwap] 模型共有 {total_blocks} 个transformer block")

            # 阶段一：限制主块交换数量到模型实际数量内
            blocks_to_swap_actual = max(0, min(blocks_to_swap, total_blocks))
            swap_start_idx = total_blocks - blocks_to_swap_actual if blocks_to_swap_actual > 0 else total_blocks

            is_cuda = getattr(device_to, "type", "cpu") == "cuda"

            # 阶段三：非 cuda 设备（CPU / DirectML 等）不支持非阻塞传输与预取，自动关闭
            eff_non_blocking = bool(use_non_blocking) and is_cuda
            prefetch_blocks_actual = max(0, min(prefetch_blocks, blocks_to_swap_actual)) if is_cuda else 0

            # 限制 VACE 块数量到模型实际数量内
            vace_blocks_to_swap_actual = 0
            total_vace_blocks = 0
            if hasattr(unet, 'vace_blocks') and vace_blocks_to_swap > 0:
                total_vace_blocks = len(unet.vace_blocks)
                vace_blocks_to_swap_actual = max(0, min(vace_blocks_to_swap, total_vace_blocks))
                print(f"[NaibaWanBlockSwap] VACE模型有 {total_vace_blocks} 个vace block，将交换 {vace_blocks_to_swap_actual} 个")

            # 阶段二/三：本次推理配置（供 UNet 顶层 hook / ContextVar 注入，block & embedding hooks 按此执行）
            swap_config = {
                "blocks_to_swap": blocks_to_swap_actual,
                "swap_start_idx": swap_start_idx,
                "vace_blocks_to_swap": vace_blocks_to_swap_actual,
                "prefetch_blocks": prefetch_blocks_actual,
                "use_non_blocking": eff_non_blocking,
                "main_device": device_to,
                "offload_device": model_patcher.offload_device,
                "offload_img_emb": offload_img_emb,
                "offload_txt_emb": offload_txt_emb,
            }
            model_patcher.model_options["transformer_options"]["block_swap_config"] = swap_config

            # 阶段二：幂等安装 hooks（同一 UNet 只装一套），并做块放置
            ensure_installed(unet, swap_config, device_to, model_patcher.offload_device)

            comfy.model_management.soft_empty_cache()
            gc.collect()

            print(f"[NaibaWanBlockSwap] Block swap初始化完成，显存占用已优化")

        def cleanup_callback(model_patcher: ModelPatcher):
            """
            ON_CLEANUP 回调：引用计数 -1；最后一个使用者释放时移除 hooks。
            """
            if not hasattr(model_patcher.model, 'diffusion_model'):
                return
            unet = model_patcher.model.diffusion_model
            release(unet)

        # 阶段二：带 key 的 callback，避免同一 patcher 重复添加 ON_LOAD / ON_CLEANUP 回调
        model_clone = model.clone()
        model_clone.remove_callbacks_with_key(CallbacksMP.ON_LOAD, _CALLBACK_KEY)
        model_clone.add_callback_with_key(CallbacksMP.ON_LOAD, _CALLBACK_KEY, swap_blocks_callback)
        model_clone.remove_callbacks_with_key(CallbacksMP.ON_CLEANUP, _CALLBACK_KEY)
        model_clone.add_callback_with_key(CallbacksMP.ON_CLEANUP, _CALLBACK_KEY, cleanup_callback)

        # 立即设置 block_swap_config，这样其他节点可以检测到配置
        model_clone.model_options["transformer_options"]["block_swap_config"] = {
            "blocks_to_swap": blocks_to_swap,
            "vace_blocks_to_swap": vace_blocks_to_swap,
            "prefetch_blocks": prefetch_blocks,
            "use_non_blocking": use_non_blocking,
            "offload_img_emb": offload_img_emb,
            "offload_txt_emb": offload_txt_emb,
            "force_fp16_bias": force_fp16_bias,
            "status": "pending",
        }

        return (model_clone,)


# 注册节点
NODE_CLASS_MAPPINGS = {
    "NaibaWanBlockSwap": NaibaWanBlockSwap
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "NaibaWanBlockSwap": "Naiba WAN Block Swap"
}
