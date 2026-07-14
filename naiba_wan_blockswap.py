"""
NaibaWanBlockSwap - WAN模型Block Swap节点
将transformer block在GPU和CPU之间交换以降低显存占用
完全独立实现，不导入任何内置节点类
"""

import comfy.model_management
import gc
import torch
from comfy.patcher_extension import CallbacksMP
from comfy.model_patcher import ModelPatcher
from tqdm import tqdm


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
                    "tooltip": "将img_emb卸载到CPU内存"
                }),
                "offload_txt_emb": ("BOOLEAN", {
                    "default": False, 
                    "tooltip": "将txt_emb卸载到CPU内存"
                }),
                "use_non_blocking": ("BOOLEAN", {
                    "default": False, 
                    "tooltip": "使用非阻塞内存传输，占用更多RAM但速度更快"
                }),
                "force_fp16_bias": ("BOOLEAN", {
                    "default": True, 
                    "tooltip": "强制将bias转换为float16，解决mxfp8量化的dtype不匹配错误"
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
                 use_non_blocking: bool = False, force_fp16_bias: bool = True,
                 vace_blocks_to_swap: int = 0, prefetch_blocks: int = 0):
        """
        应用Block Swap优化
        
        Args:
            model: 输入的MODEL
            blocks_to_swap: 要交换的block数量
            offload_img_emb: 是否卸载img_emb
            offload_txt_emb: 是否卸载txt_emb
            use_non_blocking: 是否使用非阻塞传输
            force_fp16_bias: 是否强制将bias转换为float16
            vace_blocks_to_swap: 要交换的VACE block数量
            prefetch_blocks: 预取块数量，提前加载后续N个block到GPU
            
        Returns:
            优化后的MODEL
        """
        # 如果不需要交换，直接返回
        if blocks_to_swap == 0:
            return (model,)
        
        def swap_blocks_callback(model_patcher: ModelPatcher, device_to, lowvram_model_memory, force_patch_weights, full_load):
            """
            ON_LOAD回调函数，在模型加载到GPU时执行block swap和forward hooks注册
            """
            base_model = model_patcher.model
            main_device = torch.device('cuda')
            
            # 检查模型是否有diffusion_model和blocks属性
            if not hasattr(base_model, 'diffusion_model'):
                print("[NaibaWanBlockSwap] 警告: 模型没有diffusion_model属性，跳过block swap")
                return
            
            unet = base_model.diffusion_model
            
            if not hasattr(unet, 'blocks'):
                print("[NaibaWanBlockSwap] 警告: 模型没有blocks属性，跳过block swap")
                return
            
            # 获取block总数
            total_blocks = len(unet.blocks)
            print(f"[NaibaWanBlockSwap] 模型共有 {total_blocks} 个transformer block")
            
            # 限制blocks_to_swap的范围
            blocks_to_swap_actual = min(blocks_to_swap, total_blocks)
            
            # 计算交换起始索引：前swap_start_idx个block留在GPU，后面的交换到CPU
            swap_start_idx = total_blocks - blocks_to_swap_actual if blocks_to_swap_actual > 0 else total_blocks
            
            # 存储交换配置供forward hooks使用
            swap_config = {
                "blocks_to_swap": blocks_to_swap_actual,
                "swap_start_idx": swap_start_idx,
                "vace_blocks_to_swap": vace_blocks_to_swap,
                "prefetch_blocks": prefetch_blocks,
                "use_non_blocking": use_non_blocking,
                "main_device": main_device,
                "offload_device": model_patcher.offload_device,
                "force_fp16_bias": force_fp16_bias,
                "vace_hooks_registered": False,
                "block_hooks_registered": False,
            }
            model_patcher.model_options["transformer_options"]["block_swap_config"] = swap_config
            
            # 强制将bias转换为float16的辅助函数
            def force_fp16_bias_for_block(block):
                if force_fp16_bias:
                    for name, param in block.named_parameters():
                        if 'bias' in name and param.dtype == torch.bfloat16:
                            param.data = param.data.to(torch.float16)
                    for name, buf in block.named_buffers():
                        if 'bias' in name and buf.dtype == torch.bfloat16:
                            buf.data = buf.data.to(torch.float16)
            
            # 初始化主blocks：将需要交换的block移到CPU
            if blocks_to_swap_actual > 0:
                print(f"[NaibaWanBlockSwap] 将 {blocks_to_swap_actual} 个block移到CPU内存 (从索引{swap_start_idx}开始)")
                
                for b, block in tqdm(enumerate(unet.blocks), total=total_blocks, desc="Block Swap初始化"):
                    force_fp16_bias_for_block(block)
                    
                    if b >= swap_start_idx:
                        # 将block移到CPU（offload_device）
                        block.to(model_patcher.offload_device, non_blocking=use_non_blocking)
                    else:
                        # 将block留在GPU
                        block.to(main_device, non_blocking=use_non_blocking)
            
            # 初始化VACE blocks（如果有）
            has_vace = hasattr(unet, 'vace_blocks')
            if has_vace and vace_blocks_to_swap > 0:
                total_vace_blocks = len(unet.vace_blocks)
                vace_swap_start_idx = total_vace_blocks - vace_blocks_to_swap
                
                print(f"[NaibaWanBlockSwap] VACE模型有 {total_vace_blocks} 个vace block，将交换 {vace_blocks_to_swap} 个")
                
                for b, block in tqdm(enumerate(unet.vace_blocks), total=total_vace_blocks, desc="VACE Block Swap初始化"):
                    force_fp16_bias_for_block(block)
                    
                    if b >= vace_swap_start_idx:
                        block.to(model_patcher.offload_device, non_blocking=use_non_blocking)
                    else:
                        block.to(main_device, non_blocking=use_non_blocking)
            
            # 注册forward hooks函数
            def create_block_hook(block_idx, is_vace=False):
                """为指定block创建forward hooks"""
                def pre_hook(module, input):
                    """在block执行前将其移到GPU，并预取后续block"""
                    config = model_patcher.model_options["transformer_options"]["block_swap_config"]
                    
                    # 判断当前block是否需要动态交换
                    if is_vace:
                        should_swap = (config["vace_blocks_to_swap"] > 0 and 
                                      block_idx >= len(unet.vace_blocks) - config["vace_blocks_to_swap"])
                    else:
                        should_swap = (config["blocks_to_swap"] > 0 and 
                                      block_idx >= config["swap_start_idx"])
                    
                    if should_swap:
                        # 将当前block移到GPU
                        module.to(config["main_device"], non_blocking=config["use_non_blocking"])
                        
                        # 预取后续block到GPU（仅对主blocks实现预取）
                        if not is_vace and config["prefetch_blocks"] > 0:
                            for offset in range(1, config["prefetch_blocks"] + 1):
                                prefetch_idx = block_idx + offset
                                if prefetch_idx < len(unet.blocks) and prefetch_idx >= config["swap_start_idx"]:
                                    unet.blocks[prefetch_idx].to(config["main_device"], non_blocking=config["use_non_blocking"])
                
                def post_hook(module, input, output):
                    """在block执行后将其移回CPU"""
                    config = model_patcher.model_options["transformer_options"]["block_swap_config"]
                    
                    # 判断当前block是否需要动态交换
                    if is_vace:
                        should_swap = (config["vace_blocks_to_swap"] > 0 and 
                                      block_idx >= len(unet.vace_blocks) - config["vace_blocks_to_swap"])
                    else:
                        should_swap = (config["blocks_to_swap"] > 0 and 
                                      block_idx >= config["swap_start_idx"])
                    
                    if should_swap:
                        # 将当前block移回CPU
                        module.to(config["offload_device"], non_blocking=config["use_non_blocking"])
                
                return pre_hook, post_hook
            
            # 为主blocks注册forward hooks
            if blocks_to_swap_actual > 0:
                print(f"[NaibaWanBlockSwap] 为 {total_blocks} 个主block注册forward hooks")
                
                for b, block in enumerate(unet.blocks):
                    pre_hook, post_hook = create_block_hook(b, is_vace=False)
                    block.register_forward_pre_hook(pre_hook)
                    block.register_forward_hook(post_hook)
                
                swap_config["block_hooks_registered"] = True
            
            # 为VACE blocks注册forward hooks
            if has_vace and vace_blocks_to_swap > 0:
                total_vace_blocks = len(unet.vace_blocks)
                print(f"[NaibaWanBlockSwap] 为 {total_vace_blocks} 个VACE block注册forward hooks")
                
                for b, block in enumerate(unet.vace_blocks):
                    pre_hook, post_hook = create_block_hook(b, is_vace=True)
                    block.register_forward_pre_hook(pre_hook)
                    block.register_forward_hook(post_hook)
                
                swap_config["vace_hooks_registered"] = True
            
            # 卸载text_embedding
            if offload_txt_emb and hasattr(unet, 'text_embedding'):
                print("[NaibaWanBlockSwap] 卸载text_embedding到CPU")
                unet.text_embedding.to(model_patcher.offload_device, non_blocking=use_non_blocking)
            
            # 卸载img_emb
            if offload_img_emb and hasattr(unet, 'img_emb'):
                print("[NaibaWanBlockSwap] 卸载img_emb到CPU")
                unet.img_emb.to(model_patcher.offload_device, non_blocking=use_non_blocking)
            
            # 清理缓存
            comfy.model_management.soft_empty_cache()
            gc.collect()
            
            print(f"[NaibaWanBlockSwap] Block swap初始化完成，显存占用已优化")
        
        # 克隆模型并添加回调
        model_clone = model.clone()
        model_clone.add_callback(CallbacksMP.ON_LOAD, swap_blocks_callback)
        
        # 立即设置block_swap_config，这样其他节点可以检测到配置
        # 注意：实际的block交换会在ON_LOAD回调中执行
        model_clone.model_options["transformer_options"]["block_swap_config"] = {
            "blocks_to_swap": blocks_to_swap,
            "vace_blocks_to_swap": vace_blocks_to_swap,
            "prefetch_blocks": prefetch_blocks,
            "use_non_blocking": use_non_blocking,
            "offload_img_emb": offload_img_emb,
            "offload_txt_emb": offload_txt_emb,
            "force_fp16_bias": force_fp16_bias,
            "status": "pending",  # 标记配置已设置但尚未执行
        }
        
        return (model_clone,)


# 注册节点
NODE_CLASS_MAPPINGS = {
    "NaibaWanBlockSwap": NaibaWanBlockSwap
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "NaibaWanBlockSwap": "Naiba WAN Block Swap"
}