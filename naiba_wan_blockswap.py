"""
NaibaWanBlockSwap - WAN模型Block Swap节点
将transformer block在GPU和CPU之间交换以降低显存占用
完全独立实现，不导入任何内置节点类

阶段二（refactor blockswap hook lifecycle）：
- 新增模块级 _BlockSwapController，集中管理共享 UNet 的 hooks 生命周期
- 每个底层 UNet 只注册一套 hooks（保存所有 RemovableHandle），幂等安装
- 使用弱引用注册表（按 id(unet) 索引）避免 ON_LOAD 重复注册与内存泄漏
- 使用带 key 的 ComfyUI callback，避免同一 patcher 重复添加 ON_LOAD/ON_CLEANUP 回调
- hooks 不再闭包引用 model_patcher，改由 UNet 顶层 forward_pre_hook 从本次推理的
  transformer_options["block_swap_config"] 读取配置并写入 controller
- 未经过 Block Swap 节点的共享分支没有配置时，active_config 为 None，hooks 完全 no-op
- 增加 ON_CLEANUP 处理与引用计数；最后一个使用者释放时移除全部 hooks
- ON_LOAD 只更新设备/config 并做块放置，不再重复安装 hooks

（阶段一的 dtype/device 修复、embedding 卸载禁用仍然保留，embedding 恢复在阶段三）
"""

import comfy.model_management
import gc
import threading
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


class _BlockSwapController:
    """集中管理某个共享 UNet 的 block swap hooks 与引用计数（幂等安装）。"""

    __slots__ = ("unet_ref", "unet_id", "handles", "refcount", "active_config", "installed")

    def __init__(self, unet):
        self.unet_ref = weakref.ref(unet)
        self.unet_id = id(unet)
        self.handles = []           # 所有 RemovableHandle
        self.refcount = 0           # 当前加载的使用者数量
        self.active_config = None   # 本次 forward 生效的配置（None 表示 no-op）
        self.installed = False      # 是否已安装 hooks

    def set_active_config(self, config):
        self.active_config = config

    def clear_active_config(self):
        self.active_config = None

    def get_active_config(self):
        return self.active_config


def _get_or_create_controller(unet) -> "_BlockSwapController":
    uid = id(unet)
    ctrl = _CONTROLLER_REGISTRY.get(uid)
    if ctrl is None or ctrl.unet_ref() is None:
        ctrl = _BlockSwapController(unet)
        _CONTROLLER_REGISTRY[uid] = ctrl
    return ctrl


def _install_hooks(unet, controller: "_BlockSwapController"):
    """在共享 UNet 上安装一套通用 hooks（幂等）。hooks 通过注册表读取本次 forward 配置。"""
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
        ctrl.set_active_config(cfg if cfg is not None else None)

    def _unet_post_hook(module, args, kwargs, output):
        ctrl = _CONTROLLER_REGISTRY.get(uid)
        if ctrl is not None:
            ctrl.clear_active_config()

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

    controller.handles = handles
    controller.installed = True


