import json
import os
from pathlib import Path

import numpy as np
import torch
import torchvision
import torchvision.transforms.functional as F
from PIL import Image
from PIL.PngImagePlugin import PngInfo
from torchvision.transforms import InterpolationMode

NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}


def register_node(identifier: str, display_name: str):
    def decorator(cls):
        NODE_CLASS_MAPPINGS[identifier] = cls
        NODE_DISPLAY_NAME_MAPPINGS[identifier] = display_name

        return cls

    return decorator


def comfyui_to_native_torch(imgs: torch.Tensor):
    """
    Convert images in NHWC format to NCHW format.

    Use this to convert ComfyUI images to torch-native images.
    """
    return imgs.permute(0, 3, 1, 2)


def native_torch_to_comfyui(imgs: torch.Tensor):
    """
    Convert images in NCHW format to NHWC format.

    Use this to convert torch-native images to ComfyUI images.
    """
    return imgs.permute(0, 2, 3, 1)


def load_image(path, convert="RGB"):
    img = Image.open(path).convert(convert)
    img = np.array(img).astype(np.float32) / 255.0
    img = torch.from_numpy(img).unsqueeze(0)
    return img


def save_image(img: torch.Tensor, path, prompt=None, extra_pnginfo: dict = None):
    path = str(path)

    if len(img.shape) != 3:
        raise ValueError(f"can't take image batch as input, got {img.shape[0]} images")

    img = img.permute(2, 0, 1)
    if img.shape[0] != 3:
        raise ValueError(f"image must have 3 channels, but got {img.shape[0]} channels")

    img = img.clamp(0, 1)
    img = F.to_pil_image(img)

    metadata = PngInfo()

    if prompt is not None:
        metadata.add_text("prompt", json.dumps(prompt))

    if extra_pnginfo is not None:
        for k, v in extra_pnginfo.items():
            metadata.add_text(k, json.dumps(v))

    img.save(path, pnginfo=metadata, compress_level=4)

    subfolder, filename = os.path.split(path)

    return {"filename": filename, "subfolder": subfolder, "type": "output"}


@register_node("JWImageLoadRGB", "Image Load RGB")
class _:
    CATEGORY = "jamesWalker55"

    INPUT_TYPES = lambda: {
        "required": {
            "path": ("STRING", {"default": "./image.png"}),
        }
    }

    RETURN_NAMES = ("IMAGE",)
    RETURN_TYPES = ("IMAGE",)

    OUTPUT_NODE = False

    FUNCTION = "execute"

    def execute(self, path: str):
        assert isinstance(path, str)

        img = load_image(path)
        return (img,)


@register_node("JWImageLoadRGBA", "Image Load RGBA")
class _:
    CATEGORY = "jamesWalker55"

    INPUT_TYPES = lambda: {
        "required": {
            "path": ("STRING", {"default": "./image.png"}),
        }
    }

    RETURN_NAMES = ("IMAGE", "MASK")
    RETURN_TYPES = ("IMAGE", "MASK")

    OUTPUT_NODE = False

    FUNCTION = "execute"

    def execute(self, path: str):
        assert isinstance(path, str)

        img = load_image(path, convert="RGBA")
        color = img[:, :, :, 0:3]
        mask = img[0, :, :, 3]
        mask = 1 - mask  # invert mask

        return (color, mask)


@register_node("JWImageSaveToPath", "Image Save To Path")
class _:
    CATEGORY = "jamesWalker55"

    INPUT_TYPES = lambda: {
        "required": {
            "path": ("STRING", {"default": "./image.png"}),
            "image": ("IMAGE",),
        },
        "hidden": {"prompt": "PROMPT", "extra_pnginfo": "EXTRA_PNGINFO"},
    }

    RETURN_NAMES = ()
    RETURN_TYPES = ()

    OUTPUT_NODE = True

    FUNCTION = "execute"

    def execute(self, path: str, image: torch.Tensor, prompt=None, extra_pnginfo=None):
        assert isinstance(path, str)
        assert isinstance(image, torch.Tensor)

        path: Path = Path(path)
        path.parent.mkdir(exist_ok=True)

        if image.shape[0] == 1:
            # batch has 1 image only
            save_image(
                image[0],
                path,
                prompt=prompt,
                extra_pnginfo=extra_pnginfo,
            )
        else:
            # batch has multiple images
            for i, img in enumerate(image):
                subpath = path.with_stem(f"{path.stem}-{i}")
                save_image(
                    img,
                    subpath,
                    prompt=prompt,
                    extra_pnginfo=extra_pnginfo,
                )

        return ()


