"""
Naiba Qwen 提示词工作台
用 models/LLM 下的 GGUF 语言模型(搭配 mmproj 视觉模型)把口语化需求改写成
Qwen Image 2.1 可直接使用的长提示词。三种模式自动判定:
- 无图像输入            -> 文生图(T2I 模板快照,输出 rewritten_prompt/wh_ratio)
- 有图像 + 有提示词     -> 图片编辑(EDIT 模板快照,额外输出 ratio_follow)
- 有图像 + 无提示词     -> 反推(T2I 模板 + 反推补充规则)
前端 UI 见 js/naiba_qwen_prompt_optimizer.js。运行依赖 llama-cpp-python>=0.3.48
(JamePeng fork,提供 Qwen35ChatHandler),未就绪时节点横幅可一键安装。
"""

from __future__ import annotations

import asyncio
import base64
import gc
import importlib.metadata
import importlib.util
import inspect
import io
import json
import os
import platform
import re
import subprocess
import sys
import urllib.request
import zlib
from pathlib import Path

import folder_paths
import numpy as np
import torch
from aiohttp import web
from comfy_api.latest import io as comfy_io
from PIL import Image
from server import PromptServer

try:
    import comfy.model_management as model_management
except ImportError:
    model_management = None

try:
    from llama_cpp import Llama
    from llama_cpp.llama_chat_format import Qwen35ChatHandler
except (ImportError, OSError, RuntimeError, AttributeError) as exc:
    Llama = None
    Qwen35ChatHandler = None
    _LLAMA_ERROR = exc


def _register_llm_folder() -> None:
    """确保 models/LLM(含小写变体)成为 .gguf 模型目录。"""
    if "LLM" in folder_paths.folder_names_and_paths:
        return
    models_dir = Path(folder_paths.models_dir)
    roots = [str(models_dir / "LLM"), str(models_dir / "llm")]
    folder_paths.folder_names_and_paths["LLM"] = (roots, {".gguf"})


_register_llm_folder()


# ---------------------------------------------------------------- 依赖管理

_LLAMA_MIN = (0, 3, 48)
_LLAMA_RELEASES = "https://github.com/JamePeng/llama-cpp-python/releases"
_LLAMA_RELEASES_API = "https://api.github.com/repos/JamePeng/llama-cpp-python/releases?per_page=100"
_INSTALL_LOCK = asyncio.Lock()


def _version_tuple(text: str) -> tuple[int, int, int]:
    match = re.match(r"(\d+)\.(\d+)\.(\d+)", str(text or ""))
    return tuple(map(int, match.groups())) if match else (0, 0, 0)


def _wheel_spec() -> dict | None:
    """按当前 系统/Python/CUDA 组合推算官方 wheel 的筛选条件。"""
    system, machine = platform.system(), platform.machine().casefold()
    py_tag = f"cp{sys.version_info.major}{sys.version_info.minor}"
    if system == "Darwin" and machine in ("arm64", "aarch64"):
        return {"marker": "-metal-macos-", "suffix": f"-{py_tag}-{py_tag}-macosx_11_0_arm64.whl", "backend": "metal"}
    if system == "Windows" and machine in ("amd64", "x86_64"):
        marker, platform_tag = "-win-", "win_amd64"
    elif system == "Linux" and machine in ("amd64", "x86_64"):
        marker, platform_tag = "-linux-", "linux_x86_64"
    else:
        return None
    cuda = str(torch.version.cuda or "")
    cuda_match = re.match(r"(\d+)\.(\d+)", cuda)
    if not cuda_match:
        return None
    backend = f"cu{cuda_match.group(1)}{cuda_match.group(2)}"
    return {
        "marker": f"-{backend}{marker}",
        "suffix": f"-{py_tag}-{py_tag}-{platform_tag}.whl",
        "backend": backend,
    }


def llama_dependency_status() -> dict:
    try:
        version = importlib.metadata.version("llama-cpp-python")
    except importlib.metadata.PackageNotFoundError:
        version = ""
    problems: list[str] = []
    if Llama is None:
        problems.append(f"llama-cpp-python 不可用：{_LLAMA_ERROR}")
    if Qwen35ChatHandler is None:
        problems.append("当前 llama-cpp-python 缺少 Qwen35ChatHandler")
    if not version:
        problems.append("未安装 llama-cpp-python")
    elif _version_tuple(version) < _LLAMA_MIN:
        problems.append(f"llama-cpp-python 版本过旧：{version}")
    if importlib.util.find_spec("diskcache") is None:
        problems.append("缺少 diskcache")
    status: dict = {
        "installed_version": version or None,
        "needs_install": bool(problems),
        "reason": "；".join(problems) or "依赖可用",
        "minimum_version": "0.3.48",
        "release_url": _LLAMA_RELEASES,
    }
    spec = _wheel_spec()
    status["supported"] = spec is not None
    if spec is not None:
        status["backend"] = spec["backend"]
    return status


def _pick_wheel(spec: dict) -> tuple[str, str]:
    request = urllib.request.Request(
        _LLAMA_RELEASES_API,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "naiba-test"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        releases = json.load(response)
    marker = spec["marker"].casefold()
    suffix = spec["suffix"].casefold()
    for release in releases:
        if release.get("draft") or release.get("prerelease"):
            continue
        if marker not in str(release.get("tag_name", "")).casefold():
            continue
        for asset in release.get("assets", []):
            name = str(asset.get("name", ""))
            url = str(asset.get("browser_download_url", ""))
            if name.casefold().endswith(suffix) and url.startswith("https://github.com/JamePeng/llama-cpp-python/releases/download/"):
                return url, name
    raise RuntimeError("发布页没有匹配当前系统/Python/CUDA 的 wheel。")


def install_llama() -> dict:
    spec = _wheel_spec()
    if spec is None:
        raise RuntimeError("当前系统/Python/CUDA 组合没有可自动安装的 wheel，请按发布页说明手动安装。")
    wheel_url, wheel_name = _pick_wheel(spec)
    done = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--no-input", "--disable-pip-version-check",
         "--upgrade", "diskcache", wheel_url],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=900,
    )
    if done.returncode != 0:
        tail = "\n".join(part for part in (done.stdout, done.stderr) if part.strip())[-2000:]
        raise RuntimeError(f"pip 安装失败（退出码 {done.returncode}）：\n{tail}")

    return {"success": True, "wheel": wheel_name, "message": "llama-cpp-python 安装完成，请完全重启 ComfyUI 后使用。"}


@PromptServer.instance.routes.get("/naiba/qwen_prompt_optimizer/llama_status")
async def _llama_status_route(_request):
    return web.json_response(llama_dependency_status())


@PromptServer.instance.routes.post("/naiba/qwen_prompt_optimizer/install_llama")
async def _llama_install_route(request):
    try:
        payload = await request.json()
    except Exception:
        payload = {}
    if payload.get("confirm") is not True:
        return web.json_response({"success": False, "message": "安装请求缺少用户确认。"}, status=400)
    if _INSTALL_LOCK.locked():
        return web.json_response({"success": False, "message": "安装任务正在进行。"}, status=409)
    async with _INSTALL_LOCK:
        try:
            return web.json_response(await asyncio.to_thread(install_llama))
        except Exception as error:
            return web.json_response(
                {"success": False, "message": str(error), "release_url": _LLAMA_RELEASES},
                status=500,
            )


# ---------------------------------------------------------------- 模型选择

def _model_choices() -> tuple[list[str], list[str]]:
    names = folder_paths.get_filename_list("LLM")
    main = [n for n in names if "mmproj" not in n.casefold()]
    vision = [n for n in names if "mmproj" in n.casefold()]
    return (main or ["未找到 GGUF 模型"], vision or ["未找到 mmproj GGUF 模型"])


def _prefer(names: list[str], keyword: str) -> str:
    return next((n for n in names if keyword.casefold() in n.casefold()), names[0])


