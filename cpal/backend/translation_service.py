import logging
import re
import time
from functools import lru_cache
from typing import Dict, List, Optional, Tuple, Union
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
import threading

try:
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError
    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False

try:
    from backend.utils_hindi_spacing import fix_hindi_spacing as external_hindi_fix
except ImportError:
    external_hindi_fix = None

try:
    from langdetect import detect as langdetect_detect
    from langdetect.lang_detect_exception import LangDetectException
    LANGDETECT_AVAILABLE = True
except ImportError:
    LANGDETECT_AVAILABLE = False

logger = logging.getLogger(__name__)

@dataclass
class LanguageConfig:
    """Configuration for each supported language."""
    name: str
    aws_code: str
    rtl: bool = False 
    script_unicode_range: Optional[str] = None
    spacing_rules: Optional[Dict] = None

class TextProcessor:
    """Advanced text processing for multilingual content."""
    
    SCRIPT_RANGES = {
        'arabic': r'[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]',
        'hindi': r'[\u0900-\u097F]',
        'chinese': r'[\u4E00-\u9FFF\u3400-\u4DBF\u20000-\u2A6DF]',
        'latin': r'[a-zA-Z]',
        'digits': r'[0-9]',
        'punctuation': r'[.,;:!?।؟،]'
    }
    
    ARABIC_RULES = [
        (re.compile(r'،(?!\s)'), '، '), 
        (re.compile(r'؟(?!\s)'), '؟ '),  
        (re.compile(r'؛(?!\s)'), '؛ '),  
        (re.compile(r'(\d)([^\d\s])'), r'\1 \2'),  # Space after numbers
        (re.compile(r'([^\d\s])(\d)'), r'\1 \2'),  # Space before numbers
        (re.compile(r'\s+'), ' '),  # Normalize multiple spaces
    ]
    
    # Hindi punctuation and spacing rules
    HINDI_RULES = [
        (re.compile(r'([।])([^\s])'), r'\1 \2'),  # Hindi full stop spacing
        (re.compile(r'([,])([^\s])'), r'\1 \2'),   # Comma spacing
        (re.compile(r'([?!])([^\s])'), r'\1 \2'),  # Question/exclamation spacing
        (re.compile(r'([\u0900-\u097F])([a-zA-Z0-9])'), r'\1 \2'),  # Hindi-Latin boundary
        (re.compile(r'([a-zA-Z0-9])([\u0900-\u097F])'), r'\1 \2'),  # Latin-Hindi boundary
        (re.compile(r'\s+'), ' '),  # Normalize multiple spaces
    ]
    
    # Chinese punctuation spacing rules
    CHINESE_RULES = [
        (re.compile(r'([，。！？；：])([^\s])'), r'\1 \2'),  # Chinese punctuation spacing
        (re.compile(r'([\u4E00-\u9FFF])([a-zA-Z])'), r'\1 \2'),  # Chinese-Latin boundary
        (re.compile(r'([a-zA-Z])([\u4E00-\u9FFF])'), r'\1 \2'),  # Latin-Chinese boundary
        (re.compile(r'\s+'), ' '),  # Normalize multiple spaces
    ]
    
    @classmethod
    @lru_cache(maxsize=1000)
    def fix_arabic_spacing(cls, text: str) -> str:
        """Enhanced Arabic text spacing and readability fixes."""
        if not text or not cls._contains_script(text, 'arabic'):
            return text
        
        result = text.strip()
        try:
            # Apply Arabic-specific rules
            for pattern, replacement in cls.ARABIC_RULES:
                result = pattern.sub(replacement, result)
            
            # Fix Arabic-English mixed text issues
            result = re.sub(r'([a-zA-Z])([\u0600-\u06FF])', r'\1 \2', result)
            result = re.sub(r'([\u0600-\u06FF])([a-zA-Z])', r'\1 \2', result)
            
            # Normalize Arabic numerals and punctuation
            result = cls._normalize_arabic_numerals(result)
            
            return result.strip()
        except Exception as e:
            logger.error(f"Error processing Arabic text: {e}")
            return text
    
    @classmethod
    @lru_cache(maxsize=1000)
    def fix_hindi_spacing(cls, text: str) -> str:
        """Enhanced Hindi text spacing and readability fixes."""
        if not text or not cls._contains_script(text, 'hindi'):
            return text
        
        result = text.strip()
        try:
            # Apply external Hindi spacing fix if available
            if external_hindi_fix:
                result = external_hindi_fix(result)
            
            # Apply Hindi-specific rules
            for pattern, replacement in cls.HINDI_RULES:
                result = pattern.sub(replacement, result)
            
            # Fix word joining issues in Hindi
            result = cls._fix_hindi_word_boundaries(result)
            
            return result.strip()
        except Exception as e:
            logger.error(f"Error processing Hindi text: {e}")
            return text
    
    @classmethod
    @lru_cache(maxsize=1000)
    def fix_chinese_spacing(cls, text: str) -> str:
        """Enhanced Chinese text spacing and readability fixes."""
        if not text or not cls._contains_script(text, 'chinese'):
            return text
        
        result = text.strip()
        try:
            # Apply Chinese-specific rules
            for pattern, replacement in cls.CHINESE_RULES:
                result = pattern.sub(replacement, result)
            
            # Handle Traditional vs Simplified Chinese characters
            result = cls._normalize_chinese_punctuation(result)
            
            return result.strip()
        except Exception as e:
            logger.error(f"Error processing Chinese text: {e}")
            return text
    
    @classmethod
    def _contains_script(cls, text: str, script: str) -> bool:
        """Check if text contains characters from specified script."""
        pattern = cls.SCRIPT_RANGES.get(script, '')
        return bool(re.search(pattern, text)) if pattern else False
    
    @classmethod
    def _normalize_arabic_numerals(cls, text: str) -> str:
        """Normalize Arabic-Indic numerals to standard Arabic numerals."""
        arabic_to_standard = {
            '٠': '0', '١': '1', '٢': '2', '٣': '3', '٤': '4',
            '٥': '5', '٦': '6', '٧': '7', '٨': '8', '٩': '9'
        }
        for arabic, standard in arabic_to_standard.items():
            text = text.replace(arabic, standard)
        return text
    
    @classmethod
    def _fix_hindi_word_boundaries(cls, text: str) -> str:
        """Fix word boundary issues in Hindi text."""
        words = text.split()
        processed_words = []
        
        for word in words:
            if len(word) > 25 and cls._contains_script(word, 'hindi'):
                # Split overly long words that might be incorrectly joined
                word = re.sub(r'([\u0900-\u097F]{10,})([a-zA-Z]+)', r'\1 \2', word)
                word = re.sub(r'([a-zA-Z]+)([\u0900-\u097F]{10,})', r'\1 \2', word)
            processed_words.append(word)
        
        return ' '.join(processed_words)
    
    @classmethod
    def _normalize_chinese_punctuation(cls, text: str) -> str:
        """Normalize Chinese punctuation marks."""
        # Common Chinese punctuation normalizations
        normalizations = {
            '．': '。',  # Full stop
            '！': '!',   # Exclamation
            '？': '?',   # Question mark
            '，': ',',   # Comma (optional - keep Chinese comma)
        }
        
        for chinese, normalized in normalizations.items():
            if chinese != '，':  # Keep Chinese comma as is
                text = text.replace(chinese, normalized)
        
        return text