@register_node("JWImageResize", "Image Resize")
class _:
    CATEGORY = "jamesWalker55"

    INPUT_TYPES = lambda: {
        "required": {
            "image": ("IMAGE",),
            "height": ("INT", {"default": 512, "min": 0, "step": 1, "max": 99999}),
            "width": ("INT", {"default": 512, "min": 0, "step": 1, "max": 99999}),
            "interpolation_mode": (
                ["bicubic", "bilinear", "nearest", "nearest exact"],
            ),
        }
    }

    RETURN_NAMES = ("IMAGE",)
    RETURN_TYPES = ("IMAGE",)

    OUTPUT_NODE = False

    FUNCTION = "execute"

    def execute(
        self,
        image: torch.Tensor,
        width: int,
        height: int,
        interpolation_mode: str,
    ):
        assert isinstance(image, torch.Tensor)
        assert isinstance(height, int)
        assert isinstance(width, int)
        assert isinstance(interpolation_mode, str)

        interpolation_mode = interpolation_mode.upper().replace(" ", "_")
        interpolation_mode = getattr(InterpolationMode, interpolation_mode)

        resizer = torchvision.transforms.Resize(
            (height, width),
            interpolation=interpolation_mode,
            antialias=True,
        )

        image = comfyui_to_native_torch(image)
        image = resizer(image)
        image = native_torch_to_comfyui(image)

        return (image,)


@register_node("JWMaskResize", "Mask Resize")
class _:
    CATEGORY = "jamesWalker55"

    INPUT_TYPES = lambda: {
        "required": {
            "mask": ("MASK",),
            "height": ("INT", {"default": 512, "min": 0, "step": 1, "max": 99999}),
            "width": ("INT", {"default": 512, "min": 0, "step": 1, "max": 99999}),
            "interpolation_mode": (
                ["bicubic", "bilinear", "nearest", "nearest exact"],
            ),
        }
    }

    RETURN_NAMES = ("MASK",)
    RETURN_TYPES = ("MASK",)

    OUTPUT_NODE = False

    FUNCTION = "execute"

    def execute(
        self,
        mask: torch.Tensor,
        width: int,
        height: int,
        interpolation_mode: str,
    ):
        assert isinstance(mask, torch.Tensor)
        assert isinstance(height, int)
        assert isinstance(width, int)
        assert isinstance(interpolation_mode, str)

        interpolation_mode = interpolation_mode.upper().replace(" ", "_")
        interpolation_mode = getattr(InterpolationMode, interpolation_mode)

        resizer = torchvision.transforms.Resize(
            (height, width),
            interpolation=interpolation_mode,
            antialias=True,
        )

        mask = mask.unsqueeze(0)
        mask = resizer(mask)
        mask = mask[0]

        return (mask,)


@register_node("JWImageResizeToSquare", "Image Resize to Square")
class _:
    CATEGORY = "jamesWalker55"

    INPUT_TYPES = lambda: {
        "required": {
            "image": ("IMAGE",),
            "size": ("INT", {"default": 512, "min": 0, "step": 1, "max": 99999}),
            "interpolation_mode": (
                ["bicubic", "bilinear", "nearest", "nearest exact"],
            ),
        }
    }

    RETURN_NAMES = ("IMAGE",)
    RETURN_TYPES = ("IMAGE",)

    OUTPUT_NODE = False

    FUNCTION = "execute"

    def execute(
        self,
        image: torch.Tensor,
        size: int,
        interpolation_mode: str,
    ):
        assert isinstance(image, torch.Tensor)
        assert isinstance(size, int)
        assert isinstance(interpolation_mode, str)

        interpolation_mode = interpolation_mode.upper().replace(" ", "_")
        interpolation_mode = getattr(InterpolationMode, interpolation_mode)

        resizer = torchvision.transforms.Resize(
            (size, size),
            interpolation=interpolation_mode,
            antialias=True,
        )

        image = comfyui_to_native_torch(image)
        image = resizer(image)
        image = native_torch_to_comfyui(image)

        return (image,)