def _model_path(display: str, expect_mmproj: bool) -> str:
    path = folder_paths.get_full_path("LLM", display)
    if path is None:
        raise ValueError(f"找不到所选模型：{display}")
    resolved = os.path.realpath(path)
    contained = False
    for root in folder_paths.get_folder_paths("LLM"):
        root = os.path.realpath(root)
        try:
            contained = os.path.commonpath([root, resolved]) == root
        except ValueError:
            continue
        if contained:
            break
    if not contained or Path(resolved).suffix.casefold() != ".gguf":
        raise ValueError(f"模型路径不在 LLM 目录内或不是 GGUF：{display}")
    if ("mmproj" in Path(display).name.casefold()) != bool(expect_mmproj):
        raise ValueError(f"模型类型不符：{display}")
    return resolved


# ---------------------------------------------------------------- 节点

class NaibaQwenPromptOptimizer(comfy_io.ComfyNode):
    @classmethod
    def define_schema(cls):
        main, vision = _model_choices()
        return comfy_io.Schema(
            node_id="NaibaQwenPromptOptimizer",
            display_name="Naiba Qwen 提示词工作台",
            category="naiba-node",
            description=(
                "无图=文生图；有图+有提示词=图片编辑；有图+无提示词=反推。模型仅在单次执行期间加载。"
            ),
            inputs=[
                comfy_io.String.Input("用户提示词", default="", multiline=True, dynamic_prompts=False),
                comfy_io.Combo.Input("文生图模型", options=main, default=_prefer(main, "PE-T2I")),
                comfy_io.Combo.Input("图生图模型", options=main, default=_prefer(main, "PE-I2I")),
                comfy_io.Combo.Input("视觉模型", options=vision, default=_prefer(vision, "PE-I2I")),
                comfy_io.Combo.Input("输出语言", options=["自动", "中文", "English"], default="自动"),
                comfy_io.Boolean.Input("透明背景", default=False),
                comfy_io.Int.Input(
                    "种子值", default=0, min=0, max=0xFFFFFFFF,
                    control_after_generate=comfy_io.ControlAfterGenerate.fixed,
                ),
                comfy_io.Autogrow.Input(
                    "图像",
                    template=comfy_io.Autogrow.TemplatePrefix(comfy_io.Image.Input("image"), prefix="图像_", min=0, max=100),
                    optional=True,
                ),
            ],
            outputs=[
                comfy_io.String.Output("prompt"),
                comfy_io.String.Output("json"),
                comfy_io.Boolean.Output("是否反推"),
            ],
            hidden=[],
        )

    SEARCH_ALIASES = ["naiba", "qwen", "prompt", "optimizer", "提示词", "优化", "反推", "工作台"]

    @classmethod
    def execute(
        cls, 用户提示词, 文生图模型, 图生图模型, 视觉模型, 输出语言, 透明背景,
        种子值, 图像: comfy_io.Autogrow.Type = None, **kwargs,
    ) -> comfy_io.NodeOutput:
        images = collect_images(图像 or kwargs)
        has_images = bool(images)
        text = str(用户提示词 or "").strip()
        reverse_mode = has_images and not text
        edit_mode = has_images and not reverse_mode
        base_prompt = reverse_prompt() if reverse_mode else edit_prompt() if has_images else t2i_prompt()
        language = select_language(输出语言, text, reverse_mode)
        system_prompt = build_system_prompt(base_prompt, language, bool(透明背景), reverse_mode)
        user_prompt = build_user_turn(text, images, language, bool(透明背景), reverse_mode)
        fields = complete(
            model_path=_model_path(图生图模型 if edit_mode else 文生图模型, expect_mmproj=False),
            mmproj_path=_model_path(视觉模型, expect_mmproj=True) if has_images else None,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            images=images,
            edit_mode=edit_mode,
            seed=max(0, min(0xFFFFFFFF, int(种子值))),
        )
        prompt_text = append_transparency(fields["rewritten_prompt"], bool(透明背景))
        fields["rewritten_prompt"] = prompt_text
        return comfy_io.NodeOutput(prompt_text, json.dumps(fields, ensure_ascii=False, separators=(",", ":")), reverse_mode)


NODE_CLASS_MAPPINGS = {
    "NaibaQwenPromptOptimizer": NaibaQwenPromptOptimizer,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "NaibaQwenPromptOptimizer": "Naiba Qwen 提示词工作台",
}


