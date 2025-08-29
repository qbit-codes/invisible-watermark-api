"""
Watermark Adapter Pattern
Allows easy switching between different watermarking libraries
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Tuple
import tempfile
import os


class WatermarkAdapter(ABC):
    """Abstract base class for watermark implementations"""
    
    @abstractmethod
    def embed(self, image_path: str, watermark_text: str, output_path: str) -> Dict[str, Any]:
        """
        Embed watermark into image
        
        Args:
            image_path: Path to input image
            watermark_text: Text to embed as watermark
            output_path: Path to save watermarked image
            
        Returns:
            Dict with watermark metadata (wm_len, etc.)
        """
        pass
    
    @abstractmethod
    def extract(self, image_path: str, metadata: Dict[str, Any]) -> Optional[str]:
        """
        Extract watermark from image
        
        Args:
            image_path: Path to watermarked image
            metadata: Metadata from embedding process
            
        Returns:
            Extracted watermark text or None if not found
        """
        pass
    
    @abstractmethod
    def supports_recovery(self) -> bool:
        """Returns True if this adapter supports geometric recovery"""
        pass
    
    @abstractmethod
    def recover_and_extract(self, image_path: str, reference_path: str, metadata: Dict[str, Any]) -> Tuple[Optional[str], Dict[str, Any]]:
        """
        Attempt geometric recovery and extract watermark
        
        Args:
            image_path: Path to potentially modified image
            reference_path: Path to original watermarked image
            metadata: Metadata from embedding process
            
        Returns:
            Tuple of (extracted_text, recovery_details)
        """
        pass


class BlindWatermarkAdapter(WatermarkAdapter):
    """Adapter for blind_watermark library"""
    
    def __init__(self, password_img: int = 1, password_wm: int = 1):
        self.password_img = password_img
        self.password_wm = password_wm
    
    def embed(self, image_path: str, watermark_text: str, output_path: str) -> Dict[str, Any]:
        from blind_watermark import WaterMark
        
        bwm = WaterMark(password_img=self.password_img, password_wm=self.password_wm)
        bwm.read_img(image_path)
        bwm.read_wm(watermark_text, mode='str')
        bwm.embed(output_path)
        
        return {
            "wm_len": len(bwm.wm_bit),
            "wm_text": watermark_text
        }
    
    def extract(self, image_path: str, metadata: Dict[str, Any]) -> Optional[str]:
        from blind_watermark import WaterMark
        
        bwm = WaterMark(password_img=self.password_img, password_wm=self.password_wm)
        try:
            extracted = bwm.extract(image_path, wm_shape=metadata["wm_len"], mode='str')
            return extracted if extracted == metadata["wm_text"] else None
        except Exception:
            return None
    
    def supports_recovery(self) -> bool:
        return True
    
    def recover_and_extract(self, image_path: str, reference_path: str, metadata: Dict[str, Any]) -> Tuple[Optional[str], Dict[str, Any]]:
        from blind_watermark import WaterMark
        from blind_watermark.recover import estimate_crop_parameters, recover_crop
        
        details = {}
        try:
            # Estimate crop parameters
            (x1, y1, x2, y2), image_o_shape, score, scale_infer = estimate_crop_parameters(
                original_file=reference_path,
                template_file=image_path,
                scale=(0.5, 2.0),
                search_num=120
            )
            
            details["estimated"] = {
                "x1": int(x1), "y1": int(y1), "x2": int(x2), "y2": int(y2),
                "score": float(score), "scale": float(scale_infer)
            }
            
            # Recover image
            recovered_path = tempfile.mktemp(suffix=".png")
            recover_crop(
                template_file=image_path,
                output_file_name=recovered_path,
                loc=(x1, y1, x2, y2),
                image_o_shape=image_o_shape
            )
            
            # Extract from recovered image
            bwm = WaterMark(password_img=self.password_img, password_wm=self.password_wm)
            extracted = bwm.extract(recovered_path, wm_shape=metadata["wm_len"], mode='str')
            
            # Cleanup
            if os.path.exists(recovered_path):
                os.remove(recovered_path)
            
            if extracted == metadata["wm_text"]:
                details["recovered"] = True
                return extracted, details
            else:
                return None, details
                
        except Exception as e:
            details["recovery_error"] = str(e)
            return None, details


class TrustmarkAdapter(WatermarkAdapter):
    """Adapter for Adobe Trustmark (placeholder implementation)"""
    
    def __init__(self, verbose=True, model_type='Q'):
        self.verbose = verbose
        self.model_type = model_type
    
    def embed(self, image_path: str, watermark_text: str, output_path: str) -> Dict[str, Any]:
        from trustmark import TrustMark
        from PIL import Image

        tm = TrustMark(verbose=self.verbose, model_type=self.model_type)
        cover = Image.open(image_path).convert('RGB')
        tm.encode(cover, watermark_text).save(output_path)

        return {
            "wm_len": 0,
            "wm_text": watermark_text
        }


    def extract(self, image_path: str, metadata: Dict[str, Any]) -> Optional[str]:
        from trustmark import TrustMark
        from PIL import Image

        tm = TrustMark(verbose=self.verbose, model_type=self.model_type)
        cover = Image.open(image_path).convert('RGB')
        wm_secret, wm_present, wm_schema = tm.decode(cover)

        if wm_present:
            return wm_secret
        else:
            return None
    
    def supports_recovery(self) -> bool:
        return False
    
    def recover_and_extract(self, image_path: str, reference_path: str, metadata: Dict[str, Any]) -> Tuple[Optional[str], Dict[str, Any]]:
        # TODO: Implement Trustmark recovery if supported
        raise NotImplementedError("Adobe Trustmark recovery not yet implemented")


def create_watermark_adapter(adapter_type: str, **kwargs) -> WatermarkAdapter:
    """Factory function to create watermark adapters"""
    
    adapters = {
        "blind_watermark": BlindWatermarkAdapter,
        "trustmark": TrustmarkAdapter,
    }
    
    if adapter_type not in adapters:
        raise ValueError(f"Unknown adapter type: {adapter_type}. Available: {list(adapters.keys())}")
    
    return adapters[adapter_type](**kwargs)