@register_node("JWImageResizeByFactor", "Image Resize by Factor")
class _:
    CATEGORY = "jamesWalker55"

    INPUT_TYPES = lambda: {
        "required": {
            "image": ("IMAGE",),
            "factor": ("FLOAT", {"default": 1, "min": 0, "step": 0.01, "max": 99999}),
            "interpolation_mode": (
                ["bicubic", "bilinear", "nearest", "nearest exact"],
            ),
        }
    }

    RETURN_NAMES = ("IMAGE",)
    RETURN_TYPES = ("IMAGE",)

    OUTPUT_NODE = False

    FUNCTION = "execute"

    def execute(
        self,
        image: torch.Tensor,
        factor: float,
        interpolation_mode: str,
    ):
        assert isinstance(image, torch.Tensor)
        assert isinstance(factor, float)
        assert isinstance(interpolation_mode, str)

        interpolation_mode = interpolation_mode.upper().replace(" ", "_")
        interpolation_mode = getattr(InterpolationMode, interpolation_mode)

        new_height = round(image.shape[1] * factor)
        new_width = round(image.shape[2] * factor)

        resizer = torchvision.transforms.Resize(
            (new_height, new_width),
            interpolation=interpolation_mode,
            antialias=True,
        )

        image = comfyui_to_native_torch(image)
        image = resizer(image)
        image = native_torch_to_comfyui(image)

        return (image,)


@register_node("JWImageResizeByShorterSide", "Image Resize by Shorter Side")
class _:
    CATEGORY = "jamesWalker55"

    INPUT_TYPES = lambda: {
        "required": {
            "image": ("IMAGE",),
            "size": ("INT", {"default": 512, "min": 0, "step": 1, "max": 99999}),
            "interpolation_mode": (
                ["bicubic", "bilinear", "nearest", "nearest exact"],
            ),
        }
    }

    RETURN_NAMES = ("IMAGE",)
    RETURN_TYPES = ("IMAGE",)

    OUTPUT_NODE = False

    FUNCTION = "execute"

    def execute(
        self,
        image: torch.Tensor,
        size: int,
        interpolation_mode: str,
    ):
        assert isinstance(image, torch.Tensor)
        assert isinstance(size, int)
        assert isinstance(interpolation_mode, str)

        interpolation_mode = interpolation_mode.upper().replace(" ", "_")
        interpolation_mode = getattr(InterpolationMode, interpolation_mode)

        resizer = torchvision.transforms.Resize(
            size,
            interpolation=interpolation_mode,
            antialias=True,
        )

        image = comfyui_to_native_torch(image)
        image = resizer(image)
        image = native_torch_to_comfyui(image)

        return (image,)


@register_node("JWImageResizeByLongerSide", "Image Resize by Longer Side")
class _:
    CATEGORY = "jamesWalker55"

    INPUT_TYPES = lambda: {
        "required": {
            "image": ("IMAGE",),
            "size": ("INT", {"default": 512, "min": 0, "step": 1, "max": 99999}),
            "interpolation_mode": (
                ["bicubic", "bilinear", "nearest", "nearest exact"],
            ),
        }
    }

    RETURN_NAMES = ("IMAGE",)
    RETURN_TYPES = ("IMAGE",)

    OUTPUT_NODE = False

    FUNCTION = "execute"

    def execute(
        self,
        image: torch.Tensor,
        size: int,
        interpolation_mode: str,
    ):
        assert isinstance(image, torch.Tensor)
        assert isinstance(size, int)
        assert isinstance(interpolation_mode, str)

        interpolation_mode = interpolation_mode.upper().replace(" ", "_")
        interpolation_mode = getattr(InterpolationMode, interpolation_mode)

        _, h, w, _ = image.shape

        if h >= w:
            new_h = size
            new_w = round(w * new_h / h)
        else:  # h < w
            new_w = size
            new_h = round(h * new_w / w)

        resizer = torchvision.transforms.Resize(
            (new_w, new_h),
            interpolation=interpolation_mode,
            antialias=True,
        )

        image = comfyui_to_native_torch(image)
        image = resizer(image)
        image = native_torch_to_comfyui(image)

        return (image,)