# Embedded prompt snapshots; exact upstream equality has not been verified.
# T2I: https://huggingface.co/Qwen/Qwen-Image-2.1-PE-T2I/blob/f3ed7985c788ad75b3ab7223e0c4c51e2a43545b/system_prompt.txt
# I2I: https://huggingface.co/Qwen/Qwen-Image-2.1-PE-I2I/blob/72927bc08afc99b7888ceb7d7d51a12db3700bbd/system_prompt.txt
# Upstream templates: Qwen Research License Agreement. Reverse rules are project-authored.
_T2I = (
    "c-n1R+m7VMk$umvNR%D~4A>>iMY7#m7#LZz>#+>YK%<4QPwp%-t18tblgcE!y1ZDxAK`bu8M|Mw@B1nGl07FP$zt^kAZVIoU"
    "Lxai;zVS9X5V)1;O+YqyJ56H_)`jF=nwYI<KWY1%zwnmj#KKbvs3oz^K64mNdA|}=h23Kj5hY(wvn^?LmTqZ4lcPva>LP%M>"
    "pEW=Q@R*&v^7^A9{@OO<Bod$-O;epOa5qC*D&4ObcUWhjx-#7&iENw8@Pj;)~74IJJ%4d6RtKU}l3UTT6Kzmg(bYN7u?ykdP"
    "}-e(U<?={IM~3h7qFz;xq!8+RE0fGNojF^N)6JWPPRy)3v-uJc=Cev0WHFH)QiNBQ8x;Rp#wKV%5l#uI16ggv(QjjNCH$=0#"
    "!!k9&SjjuxvvH#k(ZuH6M+}`W{4<SPVz4b1&0dFt^+kW<${lIme+h70ocbLvKviU9rzn637p$*ic$a{*${5im4a)?DAN2q@v"
    "9;rRdn7^Iz{sFe|`_ab1_t@=UIjE9RSh1V1Ql8R7z%cOvXf72)4=_=0r@lVA{@|Ni%VV5z=tL#Py&e7IXk?p{>&29(zAB@7="
    "(K_Ie}=W^cXgcl<spyIP=j|ZcD#ORhL{64S2;g+o4p?Hz{63A_78D5^Ib?HRFN@Th@M<cOYCF1JXOW?7!HxG9+ofbc4~OI0j"
    "C}(Ckjv#xEk-Fzt@--5`_}CqZploC{!T54sHbthaM74wa(wgNiFqr-0=iQ*bDKr`eKHF?cnb8fDH_4n>g)SZ-1HM=<}wsn?A"
    "ypsk!kDOksCztncOhtM4iV0{(+<@ws#No)-18t|$W{Wy~EmTl-`2e1=XP`_cD^wRbxlf}t2%Jh!mskr9kHZh-6gtkEV;?CWD"
    "RVZ4>|tldN`mp>U=RhcW_#N&26pg8|Kc%@pI%9D?bp@!QRhg)g72^#es<iw_1OKT+WZ%&BH8Osb;bLGQv>KkCn)d0JT;}J3-"
    "aN$^2r-<TNHbZKt<F61s16T|^JB=kGJMa2D0}RgjKv^JQ7qN1gKOY;S&OqGyoL9mALQIWdyo@*ITRl17MC{d%>VSKIx{5WGa"
    "Kb}x;WPL0T7m*=zujN(pqRty$BHkZQP`T^cY?3n+PjyxFYYYk!u3VTIA-`O+`_dqiMe}m`|`;M7-S4JzEgaxML<(uBQ!ymdp"
    "EVCdQ2T@b<vBY2%P`lG5+rP?ens#&A&{XzH{(u#9u8T-|nWaOva#$Z4n7I)WPK7JH$m-VU@3Le|KkenG@B90QDVCTXWWsAlg"
    "NNVh(JK1LNb}?{1%eHH$DD3EXf2?+Na(Hjdv?fxSS%&h<S3AL@E_hecjMdj9hq+vDF?P*KGdUp&{xFZs_)9rPuq80-r*`bVP"
    "n4gnu~jj?`hRBpXkFL{Unyu|;rh>0&9Ed1kaZQBBGvaVD@?e28^i+sbuf^VCx{a&LE4(KnAz$}?#J1M-zWS{}0gjT^>bHLNs"
    "Mt1Y<e&xL{#r!|X%HpkvV(N-2_k9glen*{_Cv1wGN+3Vs4UUdj%n*-3#@R>|Vd^T?#&~Xhb?xmX2bi6!?+>~XE$mu9j{a+CY"
    "!Yqt^Lp#p8DqRP=8lR}nnHZGzy9OD7f1d=z2}SB7r!8<Xn+03|8SIuQ~rjdj8WOp|NXB;ib5jcU!euJ8I$gZ=L}c%IwavWV3"
    "dRUz0QSu;<0XH_BYeOzgMpZO32SZdRgk|y-aW8AyN$B3#C%c;6=qpVG9@CXll>1f-q`(Cn_K;%jy62PYDBuSvc_B>q}JA@!+"
    "PAW_4O_$|)!EBS5HV`{dh}`NSJFAHZ(vxxQEc3IKN;l{SW%0Y&g6r1#>;qFZqWdx&smNjmhaMTknJSUq>(oSi&Xb`Oem^8h`"
    ">RGB6CD{v7QW~LP(1LQ#l@E&4fXmD+XOxia$O>(3wFTcH+nP-Kq#}w5yk>zlX+KXIYYkESWX9AqL7!E;0u04MhB(LN!ZzVxQ"
    "aGRY+Br8dfm^9`aeFJa>O5%?p!7Gq*V76BAlqY4{cq8n{1NpF+YV`!aV}b^m#M#J3PXTES;oQ2~UnSsMJ7HY9ArGvKtFevRX"
    "^aCfpp10D9TMJ|9Kq?p<Zp!TEbkPC<q>JAXU40{&LcNq%sAEetOsTcsbdo8B$*d+drt%xR*fNhSZE~b<_XfzoX@ppI3|~Uu4"
    "aNnq&yFF(DuB*!CBctlA~XC%L*Q(NqIpIm0Ii}%!dIBe=KL}LesQ<(ee;H^jGNZO4mCQ=|dnbD-#7#L>G`kl7$ur7a#aiff7"
    "Z^I?sQPN@A|1iZ7L_;wJ#XQ6De@sM-+Zk(W=G`HZJM1d>2{_U!Hc`co4gfM>-D2?EDHKYJ!}xPn^D0)vPyR26UbPGA~U3*3{"
    "CYXlS(%EYfSBNzxFG(h+r1m~is`EX?~!0mGZhNqaMm@Zo>+mxEA5D5rQI>xe;c!CfH#<=|`RM{JAKguymuSyLBMQzOs-4;&G"
    "q>Xyz2&=RJhD!dzQai><zK0XlKH$rt5>l$*RM*oG{1O=ALR<54YrkcUAf)mVIlI`Luh`zLR#_QpEBtH@6?sTnO5*F5hxs>_3"
    "*xz|H9<_~dBpsDK*as4qR2Ropn!U)eT-s4LWgR%vPH{?d>(d(;IS#5X7><&Q&<KaCtsvqIfmvcI>DTr_;+DnTE{K+Hf!R-S_"
    "kUYlHiHW>9_<I*n2NzChqq|BdaAo&vZ<0v~(@C2RuTMta(yP$Yk16Hc-cvcVZI06TKc>608KnDNa|0%@xWK97$9jfj)GsFs?"
    "?3OQ7r~5M!{|cJ{SKsO)zh@jVInU!cnt=%P|)DnILq$}2~?!0~m(P>@v7SKLXuBNDOFm|0+1q>v?ZT*W_F>lxC<+Kp}}nDzs"
    "^8H}Y;x5mAe_=}g#9T>*foC`iWP@#a_&}`o6po>dCDSJQ`Sc$&<=&Xv+%YfHQI2k=tNj3buK3dY?b?u3VyYJ&E7dMeK;4a-J"
    "oL9^eB)=3Eq8+TQ{RZpYYon<5r&Vw3nvX9u@!<Oj;L)DVZVK(FWf&AJIj(@6h&dqYTI3zFw#@V`bwB@Vp&T7k08j$mT(%yB>"
    ">q@Si`&j97yIRiZk$1akhw}OU&+cJz!3e%iOZM|_hC?El{Qt_6EM}&pPZB>t!Qkg$}X6&IE+?r(n~UZT(Y3#M@WajE)Aun7|"
    "!9)bMd)$QR3Nw&A59h`{y!La7>S0`bwf^anZt}l<hrDvX%1v1um$Y%4l$p;tz;}aPO;2LyV)~L8yGed?TBVz?b_aOW12-B->"
    "@Xp*P+^<oBhCQ^X8xc>pmP16R$ON^@ggb(Tb*e}L*e5B$TFb8vlSz9X}R;s505LDCv*?Ca!qpx>p7MTf_7AI-I&nrn3KR<jF"
    "5IC&*>GaIg5*(G_9XO3c%0~u~6BVYj3#7;uRWwt&%it<KZuX|U+G>WC2&~-+X3|ZrzC~9kwfna)v+MzU_#NEsjcWdYyY$B@X"
    "C>hy#(k_9-L+dhh+xR}0>|3+v$EoCnIIh{XQxX=B@vIkm7LS7PNU9wN2_wRW>w{dJR?4N6MdC|*uubN0EGEVyY8oSzlfY{wN"
    "_LMl`p9mKNQ?(Wh-V@K0SI0oA<b>H8g-L>aP7qB<Vz0~Rca~JC0fA2R&o9tIi(m?@Sir-gjJkusk)WGs@&`d%TV>lODlC<*%"
    "wT8wN(GwYnZ!x87_mYX}C=jlA@X(nKfV-FI=4c#fGpfIUk$K##tiK12v%24-pBV3H$w&ePbGTR@o%l*}&;Be@;JAr%1cgvI`"
    "{1K95r)eGhTy6S6xKA(Csam7oCz;ym4swSPIdHh91$0k&+Pykj}1rGm6R)dI>gDsADi>A5IWu&*eYCXhD5Mg3XJV&=riQgeS"
    "X4?k+V6L^<}ZnMIkT5zG60~4cU228+xn@CsL6PSWFVvK-)84r@Q6q)u-5C<+Z1>&Wf?jMIX)L~?u#88v88#;Dzo0UiXRuPFj"
    "PuabQag6O!qP$^~rN0osMI|bdUWoub=jKY3>VRFOZYB?GO+d0Q*wW%Zdym+VUJA5Urmcq;eOC5rL3k?=;Zt9_7@JSLH>K~P#"
    "-T&5x<3pGeP5cE(&_Cmm3IgaQX+sv*NT$)+_8CZuCzz5>t6M#X8#viB(1tp`SxNe?UMONSF^RQT)aM-MWF(IQLF{q%O%q|m+"
    "}RC^V9)9&uYLQ^@0izL3;mz_zf2S<CDNn6A??xXYIOO2%qp~CRo<sbo$aH*T!6BQlX4G@kWNor&VZNt`e^L<;=$gTIU<Algr"
    "wRH@b!}0zA&U-bxFesIC-Nj^42+GIK2L=eKcOigGy}39&F^Q+)K7Dfn@r+cHKP_Z-B&t1z0rh@~B=-9+@$_bc^D<@8Q34l7<"
    "&d_FE$I@I=i?Jl!3k;NfMl)&XO0kZKm!d%kp)_x!D24rT#a5S45*=O|fu)3)!&s5p#w}p;xWNN`#<U6U`bLn7kE}w<)Z7Q?*"
    "?RVtU0=#GJk9^hohOgX-cSb;0lFE%7>yJ`72sp77RlA<9w_|H3G0{QEJmTxs&1vaXXu6-Tsz{~GMjKFB$s>0p=W5UVD^CZoM"
    "ndIA0|m7o&p<E?Nw2yb{odnv_p7uza`uT4g?9~!L+iTGQ*&B@&Q!gy*%ein1aO$*lv%bLVZTT`zW=)5B&T7eDM_>Q5Tp-84v"
    "G4}OCk{s@@{+dS{Y~*%~z^M8uW72D(aLjw(_eyhiw;;=z>;la{W=94WL8Se#;W2cMrgoZX#+&cJnJ~*c!S>R}vg#ORh%o?|2"
    "Wz{5b)4tab^(cKppDd8`7(-kgqs*hGp_NA@^(327_j<Bd7+YGZ5v=pP|yvs@djZj0n1wcIg0d$ur*j-6C#n9@alX1h)F2d=<"
    "#e3K@*{|82L3`UQVO|?~fKz7Mz1FwSdYI0Eci5DV?AUS!VU;;W3$rn5zQx%2gAz=rM%JsD0v$6sTBGjbCUYUoGrT*A)f6~l&"
    "&&)ZvK`aCED#v)!PaQVr6@ltsVH8CNh2MNA4K1jx%Nudf%>zEecNoG^8~XgBKSMApd?253XZ4BFe^gJL;a=%xAyoiCg+6U{!"
    "5Wp|Ze@V5?So$mM3_X{)w5fZG{92F&@|K;B2KO&F>>i1(jK!uI9yKt-p2vY2S3i2+!D!*t(i@T{ZQ6I_3Q~wY*c-^rmhS~1@"
    "JBl`#U0Z*+OHki+#y}R}B}50kS3y3K=jv($>B%S1_gxdudl3yk12><*4#Y<yjv^GT;F`*D1;qtq4HP)Q(l@+1}tA#(B0#KzU"
    "4HXGr@9V<?rk+8#hNbvw5C_V!G~Ds_o=BeVQAhCiMlqv9_GQUtIyqH|?orOU<nD>w{eNfk^vU__`&)PV(40o)147dYkZy7ZL"
    "XAYFG>!zsnYdtrbuJym*dAVgpa23yug5-d5x)XT6XUiHTnnq#?veZSn+pmr<{LfZ5YYquloM7(DMZ)217mULa1M&pN3?sw$I"
    "5SW2TI#xpLT9yo#PGIj3rC=P`N&}_@jBlW(!u>VmF8B2ylMU0tLHWRNJZEj-QyU*jxxk*F>U_E5E(AaMeOvk{rlT&_zbu$<9"
    "@Z^of`!v&9nc~Z*n6fmgc!0#&q5eD&WhA%Gc#9(Sj>E!HwmL;GTCbGPxID%eY5T|`#&r#mRL1`ELMWBx@zpZyecI5^B5_KxN"
    "WPk$;;TwNu=A(qTke!v4{hdo6}J0!9TnHFkvyhLA$!6&2upa1(n}#t-9N7nOHW}-$A&P<Qh5jdXp!4!9Ui1SyI~&{9VtwvM="
    "`@C%LRxniSVP50&@bG!By#VlbjHKX~~Knvh^#$`RdA3x~%3>BGD4=PvWQ?$GxA+_)-NXao#i4WRh=&rOowy209i8RW-rn_Ij"
    "2mnU`Z?}bs6`*9iIw}-8LdHdq`oB#TM@sa;>"
)