class TranslationService:
    """Production-ready translation service with enhanced multilingual support."""
    
    def __init__(self, region_name: str = "us-east-1", max_workers: int = 5):
        """Initialize translation service."""
        self.region_name = region_name
        self.max_workers = max_workers
        self._lock = threading.Lock()
        
        # Enhanced language configuration
        self.lang_config = {
            "en": LanguageConfig("English", "en"),
            "ar": LanguageConfig("Arabic", "ar", rtl=True, script_unicode_range="arabic"),
            "hi": LanguageConfig("Hindi", "hi", script_unicode_range="hindi"),
            "zh": LanguageConfig("Chinese (Simplified)", "zh", script_unicode_range="chinese"),
            "zh-cn": LanguageConfig("Chinese (Simplified)", "zh", script_unicode_range="chinese"),
            "zh-tw": LanguageConfig("Chinese (Traditional)", "zh-TW", script_unicode_range="chinese"),
        }
        
        # Initialize AWS client
        self.translate_client = self._initialize_aws_client()
        self.text_processor = TextProcessor()
        
        # Cache for translation results
        self._translation_cache = {}
        self._cache_max_size = 10000
        
        # Test the service
        self._health_status = self._perform_health_check()
        
    def _initialize_aws_client(self) -> Optional[object]:
        """Initialize AWS Translate client with proper error handling."""
        if not BOTO3_AVAILABLE:
            logger.warning("boto3 not available - translation service will be limited")
            return None
        
        try:
            client = boto3.client(
                "translate",
                region_name=self.region_name,
                config=boto3.session.Config(
                    retries={'max_attempts': 3, 'mode': 'adaptive'},
                    max_pool_connections=self.max_workers
                )
            )
            logger.info("AWS Translate client initialized successfully")
            return client
        except Exception as e:
            logger.error(f"Failed to initialize AWS Translate client: {e}")
            return None
    
    @lru_cache(maxsize=500)
    def detect_language(self, text: str) -> str:
        """Enhanced language detection with fallback mechanisms."""
        if not text or len(text.strip()) < 3:
            return "en"
        
        # Use character-based detection for better accuracy
        script_scores = self._analyze_script_distribution(text)
        
        if LANGDETECT_AVAILABLE:
            try:
                detected = langdetect_detect(text)
                # Validate detection against script analysis
                if self._validate_detection(detected, script_scores):
                    return self._normalize_language_code(detected)
            except (LangDetectException, Exception) as e:
                logger.debug(f"Language detection failed: {e}")
        
        # Fallback to script-based detection
        return self._detect_by_script(script_scores)
    
    def _analyze_script_distribution(self, text: str) -> Dict[str, float]:
        """Analyze script distribution in text for language detection."""
        total_chars = len(re.sub(r'\s+', '', text))
        if total_chars == 0:
            return {}
        
        script_counts = {}
        for script, pattern in TextProcessor.SCRIPT_RANGES.items():
            count = len(re.findall(pattern, text))
            script_counts[script] = count / total_chars if total_chars > 0 else 0
        
        return script_counts
    
    def _validate_detection(self, detected_lang: str, script_scores: Dict[str, float]) -> bool:
        """Validate language detection against script analysis."""
        lang_config = self.lang_config.get(detected_lang)
        if not lang_config or not lang_config.script_unicode_range:
            return True  # Can't validate, assume correct
        
        expected_script = lang_config.script_unicode_range
        script_score = script_scores.get(expected_script, 0)
        if expected_script == 'arabic':
            # Arabic detection requires higher confidence
            return script_score >= 0.5
        elif expected_script == 'hindi':
            # Hindi detection requires moderate confidence
            return script_score >= 0.4
        elif expected_script == 'chinese':
            # Chinese detection requires moderate confidence
            return script_score >= 0.4
    
    def _detect_by_script(self, script_scores: Dict[str, float]) -> str:
        """Detect language based on script distribution."""
        max_script = max(script_scores.items(), key=lambda x: x[1], default=('latin', 0))
        
        script_to_lang = {
            'arabic': 'ar',
            'hindi': 'hi',
            'chinese': 'zh',
            'latin': 'en'
        }
        
        return script_to_lang.get(max_script[0], 'en')
    
    def _normalize_language_code(self, lang_code: str) -> str:
        """Normalize language codes to supported format."""
        normalizations = {
            'zh-cn': 'zh',
            'zh-Hans': 'zh',
            'zh-Hant': 'zh-tw'
        }
        return normalizations.get(lang_code, lang_code)
    
    def translate_text(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
        enhance_readability: bool = True
    ) -> str:
        """
        Translate text with enhanced readability processing.
        
        Args:
            text: Text to translate
            source_lang: Source language code
            target_lang: Target language code 
            enhance_readability: Apply post-processing for better readability
        """
        if not text or not text.strip():
            return text
        
        # Check cache first
        cache_key = f"{hash(text)}_{source_lang}_{target_lang}"
        if cache_key in self._translation_cache:
            return self._translation_cache[cache_key]
        
        # Normalize language codes
        source_lang = self._normalize_language_code(source_lang)
        target_lang = self._normalize_language_code(target_lang)
        
        if source_lang == target_lang:
            result = self._enhance_text_readability(text, target_lang) if enhance_readability else text
            self._cache_translation(cache_key, result)
            return result
        
        if not self.translate_client:
            logger.warning("Translation service not available")
            return text
        
        try:
            # Get AWS language codes
            src_config = self.lang_config.get(source_lang)
            tgt_config = self.lang_config.get(target_lang)
            
            if not src_config or not tgt_config:
                logger.error(f"Unsupported language pair: {source_lang} -> {target_lang}")
                return text
            
            # Perform translation
            response = self.translate_client.translate_text(
                Text=text,
                SourceLanguageCode=src_config.aws_code,
                TargetLanguageCode=tgt_config.aws_code
            )
            
            result = response.get("TranslatedText", text)
            
            # Apply readability enhancements
            if enhance_readability:
                result = self._enhance_text_readability(result, target_lang)
                result = re.sub(r'[<>[\]{}0-9A-Z]{2,}', '', result)
            
            # Cache the result
            self._cache_translation(cache_key, result)
            
            logger.info(f"Translated text from {source_lang} to {target_lang}")
            return result
            
        except (ClientError, NoCredentialsError) as e:
            logger.error(f"AWS Translation error: {e}")
            return text
        except Exception as e:
            logger.error(f"Translation error: {e}")
            return text
    
    def _enhance_text_readability(self, text: str, lang: str) -> str:
        """Apply language-specific readability enhancements."""
        if lang == "ar":
            return TextProcessor.fix_arabic_spacing(text)
        elif lang == "hi":
            return TextProcessor.fix_hindi_spacing(text)
        elif lang in ["zh", "zh-cn", "zh-tw"]:
            return TextProcessor.fix_chinese_spacing(text)
        else:
            # Basic cleanup for other languages
            return re.sub(r'\s+', ' ', text).strip()
    
    def _cache_translation(self, key: str, value: str):
        """Thread-safe caching with size limit."""
        with self._lock:
            if len(self._translation_cache) >= self._cache_max_size:
                # Remove oldest entries (simple FIFO)
                oldest_keys = list(self._translation_cache.keys())[:100]
                for old_key in oldest_keys:
                    del self._translation_cache[old_key]
            
            self._translation_cache[key] = value
    
    def translate_if_needed(self, text: str, target_lang: str = "en") -> Tuple[str, str]:
        """
        Translate text to target language if needed.
        
        Returns:
            Tuple of (translated_text, detected_source_language)
        """
        detected_lang = self.detect_language(text)
        
        if detected_lang == target_lang:
            enhanced_text = self._enhance_text_readability(text, detected_lang)
            return enhanced_text, detected_lang
        
        translated = self.translate_text(text, detected_lang, target_lang)
        return translated, detected_lang
    
    def batch_translate(
        self,
        texts: List[str],
        source_lang: str,
        target_lang: str
    ) -> List[str]:
        """Translate multiple texts efficiently using thread pool."""
        if not texts:
            return []
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = [
                executor.submit(self.translate_text, text, source_lang, target_lang)
                for text in texts
            ]
            return [future.result() for future in futures]
    
    def get_enhanced_followups(self, lang: str = "en") -> List[str]:
        """Get culturally appropriate follow-up questions with proper formatting."""
        followups = {
            "en": [
                "What services does Commedia Solutions offer?",
                "How can I contact Commedia Solutions?",
                "Tell me about Commedia's expertise and experience.",
                "What industries does Commedia Solutions serve?",
                "Can you provide pricing information?"
            ],
            "ar": [
                "ما هي الخدمات التي تقدمها شركة كوميديا سوليوشنز؟",
                "كيف يمكنني التواصل مع كوميديا سوليوشنز؟",
                "أخبرني عن خبرة ومهارات شركة كوميديا.",
                "ما هي الصناعات التي تخدمها كوميديا سوليوشنز؟",
                "هل يمكنك تقديم معلومات حول الأسعار؟"
            ],
            "hi": [
                "कॉमेडिया सॉल्यूशंस कौन सी सेवाएं प्रदान करता है?",
                "मैं कॉमेडिया सॉल्यूशंस से कैसे संपर्क कर सकता हूं?",
                "कॉमेडिया की विशेषज्ञता और अनुभव के बारे में बताएं।",
                "कॉमेडिया सॉल्यूशंस कौन से उद्योगों की सेवा करता है?",
                "क्या आप मूल्य निर्धारण की जानकारी प्रदान कर सकते हैं?"
            ],
            "zh": [
                "Commedia Solutions 提供什么服务？",
                "我如何联系 Commedia Solutions？",
                "告诉我 Commedia 的专业知识和经验。",
                "Commedia Solutions 为哪些行业提供服务？",
                "您能提供价格信息吗？"
            ]
        }
        
        base_followups = followups.get(lang, followups["en"])
        
        # Apply language-specific formatting
        return [self._enhance_text_readability(text, lang) for text in base_followups]
    
    def _perform_health_check(self) -> Dict[str, Union[bool, int, str]]:
        """Comprehensive health check of translation service."""
        status = {
            "aws_translate_available": False,
            "language_detection_available": LANGDETECT_AVAILABLE,
            "supported_languages": len(self.lang_config),
            "cache_size": 0,
            "last_check": time.time(),
            "status": "unknown"
        }
        
        if self.translate_client:
            try:
                test_result = self.translate_client.translate_text(
                    Text="Hello world",
                    SourceLanguageCode="en",
                    TargetLanguageCode="es"
                )
                status["aws_translate_available"] = bool(test_result.get("TranslatedText"))
                status["status"] = "healthy"
            except Exception as e:
                logger.warning(f"Health check failed: {e}")
                status["status"] = "degraded"
        else:
            status["status"] = "limited"
        
        status["cache_size"] = len(self._translation_cache)
        return status
    
    def get_service_info(self) -> Dict:
        """Get comprehensive service information."""
        return {
            "supported_languages": {
                code: {"name": config.name, "rtl": config.rtl, "aws_code": config.aws_code}
                for code, config in self.lang_config.items()
            },
            "features": {
                "enhanced_readability": True,
                "batch_translation": True,
                "language_detection": LANGDETECT_AVAILABLE,
                "caching": True,
                "health_monitoring": True
            },
            "health_status": self._health_status,
            "cache_stats": {
                "size": len(self._translation_cache),
                "max_size": self._cache_max_size
            }
        }
    
    def clear_cache(self):
        """Clear translation cache to free memory."""
        with self._lock:
            self._translation_cache.clear()
            logger.info("Translation cache cleared")