def _make_block_hooks(uid: int, block_idx: int, is_vace: bool):
    """生成块级 pre/post hook。通过注册表读取 active_config，不闭包引用任何 model_patcher。"""
    def _pre(module, inp):
        ctrl = _CONTROLLER_REGISTRY.get(uid)
        if ctrl is None:
            return
        cfg = ctrl.get_active_config()
        if not cfg:
            return  # 无配置 -> 完全 no-op，不影响共享分支

        if is_vace:
            vace_len = _get_vace_length(ctrl)
            should_swap = (cfg["vace_blocks_to_swap"] > 0 and
                           block_idx >= vace_len - cfg["vace_blocks_to_swap"])
        else:
            should_swap = (cfg["blocks_to_swap"] > 0 and block_idx >= cfg["swap_start_idx"])

        if should_swap:
            module.to(cfg["main_device"], non_blocking=cfg["use_non_blocking"])
            # 预取后续 block（仅主 blocks）
            if not is_vace and cfg["prefetch_blocks"] > 0:
                unet = ctrl.unet_ref()
                if unet is not None:
                    for offset in range(1, cfg["prefetch_blocks"] + 1):
                        prefetch_idx = block_idx + offset
                        if prefetch_idx < len(unet.blocks) and prefetch_idx >= cfg["swap_start_idx"]:
                            unet.blocks[prefetch_idx].to(cfg["main_device"], non_blocking=cfg["use_non_blocking"])

    def _post(module, inp, out):
        ctrl = _CONTROLLER_REGISTRY.get(uid)
        if ctrl is None:
            return
        cfg = ctrl.get_active_config()
        if not cfg:
            return

        if is_vace:
            vace_len = _get_vace_length(ctrl)
            should_swap = (cfg["vace_blocks_to_swap"] > 0 and
                           block_idx >= vace_len - cfg["vace_blocks_to_swap"])
        else:
            should_swap = (cfg["blocks_to_swap"] > 0 and block_idx >= cfg["swap_start_idx"])

        if should_swap:
            module.to(cfg["offload_device"], non_blocking=cfg["use_non_blocking"])

    return _pre, _post


def _get_vace_length(ctrl: "_BlockSwapController") -> int:
    """安全地获取当前 UNet 的 vace_blocks 长度（用于判断 VACE 块是否需交换）。"""
    unet = ctrl.unet_ref()
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
            for h in ctrl.handles:
                try:
                    h.remove()
                except Exception:
                    pass
            ctrl.handles = []
            ctrl.installed = False
            ctrl.clear_active_config()
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
                    "tooltip": "将img_emb卸载到CPU内存（阶段一暂不安全，已禁用）"
                }),
                "offload_txt_emb": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "将txt_emb卸载到CPU内存（阶段一暂不安全，已禁用）"
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
                    "tooltip": "预取块数量。在处理当前block时提前加载后续N个block到GPU，可抵消block swap的速度损失，通常设为1-2"
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

        # 阶段一：embedding 直接卸载暂不安全，开启时给出明确警告并忽略
        if offload_img_emb or offload_txt_emb:
            print("[NaibaWanBlockSwap] 警告: embedding offload（offload_img_emb / offload_txt_emb）"
                  "在当前版本不安全已被禁用，将不会影响共享分支。计划于后续阶段恢复安全的往返卸载。")

        # 阶段一：修正提前返回条件
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

            # 非 cuda 设备不支持非阻塞传输，强制关闭
            eff_non_blocking = bool(use_non_blocking) and (getattr(device_to, "type", "cpu") == "cuda")

            # 限制预取数量到实际可交换的主块数量内
            prefetch_blocks_actual = max(0, min(prefetch_blocks, blocks_to_swap_actual))

            # 限制 VACE 块数量到模型实际数量内
            vace_blocks_to_swap_actual = 0
            total_vace_blocks = 0
            vace_swap_start_idx = 0
            if hasattr(unet, 'vace_blocks') and vace_blocks_to_swap > 0:
                total_vace_blocks = len(unet.vace_blocks)
                vace_blocks_to_swap_actual = max(0, min(vace_blocks_to_swap, total_vace_blocks))
                vace_swap_start_idx = total_vace_blocks - vace_blocks_to_swap_actual
                print(f"[NaibaWanBlockSwap] VACE模型有 {total_vace_blocks} 个vace block，将交换 {vace_blocks_to_swap_actual} 个")

            # 阶段二：本次推理配置（供 UNet 顶层 hook 注入，block hooks 按此执行）
            swap_config = {
                "blocks_to_swap": blocks_to_swap_actual,
                "swap_start_idx": swap_start_idx,
                "vace_blocks_to_swap": vace_blocks_to_swap_actual,
                "vace_swap_start_idx": vace_swap_start_idx,
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