_EDIT = (
    "c-pO8X_Fk)mHpno;zbb-b$3*k)Gf?X3`8_i12RJDP`4}`GZR);<*TZ+vNFq=S=}l|Gl2rL2#mpl48}_g!)lMsHZx#>FhmUhg"
    "itU1i#g}s_cF73k?o23U{js>miz8<?(%Nx4zm(Qg;~wg;ixbx$skC&HZ$KmdEGp06PpFGncY}wnw|gra_565cdk7*H#0Lo|I"
    "n#(YwI$o7}(630RLORaMt8@6l6hRO&lcsanQFWwB0C=(j;%0lc_m#cHMN-q!)7xrVd;4^IUIsdCr{nQ_>z^naplxQBl~$jD)"
    "x&xjDJAcH-Qr)%8=~U*W^t3JG?@W)riSW}!KIetqrK$rTf(<4$bNkH=|Yb2H23LYsH9XjFg}GfBsWi(Au6GubSRdc85}G{ZE"
    "saZ@Pei^5(m%qWPG!iEO_pUTr{2twytW_=Ll<q-{j_o4(G3zE<zX|j;mep*BUNNMAo3+8+d)<#KQWaDn(W<-fOF^Ce&!#wk^"
    "j;y@|SA$xIFSC;L<0v28ei=9DHp?uZ`GH9()=G%8-wQ?ocW;_U)651*(>#>fq&sMuHN3!jO|T+}n#LC0*4$r70p<SSez~u&J"
    "icz$A6Z^E7fzi%Z5~`P=T^>~TsgOL(wsW8eipA*DCgDl>*myB%MY)3HKbxeTMCTYuLICNNGXKm3er$eZa8?<g>bVd1+5bU1+"
    "p0hwb(MJl$J4AbR?f*Qa{>&O7W$=9ALUA2-HH(+cam-nIsruL|}>_>)WE@qSrN<F>71>mT7EX|7`oYmyc|{{nGYp@9bRrZ2P"
    "G<jx?Hh{`~XXZ#?_$o4?$8=5-9%ec|KnSD)pJAPljzmxn2$BDQ>9vAY|TtfovFDh`MXr&F5a2?hp^^rIX&^*A4aRlNxM?n!U"
    "WEVay8>cnP5C5V(eQ8F4AY6~Wap%>vqgaB*Fb@AHH!gXs-o_*}pndLL<6<eIxWf}0=UXJo2O8RaAweQ4i4s7B!ol;nj5m-JD"
    "D+U}TMUC>~HOdtUl;D!kB-O2!&z#)1fr^qNre!&Iz{&O==m6b`irmIMIaHK%<8jDy?zb&9rR6N>MBU2LXj&dap-NrRWhh>0P"
    "Z!ec5`+d>4o5&7cTVtVnC29&E_*m`1o<W5dupI$M>7k%jrwG(D4E%eia`o_!vJJhX#qsu9M*%8B@f6R1#z+nRLzPVhI7j6;W"
    "#f$$C~+h5;Z?x6AV}urbEDJO^S0($Ullzzw>dHrQ<|+SBDn*5V7hgj_Ybs;m!JH3WB0UxHp8Ffa;`zZ-7x7dK~{{qK9dc#t~"
    "_YK|946rqB`$i7uCDPAA}53#Jo%NWSw)eCsCJAp{wiPUM!PyUENriEW;jngm{t;;0)@kPuWZXp$zjWtOqh{CwXg@WBavp-J("
    "78TQMag?cv5&*OZiLHjoOz*-uA7sL*OBI=qjD1wDB?T*PAyvd6+n{?6uZuKY_&>bXESBT4C6ot(iCQj2!WO>jXMA$e4v5-uE"
    "fDI?q6rQn|jM9D<j0O|+shx?*p-Gql@s*5@gN}{!nl{%Q`vACNv!;$|%Ay|P@*<ez-u^-X_^{@+@Hz=WfAj<%j}us*%qBY*2"
    ";&l2jKHu2`UEoxCZK2tP=HSY1kFKZet<}U!A(Gn#84cnFx@!FqTYljP#d!dq2#a1w%~CdmMsDg1RFtrY{g85ov1%f$GOa#GD"
    "zXrG_ua-(0+}DocE%Ef^w=YKx3Sg>w!743<HjmrZB?D0;Et=rXU-VTRweZ`3GxUET_=blM)rcsd$sj#ldCtf?uzI_BEZN(JU"
    "5<bV1kaAxxt}Q?y{+9e0=$05o&9^CKl-X6Br&+*JM8IZqU(n|x%0;hr5OB7@8+0^1!c8%i`9!%8@cv?F#Mq|~RB4uc+UA1}!"
    "w*chxRAEcX2(+jXrZyXyJ*_EixP=aU)844BE!RF^5NjHH8-GKy>opBV03Z<O0(8)-K4H4R!3*Kvq32z33oO$8!2%*Oq-033V"
    "?%NOu2=q*8V5#uyXiy+L>EN_SJ3;qSUm#C}+9V<qkDyBDPnC~;j8kb81GAXKer3Mei0tMl1$jro#Ek%U1`=}s$PlXKlv(X6r"
    "37FAZIi<od{iK;)a7zDz!=ye)+szOuw84!+FA!6Ie@}!mS+|RNvIynQE~QB9CW!*;Gd~K=cK%gGz4TK1xRyMh@gwuKUa~GAT"
    "t`I&_W0_6|P`lK^UZK?kV~J-zcX-l{A1sNubcBYtd6f6~%luY&>Zj=ljIpC;@TQA8_{?Db8RW+BvgKdsN7jX@JL{mRW;fRqZ"
    "WcEJcdM$&4Dw+D(WARt3EkB{tv&j!&M5mvS%%8x`5ukVh67ho(F;W+B`KLUZK>oEh%M@d2FHvy)1wdOT6<Tn9N1(^n*9>S~6"
    "NBtqaIL@aylGbbZL17sg7F`)M$tYOw*s!6{X&>kd(tYS#OrJqiVE0uxK6o?;<f$tVhLs^DXr4%ZWIT<4O3oZ$Og|?qrtNJ!b"
    "VPbm~E-0LB_kjD<eMu%Cgq@l}5Hm`LV=L%7JggQ70ATPjm5`{C3%2KzAsiZVf%XitqWSsL78KB1Djud|byg*y$XUWD6z9z|("
    "RTAekc~w1F)FhvfgHLLr$T@kk8-C3GN4B<nwOGv=A~~#7$kiaXzdCED7hY3oNoprKO`LqI0xM>^bMYxOVyB~zFuQs<B<ry0d"
    "q%)nS&aDE>0~c1KSC5h$h0hmayPF{jvvO#|R~Z{8mH(6T0aba#5L8`OP@tL`j!1x`~jf8;o=7;=vySu=&yvD7rsFXoE*RrrD"
    "yMt8_@&hMEar5%JFayvy&r^AYEnJ1v}_Z<%wpoA#6FiGYz5kdS)MaHL?+0XdaIRD0@0m#K{uBHmNO%CHt$1kixoR7<%aqEF#"
    "K>0g@V-<ng>0`v|2P8rA&|5qe}$wxRyfY_x-eRV+2a+#ip02~boDo__eC!rC<Zy+q~s6k~`QqqZwMi8w~h2b+Ta+p|iCMXkR"
    "yCL3@mhP}bImx`h8L-C89Xtsr$^meVxjuLr6Pbe!VW!LvTo{lCJ^K3rH7;>pk?^CbVpqK4S}>{cw^_RA%u4-40;GamIYXOKP"
    "0_r{hGp^&Q6OZ5)=xofmcm4UngdUSJA|$&8e{|dU56JV!FR^Trh|C!k}W(VRHeXkY9zrA8W>;lk{7E)pfo+Yo@Fr0&3&+-kq"
    "I@}^rcwl67MpyX}e*W<eS|LM}<HsMlXe$8S?SaGVj6im#iH%tJ!gMi8CV)4y<Rm1*)^x_ec}`A1zWO;uWV1e#H93o5>JnN}_"
    "YzP^LoaBqNM+4KG=+>)2w`VrU)>BSZ}@QprX5r$R!AS{)Yw9O8&X=ncddI1~jBzS=BL69ia*HkgEo{4@{II)GN<fGv`03(hb"
    "k#;|4x8F)jF?S1NWL-1RQ2TVxSc{ed5qhxbuanQE=rX%blxl2JL%mko}hloWOOi0i`U5bXRcf|3SRzZ<A4Lo(hg#7qPH@j)P"
    "g3n3*2;<y99O3d8!KvG1b7}&)mP0jsD!Ecag<8y__(Btj)FBIhGzdS$NP0G4=q1UL=Iew9(ANR0Yx<p+Y<9|>S*O{W(9$UfE"
    "|aBBBGXm*pR;)ipX-tv&@RfG@B~A(`t@;^xFo2Iu7@s-@eo-%qs9YewkbKBx=N*A@}SCiyz0xmv?Im~^=O%O#=25(_Q+O-%4"
    "Mcl)^!27l7LHESWxw77DKwHTx65&PhL{ioCuVlG6@PP52l#_8d!ypH+OZPCIjG0j<-2+G00uAMpTJh5Crtp6i0ByS0`HLQ6N"
    "G+MM1jc@;#Abv&O?XP+6+PJlwm5fw|qn#YEVbX}XK5u=vCUqTq-3970D2(nUDeGOPY+mvgD*47dlAoW%hm6k}uhEidIMjqIk"
    "GWTWZ|s5fU5pJ0?xFqP$`mPT0Zq$u2Z_C;SVoM_g|DH7o@z^R2b-~wGboDv~FrbnZQa3luENCYLK;5`H4>!eUlu)N_6lDQ|%"
    "II}}6fMw)ATqDEGAkHgIY-;M1NFfBV{#b)Xq%tuxDsTtnz^Wtx@F69bI*xr{QsZVf9Y{S>ShdciFRDct#9AmaFKK+TDd(Uzi"
    "CRgTxXF5$Itf2p<G7|XPVdbWJmDE=Bvk3D2IFFfrdF>sY7&*n$3vj37$=jEP6zym0y^{n9t74$3g~^1d5Un#9g(>(c$DzVQq"
    "V3SiQ|@eEGU>AFk&yuM=sTJ7F#9u5I@cu<paoLFUm@xEcMmjT5ekE6b=m~4RcpHm+Tna*@X9MYHY8DNRIg+rowI!%LQMV3A9"
    ">LK?8+?WFnMEXnJ3bJA<jv!qts?5ieB04VNyfa=Ys)dIIkzM_N|lJZc|<9UsMt3*TS-@OfX9T+);;rH@6<WP1!UScsGpesAs"
    "UnWn=hU({>YDk}SGDXy4qW~;JxAbE03NcQN)=rWnOD>W@S&E2;ruZnVChi331Cr9!=s4_|y4M=6)O_su}M9FdtT9HQg_tmr="
    "QOgrn{l8q&IR<GmPlTxIWG7-?EsD@^ih&i-4qU~<h2^%4r$Moe9K>0FQQ%}Lpdrp+L+YHJ$pINi4F&cjM^QeN61$<^_HeGUs"
    "_eEUhDyRJMFI(RO1jl_<<^UnI~Ek|yQXCkT(#tsAk4YaAD<h;wq|A?!f74@Rz(Xs;FKuX>>2aG{bp&dx##A#?k68RzqU>pn~"
    "Q%Z3bgpZ#iswg#NVw}i@>0vJAO!spr*hr?-jU6!gvPGt~@~*Iph+Un8wzxzg*<a*v=pSc<aWKTVK3^2mD)YEX&=h4GDo83aH"
    "Bscc)tf{k~Jep=M)4)^b=9Kj3z^WyltmA!F-`p^@jy{bmtt3H9Da(%_)4&{`g}0(5sO=;kcx-+JmLQjA|a*Pgv~<9$!Q5>7#"
    "_iBDHfx!V)Tm1^-Nw^AD-LPS$gw>hAu?=5H@ke0cSwpp{te2lbx!Ws*rvp@@|Qde~C0}{*llu%fTa8VJA^g5ogxK>Y|#OjjN"
    "6F9r|@^f2%{`e^Vv-9+OW%N!7gR2a-wF+p;P^FBW^K_hbZ9P*`J17+;^j<Uxqm3vOB)iWQ7s!%~z9i?LOjNY&o{3#by^V#Ik"
    "(97D(kQG4+mfV6?m3Yw8nLIdib88ZAy5RK@s5i})=LJ#u+Tl%N|nQ{US#7iZ<~vogC7c$E(#ki%I_cc(l|~xFH&vgKA06QnI"
    "QSzaO?ouUIs4b^cJcPkc9XPi7_{Vcx=^l_2S>(blKsEj8w#EG~^(6n6(0d=wjQP5M+#c2WB<ZC2}ChD?AgIWrXmVnbW*IQjn"
    "jNzE4i0S1I*acke|>duG9`NVqZrh9ZMOnwChLN!v6Q?_D}}dGXji$7nA196R>)Yj+)!-+VS|VCr&>5SejT`(6&XvwfWZIo@9"
    "4f9`EB-X+u8i=1@QyXp-FR@sn{fT&7h<zQ;T8DkbqWBdKLwqN~h>(6gC%u&<Gk#uBMer~<}-!yFg3^oFon*3ztm{*+6>&vrS"
    "H(uHO^5<J0UH$gAx=Ijt#zXZc4Y^}g;&i{?{m0I==VTZ_G0eNcNLRs&t&erTo$H_M{^aLdZ(ZH_{DwS$)?O;o5sM)42osc+t"
    "q=a}XKY5I*hu^3&)xT)`S#5^MKByo1RD=KNf5>IY;|>Am-+1G&eabAUCMzNLzSQ}uJ644`Sz>N?)>g6e+)`M&$07|SN%CgX~"
    "vRwp|t<uRZrCRwHLO3^LgzU$k`LS=MZkt$1iPt_6vD%3i=Zum>lZWraW6Kq{1M-&siJmubqE;fBK+8qv(U<wXXg2@9@?WHT_"
    "q#N|I{3>jUF?si(fDecT^=>w{}sFTOIp$Z`^9#FnW^_qLagxjDO^J`GXHP`KnQ*z_FUy7BI}AAcds$eg>O*p9o`KLMWZT)*i"
    "BSY7~o1;Oj>53k?)@&&I7-@fvxKZFj>yD3#mR$f{x1-JdlpSGWW#|bVkN)=ryH{bp6>aClf0?1V!C-ve+X9Rgpan~Mgee}}K"
    "=WpKn>|Ocm@hC{a!G1m%yLFGZ?{w=%t3g;}H4_3`I2HV_?caXo-^sK)OLD;M?bknKSfCUnDU`!8!u=JLXYgjW_412eqdP!U7"
    "C_*vvapoSciq6{JKdx2w(oAtQhQ(i`5Z%yyD?;zMv1?5r~(t0ynBg1Y9_(k#;8A7$gE`Gbdi_rL`xvEjipBgw&efsd9*Pnpz"
    "q5YKDS7-T<_lNC?#I6%YY`|e^Kf3=G@dbAnEt;M<Jd@QVamTcu7fQ5I_r_v!d)=t0P6c(?s2hGy%vyf}By()2q6g@8bnhjZ~"
    "REO}tAUwb!F#tH}~#s}u9i$aKe=s(1FKM2wbn2gV}K-&UM%`sz2swxvfGv_@W&1k!j&UUE)2FnHB64G=cwoO=KZ;YVxzWe2)"
    "SA*($@MX34x`(4VCfre44EilRuX(ww|o{Vn6d9pcOWhz|2N{z;0RM-O@Yqdq`UiI#DgIy6Wip^Oo)3R@2`!@5`aZa0a7!HHP"
    "xq2wE)ULPNNo|Kpq6AGOJeXpOOvT)Kxb1rdW*6)7oommm*AhTg8fC#js!$5HwV&}|*THP`$&8rl%H^)rWS(Kx6oq>uT{h#mW"
    "3#2gzmd+t^4?p+Wtg!PM8>(lr>M7ah#|V#gO7cyGOCx__6sjE3wr0Zt!G}}`OUvkIl5^+ii64ab1y$GdD8E{+WqwTt>-@4dg"
    "<+3H{WVhS<B%Z6Y2W?OULHOpP-gjxN?W9qWR?5clx>Pj{eyONL;&vlxazg|LhtPe&ldJIARw;*31>NCeL_ZWUd%L+FY5rvaq"
    "lq|HGJ77efGD_2~F92;$yCCk-c<Chm!I<XT&w>Rv~AqA+EI%EAEodPTjC3_tCItObS;dL1V7uBhF~pfjn|BZ+VvqdCriWqa&"
    "*d$!KzNa*+I8_aAfd#*TyHx1zb6=xipqVKVdGv=FX@0g|fZaGY(Og~h8dJ2>C^DYIGaZ@dNhop_XJo5^Akjc%tD}jU0Ro!76"
    "k@UMo0ZU_nlkW*7=ZdLMtqa=;{6wu&L{!r!rB!Q*_8o|@X4z`HY*wN754sF{`}&voOA_zr-`INk9sU8%iWhQq7M-iixZ*M3@"
    "dp|ZTJ24Opx9<}s$4<W9%U<=UgBfh7vJ3d$qm`>#W#@>lv{`f9<+4rMSbNHv9HBe3;+9D+rN3yt-br!)8*QFyLRB}Q?Kglug"
    "RrL$;Da3h&PEDJHPtLw{QJy`;9NSkN(>I>gvvWH_P38@j%y{B?O3*kOiv_oIQk0&#F`MVAbA`*{VH8H)H9~y(|TNkbI`z)mJ"
    "}V>%KZ*eHd_Gn)`KT$4V(!8y%*%*fVm9mwU?{RM1+rqoL&v(LJen@E34<_me+uz4Xi7C$IAF-4A|$>*lMsZvOFc;q;kuIv1O"
    "GV|E}KI5ffDmQ<_FNEvT_eqZ&akc#<q4Th$#WHpTv)ijQzm!JCfo%dbSfAb)_rr*@t*Z)sQe^@Fnk|+?>g*N@c8c`j7_k({O"
    "@K?1z>ZsAoW$N9@y@@g3N_3@DrxQ-Tl=Sd#0sT10i@yc=t2ui8dpP=^t=(44ZeRO7QXF#N=BKy5xS^>ZV1LHPyndt;etF4xa"
    "5Uy2upW<>k%Gj3lfNclsBi3A3#UE<;1w){Cy{4|xeTvGBsQz!1kD}X?V4M=ydjZ`9VuzM%08<`Qa0j+50pP+L!U%X&~Pz_*!"
    "KK`wqY)<DUnMNRwR%L3_@#nDwl;WHQ0oJxS;-+0l38bOgCHgeLHMWldYt)g;Z4gNwY`L?=!2CR>VX1RbAu`%uT0uU?=U=!C)"
    "=^SmpJ;va5gw+w9OyXbwCaH>*GAp=9sHy?e{)u%BMYZYBrp$>t0;4F!p|KirlAv8t&Zq{D($DK34<Uy7HY>rAK$R^Svid5;p"
    "YmLE@;dMsBRJD4!$%?gs1Xz0F5bC-fl$TAx+ww4<(5PSUCcfNV@mG2(=4lgW49ognN3fPn3x<$)0s#H7a;P%ZBqp{nADtn>*"
    "h@&^?BCBIQM~Sc921xg1gJJ}{TT(T32(apl8Fh4@)q)40z*jfs1aqswx5wQz*Uwr`C#dL>S5yrJ{x0xRsy0NcRMo)ae&F%Dj"
    "{VO^81Vgb)$sa4=l5pE)%QK#sh!Vly-r*W_Vmvj!c5Po^+9Is0{a<F$O4*g7aB?c-Om7jbq?OTac%d#XB?is{j04H{(!K@gK"
    "1H%m1b@Qe%lk9z3coXkWCJT*ReQsxi%ys2H2rhUMA=rbQp}Zhgpyige|sUGixsD$p`ROHEh){LJBb{3YTc?1HqhaC53B5@F@"
    ";0v>V7Z?Euf7;JxqO_Zo!xK+0K;*1zRLvibQ{VT%7sB$G=OhFT<N;2eiAPH!>Xh!ENR*RLI~ZQL}+zkY48q_b(3zJ6_KuDm7"
    "E(<0lH`!QKiz6YD1M~={uYLW1l+s^9kosKdW%-656cXvEY@;S5j?IV0kRGD+Rs?T~HrZSW1unN+PihSzRMBfr=FLxE-{S}Kq"
    "2rr5unvs5Hu%h2_<-F?<Efv&T=u8&m)|YA~Wv5`D=w_?)ntxerA7`hS#zFesS}Ips9xCs5&dPnpL_Onx1?K=$XOKku<5E@9>"
    "%UE{z(K6Oo7->VcAllSs<CTFArY`fS>*eoOnF@a7<OI&IyUzg&rL;~IxBqfAtyZUk8m&CH5R6#s8uQlMLWID9?Bz3JWdVt6W"
    "uhYs)tXT`I`{EX2Z3*W(Dv5D)Aw?o1QsaHf0Af$YSq?KZpeKRbM`N>24EeE?&I&Bk0P^Kg}4^C@<`PsGnLl+DK@oZ}JcL#OZ"
    "-XlaoF9GHI$xEBEk67&{!1+GqVb(M_)NL>4&W%Ns|4ut$7%0RLcn03IEApfU5$B!6b+;$FHhy8C*elz!bA56ldaX14#E^75u"
    "LaJTnjsZk<dXR-HCdXJQkXU^h4ywpWZa7hZv?CIi@TFcbz#eYaHN)!Duv_QWNmWB^4gt#`Wz&Cf>X4R}!=Do>OHBDle@<KN0"
    "#?q~VL3_S&NBrNKx}%g2fhel!J_-GNAeGNriyA@Yw|GLdqt_MdwRJ>44LBqB<J#wAr8rwFi0`@NmG5sT5cfUuet|K$bQQ`ay"
    "?iYz*!5f7vW7m#Hve)vn$OgJfi_xi*ooA!-JQ28zcl2Lv$wrScLu_<mW^FRY*5cHD15?h<2V}SQQnk~gR^m>AKq}9wq&rE2O"
    "6henFhUHBy12`W*fJ@`t9~lukJqeQ$$3!Zv1Tb%U4)t`t_GvAN&+y5|is^Sr4jrP6m<^4Wdq@Inium=iRH@@4vZy{WDeuWGQ"
    "l|iqYyF?4v;zh?jC(AH{!me)0O>KmL!mZoG*34fk&s$UiUep!HuDx&~6V25s0jk2<iSwvFTWILWl>H=JsIm3P|btDo?=hFwW"
    "{syV7n{^S3J(Kus~9PVI2JFaHKRKF5q$~#9Fo!Nz4z5<js4psk!>8>VUimnWA)7=o2|AxR+1Eud%vHDH$A^lKH=%@GLr=o{^"
    ">)R9z+V?%L03aL|`-g}u(2IeUs6|U_+Oli<F~4lP{kOk1ti=3({InH*MEbepzD_)-s6Ekgzm2v9L2v5{^olO5p^yIa9J9VhZ"
    "3?XBT!G-g{<Gz|`zjHZpj7*S+Eo+XlfQo92L(H%O>v4hnyHdE3;uH!*WaP45@l6#>6dNl*Lh+6^ZDt2Z-SgGai(3b9Zv&RZW"
    "_n}8=CY<8K?TE4)$G0?zzGW_I%H)brIQm3e(!=f`n{`U3VQ?u?NbO*IP|r<6PqJZ=QU2ZXeA-`907cFCf^pAzx?H3zU3;8a^"
    "f+N+njy<rOrOns};Lhw56Zk~!ce&U?s4!_Az24H9Z4+C8^>wYf8{#jx(*^kdsvvt>QRa{hogN25^mqrC>&-K7usC5lvKx+&J"
    "^Nt+`7L4w0OoU{|tef6EU{};}S;2r"
)