# Singleton instance for global use
_translation_service = None
_service_lock = threading.Lock()

def get_translation_service(**kwargs) -> TranslationService:
    """Get singleton translation service instance."""
    global _translation_service
    
    if _translation_service is None:
        with _service_lock:
            if _translation_service is None:
                _translation_service = TranslationService(**kwargs)
    
    return _translation_service

# Convenience functions for backward compatibility
def translate_text(text: str, source_lang: str, target_lang: str) -> str:
    """Convenience function for text translation."""
    service = get_translation_service()
    return service.translate_text(text, source_lang, target_lang)

def detect_language(text: str) -> str:
    """Convenience function for language detection."""
    service = get_translation_service()
    return service.detect_language(text)

if __name__ == "__main__":
    # Example usage and testing
    service = TranslationService()
    
    test_cases = [
        ("Hello world", "en", "ar"),
        ("مرحبا بالعالم", "ar", "en"),
        ("नमस्ते दुनिया", "hi", "en"),
        ("你好世界", "zh", "en"),
    ]
    
    print("Translation Service Test Results:")
    print("=" * 50)
    
    for text, src, tgt in test_cases:
        try:
            result = service.translate_text(text, src, tgt)
            detected = service.detect_language(text)
            print(f"Text: {text}")
            print(f"Detected: {detected} | {src} -> {tgt}")
            print(f"Result: {result}")
            print("-" * 30)
        except Exception as e:
            print(f"Error translating '{text}': {e}")
    
    # Health check
    health = service._perform_health_check()
    print(f"\nService Health: {health}")