_REVERSE_EXTRA = (
    "c-n1K!EVz)5WVLsM(U-Nl2lw<#0d$3Pz#}mV>4Ng?Ir77vpY`ezvs=G7La;K;&^A@y!YnK#Rcu;B)Q0D%xM_a$Bu^7$ZGY_`"
    "$9V9Ncg?Ge;~%wz@2QQ@wHC59Jll_j*~7Ym*t8$3zcacgO`RF2))qBmx;qlId`IzVwl%JYwB6+BL~`NIcKjb@p0j?r(r5e2O"
    "*}SDCUr&kjj&8G;M0T)lv!=R&r?y4P|jzSnDl6_`o^LG^XH74?6W0wYWtwX%7wC)oM2dDb%J694IyMH>(Z3m*TQVf1~@%bb)"
    "~!e+ZE2B+A-E`j$p6iz%r5!^=laAkt<j{fhqQ4yL~*DY~UQ^PdKZ>JuFP>t<P_sFf_y2?ah#C~(&GXb7~owdT#cHI<MQwGhB"
    "@Cf9T9<T}e3*va)#WCUo@JUMG{Yi`0HqX}M9P+&D4zG;}Z(ETA%%NfSc2@_&+Jlee*v_AYq)f#pdsCHp-unuwnWcD0D!$Eo~"
    "zKX#S&>atwc}>B0y;%eV4uV;)>A>#T<uq9*`(y>Z8P-B<0=AE2Q*R`qr9q|M{7@id?lO<PQT_rUl21auF&A}Sz+eWl5UTG>M"
    "ix|LGFAO`eso!U7fY1|5yje!pv7IKiV%p{@iKrb^Eb0YWsS_sKjZPkTo^bXOWguQ>`x1qB9g5)lm-tfnPUl)GaU)D4?F{3eG"
    "oGew=0FfiUtFP)Fm8GP#9q(9>4EC<NNClu#ME4c&$8)rRp|0jJ=g&oF00!&!UVmo-9YPo9Y&T{VQ9C4QRZxh%|Iqa{qh<tTJ"
    "{5L$Ms#b}L>)Yk#}=TaV93Th&!3@Y3&}3=$u3ZtU(SwYa~mSb^t3Ho?QRPv7qEDAmkC0hZ4eI6hx7Zx~@bd+kY{*y3wDR`*m"
    "wQ(hBi_UzC7V`k9U-%^w6khsC?`tGq!A*Azu`x^wt)0+"
)

def _decode(blob: str) -> str:
    return zlib.decompress(base64.b85decode(blob)).decode("utf-8")


def t2i_prompt() -> str:
    """文生图模板快照:输出 rewritten_prompt / wh_ratio 两字段。"""
    return _decode(_T2I)


def edit_prompt() -> str:
    """图片编辑模板快照:输出 rewritten_prompt / wh_ratio / ratio_follow 三字段。"""
    return _decode(_EDIT)


def reverse_prompt() -> str:
    """反推模式 = 文生图模板 + 反推补充规则(描述语言由运行时注入的规则决定)。"""
    return _decode(_T2I) + "\n\n" + _decode(_REVERSE_EXTRA)


# Qwen-Image RGBA 工作流的固定触发句(功能约定,输出透明背景提示词时首尾包裹)
TRANSPARENT_HEAD = "This is an RGBA image with transparency."
TRANSPARENT_TAIL = "The image has alpha channel and the background is transparent."

MAX_OUTPUT_TOKENS = 2048
TEMPERATURE = 0.3
TOP_P = 0.9
TOP_K = 30
MIN_P = 0.05

# ---------------------------------------------------------------- 语言与消息

def _has_cjk(text: str) -> bool:
    return re.search(r"[\u3400-\u9fff]", text or "") is not None


def select_language(choice: str, user_prompt: str, reverse_mode: bool = False) -> str:
    """把节点上的输出语言选项折算成 Chinese/English。

    自动档:反推固定中文;否则提示词含中文(或为空,准备反推)时用中文。
    """
    if choice == "中文":
        return "Chinese"
    if choice == "English":
        return "English"
    if reverse_mode:
        return "Chinese"
    text = (user_prompt or "").strip()
    return "Chinese" if (not text or _has_cjk(text)) else "English"


def _language_lock(language: str) -> str:
    if language == "Chinese":
        return (
            "OUTPUT LANGUAGE LOCK: the descriptive prose of rewritten_prompt is written in "
            "Chinese. Only text that must visibly appear inside the image keeps its original "
            "script. 描述性文字必须全部使用中文，画面内文字除外。"
        )
    return (
        "OUTPUT LANGUAGE LOCK: the descriptive prose of rewritten_prompt is written in "
        "English. Only text that must visibly appear inside the image keeps its original "
        "script. 描述性文字必须全部使用英文，画面内文字除外。"
    )


def _transparency_lock() -> str:
    return (
        "TRANSPARENT BACKGROUND OVERRIDE: the result is a native RGBA image on a fully "
        "transparent canvas. Remove every background description - backdrops, walls, floors, "
        "rooms, tables, sky, clouds, landscapes, gradients, background colors - even when the "
        "user or a reference image asks for them. The subject stands alone on transparency."
    )


def build_system_prompt(base: str, language: str, transparent: bool, reverse_mode: bool = False) -> str:
    """模板快照 + 运行时锁定段(语言 / 透明背景)。不改动模板原文,只向后追加。"""
    lock = _language_lock(language)
    if transparent:
        lock += "\n\n" + _transparency_lock()
    if reverse_mode:
        lock += "\n\nOutput only the two-field JSON (rewritten_prompt, wh_ratio); never add ratio_follow in this mode."
    return base + "\n\n" + lock


def build_user_turn(user_prompt: str, images: list, language: str, transparent: bool, reverse_mode: bool) -> str:
    """组装本轮用户消息:语言要求 + 图像编号 + 任务正文。"""
    count = len(images)
    head = f"OUTPUT LANGUAGE: write the descriptive prose of rewritten_prompt in {language}."
    if transparent:
        head += " The result must use a fully transparent background; ignore any contradictory background request."
    if count and not reverse_mode:
        labels = ", ".join(f"<image{i}>" for i in range(1, count + 1))
        head += (
            f" Exactly {count} image(s) are attached in order: {labels}. Refer only to "
            "images actually attached, never invent or renumber labels."
        )
    if reverse_mode:
        task = (
            "No user instruction was given. Inspect the input image and write the final "
            "text-to-image prompt exactly as the reverse-prompting rules above require."
        )
    else:
        task = "USER REQUEST (follow its meaning, not its language):\n" + (user_prompt or "").strip()
    return head + "\n\n" + task


# ---------------------------------------------------------------- 结果解析

def extract_json(text: str) -> dict:
    clean = re.sub(r"<think>.*?(?:</think>|$)", "", text, flags=re.DOTALL | re.IGNORECASE)
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", clean):
        try:
            value, _end = decoder.raw_decode(clean, match.start())
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise ValueError("模型回复没有有效的 JSON 对象。")


def validate_result(data: dict, edit_mode: bool) -> dict:
    names = ["rewritten_prompt", "wh_ratio"] + (["ratio_follow"] if edit_mode else [])
    fields = {}
    for name in names:
        value = data.get(name)
        if not isinstance(value, str):
            raise ValueError(f"模型返回的 {name} 必须为字符串。")
        fields[name] = value.strip()
    if not fields["rewritten_prompt"]:
        raise ValueError("模型返回的 rewritten_prompt 为空。")
    return fields


def collect_images(inputs: comfy_io.Autogrow.Type) -> list:
    batches = []
    for name, value in inputs.items():
        match = re.fullmatch(r"(?:图像_|image_)(\d+)", name)
        if match and value is not None:
            batches.append((int(match[1]), value))
    frames = []
    for _number, batch in sorted(batches, key=lambda item: item[0]):
        if not torch.is_tensor(batch) or batch.ndim != 4 or batch.shape[-1] not in (1, 3, 4):
            raise ValueError("图像输入应为 BHWC IMAGE 张量。")
        frames.extend(batch.unbind(0))
    return frames


def _image_data_url(frame: torch.Tensor, max_side: int) -> str:
    array = frame.detach().cpu().float().clamp(0, 1).numpy()[..., :3]
    pil = Image.fromarray((array * 255.0 + 0.5).astype(np.uint8), mode="RGB")
    if 0 < max_side < max(pil.size):
        pil.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    pil.save(buffer, format="JPEG", quality=95)
    return "data:image/jpeg;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def _context_plan(image_count: int, reverse_mode: bool) -> tuple[int, int]:
    """按图像数量决定上下文长度与单图最长边。"""
    if image_count <= 0:
        return 8192, 0
    if image_count == 1:
        return (16384, 1536) if reverse_mode else (8192, 768)
    if image_count <= 4:
        return 16384, 512
    return 32768, 256


# ---------------------------------------------------------------- 透明背景清洗

_QUOTED = re.compile(r'"(?:\\.|[^"\\])*"|“[^”]*”|「[^」]*」|『[^』]*』')
_BACKGROUND_PHRASE = re.compile(
    r"(?:背景(?:颜色)?\s*[为是：:]\s*)?(?:纯|浅|深)?(?:黑|白|灰|红|蓝|绿|黄|粉|紫|米|棕)色?\s*背景"
    r"|背景(?:颜色)?\s*[为是：:]\s*(?:纯|浅|深)?(?:黑|白|灰|红|蓝|绿|黄|粉|紫|米|棕)色?"
    r"|\b(?:on|against|with)\s+(?:(?:a|an|the)\s+)?(?:[\w-]+\s+){0,3}(?:background|backdrop)\b"
    r"|\b(?:black|white|gray|grey|red|blue|green|yellow|pink|purple|beige|brown|gradient)\s+(?:background|backdrop)\b",
    re.IGNORECASE,
)


def _clean_background_text(text: str) -> str:
    pieces = []
    cursor = 0
    for match in _QUOTED.finditer(text):
        pieces.append(_BACKGROUND_PHRASE.sub("transparent background", text[cursor:match.start()]))
        pieces.append(match[0])
        cursor = match.end()
    pieces.append(_BACKGROUND_PHRASE.sub("transparent background", text[cursor:]))
    return "".join(pieces).strip()


def append_transparency(prompt: str, enabled: bool) -> str:
    if not enabled:
        return prompt
    text = prompt.replace(TRANSPARENT_HEAD, "").replace(TRANSPARENT_TAIL, "").strip()
    text = _clean_background_text(text).strip(" ,，;；")
    if text and text[-1] not in ".。!?！？;；":
        text += "."
    return " ".join(part for part in (TRANSPARENT_HEAD, text, TRANSPARENT_TAIL) if part)


def _check_interrupt() -> None:
    if model_management is not None:
        model_management.throw_exception_if_processing_interrupted()


def _chat(llm, messages: list, seed: int, response_format: dict | None = None) -> str:
    options = {
        "messages": messages, "seed": seed, "temperature": TEMPERATURE,
        "top_p": TOP_P, "top_k": TOP_K, "min_p": MIN_P, "max_tokens": MAX_OUTPUT_TOKENS,
        "stream": True,
    }
    if response_format is not None:
        options["response_format"] = response_format
    if "reasoning_budget" in inspect.signature(llm.create_chat_completion).parameters:
        options["reasoning_budget"] = 0
    _check_interrupt()
    stream = llm.create_chat_completion(**options)
    pieces = []
    try:
        for chunk in stream:
            _check_interrupt()
            choices = chunk.get("choices", [])
            if choices:
                content = choices[0].get("delta", {}).get("content")
                if content:
                    pieces.append(content)
    finally:
        stream.close()
    _check_interrupt()
    return "".join(pieces)


def complete(
    *, model_path: str, mmproj_path: str | None, system_prompt: str,
    user_prompt: str, images: list, edit_mode: bool, seed: int,
) -> dict:
    if Llama is None:
        raise RuntimeError(f"llama-cpp-python 不可用：{_LLAMA_ERROR}。安装依赖后请重启 ComfyUI。")
    n_ctx, max_side = _context_plan(len(images), bool(images) and not edit_mode)
    llm = None
    handler = None
    try:
        _check_interrupt()
        required = Path(model_path).stat().st_size
        if images:
            required += Path(mmproj_path).stat().st_size
        if model_management is not None:
            model_management.free_memory(required * 1.25, model_management.get_torch_device())
        if images:
            if Qwen35ChatHandler is None:
                raise RuntimeError("当前 llama-cpp-python 缺少 Qwen35ChatHandler。")
            use_gpu = False
            if torch.cuda.is_available():
                free, _total = torch.cuda.mem_get_info()
                use_gpu = free > required * 1.25
            handler = Qwen35ChatHandler(
                mmproj_path=mmproj_path, use_gpu=use_gpu,
                add_vision_id=True, enable_thinking=False, verbose=False,
            )
        llm = Llama(
            model_path=model_path, chat_handler=handler, n_gpu_layers=-1,
            n_ctx=n_ctx, n_batch=2048, n_ubatch=512, verbose=False,
        )
        content = [{"type": "text", "text": user_prompt}]
        content.extend({"type": "image_url", "image_url": {"url": _image_data_url(frame, max_side)}} for frame in images)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": content if images else user_prompt},
        ]
        for attempt in range(2):
            answer = _chat(llm, messages, seed, {"type": "json_object"} if attempt else None)
            try:
                return validate_result(extract_json(answer), edit_mode)
            except ValueError as error:
                if attempt:
                    raise ValueError("模型重试后仍未返回有效的提示词 JSON。") from error
                llm.reset()
                messages = messages + [{
                    "role": "user",
                    "content": "Return only the required JSON object with string values for rewritten_prompt and wh_ratio"
                    + (" and ratio_follow." if edit_mode else ". Do not include ratio_follow."),
                }]
    finally:
        try:
            if llm is not None:
                llm.close()
        finally:
            try:
                if handler is not None:
                    handler.close()
            finally:
                gc.collect()
