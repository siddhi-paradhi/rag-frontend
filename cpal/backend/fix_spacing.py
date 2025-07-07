"""
Multilingual text spacing utilities for production use.

This module provides efficient text spacing fixes for various languages
with proper error handling, logging, and performance optimizations.
"""

import logging
import re
from functools import lru_cache
from typing import Optional, Dict, Callable

# Configure logging
logger = logging.getLogger(__name__)

# Language-specific configurations
ARABIC_PUNCTUATION_FIXES = [
    (re.compile(r'،(?!\s)'), '، '),  # Add space after Arabic comma
    (re.compile(r'؟(?!\s)'), '؟ '),  # Add space after Arabic question mark
    (re.compile(r'\.(?!\s)(?!\d)'), '. '),  # Add space after period (not in numbers)
    (re.compile(r'\s+'), ' '),  # Normalize multiple spaces
]

class SpacingProcessor:
    """Handles text spacing fixes for multiple languages with caching and error handling."""
    
    def __init__(self):
        self._hindi_tokenizer = None
        self._hindi_available = None
        
    @property
    def hindi_tokenizer(self):
        """Lazy loading of Hindi tokenizer to avoid import overhead."""
        if self._hindi_tokenizer is None and self._hindi_available is not False:
            try:
                from indicnlp.tokenize import indic_tokenize
                self._hindi_tokenizer = indic_tokenize
                self._hindi_available = True
                logger.info("Hindi tokenizer loaded successfully")
            except ImportError as e:
                logger.warning(f"Hindi tokenizer not available: {e}")
                self._hindi_available = False
            except Exception as e:
                logger.error(f"Unexpected error loading Hindi tokenizer: {e}")
                self._hindi_available = False
        return self._hindi_tokenizer
    
    def fix_hindi_spacing(self, text: str) -> str:
        """
        Fix spacing for Hindi text using indicnlp tokenizer.
        
        Args:
            text: Input Hindi text
            
        Returns:
            Text with corrected spacing, or original text if processing fails
        """
        if not text or not text.strip():
            return text
            
        # Check if text actually contains Hindi characters
        if not re.search(r'[\u0900-\u097F]', text):
            logger.debug("No Hindi characters detected, returning original text")
            return text
            
        tokenizer = self.hindi_tokenizer
        if not tokenizer:
            logger.warning("Hindi tokenizer not available, returning original text")
            return text
            
        try:
            tokens = tokenizer.trivial_tokenize(text, lang='hi')
            if not tokens:
                return text
            return ' '.join(token for token in tokens if token.strip())
        except Exception as e:
            logger.error(f"Error processing Hindi text: {e}")
            return text
    
    @lru_cache(maxsize=1000)
    def fix_arabic_spacing(self, text: str) -> str:
        """
        Fix spacing for Arabic text using regex patterns.
        
        Args:
            text: Input Arabic text
            
        Returns:
            Text with corrected spacing
        """
        if not text or not text.strip():
            return text
            
        # Check if text actually contains Arabic characters
        if not re.search(r'[\u0600-\u06FF\u0750-\u077F]', text):
            logger.debug("No Arabic characters detected, returning original text")
            return text
        
        result = text
        try:
            for pattern, replacement in ARABIC_PUNCTUATION_FIXES:
                result = pattern.sub(replacement, result)
            return result.strip()
        except Exception as e:
            logger.error(f"Error processing Arabic text: {e}")
            return text
    
    @lru_cache(maxsize=500)
    def fix_english_spacing(self, text: str) -> str:
        """
        Fix spacing for English text.
        
        Args:
            text: Input English text
            
        Returns:
            Text with corrected spacing
        """
        if not text or not text.strip():
            return text
            
        try:
            # Basic English punctuation spacing fixes
            result = re.sub(r'([.!?])(?!\s|$)', r'\1 ', text)  # Space after sentence endings
            result = re.sub(r'([,;:])(?!\s)', r'\1 ', result)  # Space after commas, semicolons, colons
            result = re.sub(r'\s+', ' ', result)  # Normalize multiple spaces
            return result.strip()
        except Exception as e:
            logger.error(f"Error processing English text: {e}")
            return text


# Global processor instance
_processor = SpacingProcessor()

# Language handler mapping
LANGUAGE_HANDLERS: Dict[str, Callable[[str], str]] = {
    'hi': _processor.fix_hindi_spacing,
    'hindi': _processor.fix_hindi_spacing,
    'ar': _processor.fix_arabic_spacing,
    'arabic': _processor.fix_arabic_spacing,
    'en': _processor.fix_english_spacing,
    'english': _processor.fix_english_spacing,
}

def fix_spacing_for_lang(lang: str, text: str) -> str:
    """
    Fix text spacing for a specific language.
    
    Args:
        lang: Language code ('hi', 'ar', 'en', etc.) or language name
        text: Input text to process
        
    Returns:
        Text with corrected spacing
        
    Raises:
        ValueError: If language is not supported
    """
    if not isinstance(text, str):
        raise ValueError("Text must be a string")
    
    if not text or not text.strip():
        return text
    
    # Normalize language code
    lang_lower = lang.lower().strip()
    
    if lang_lower not in LANGUAGE_HANDLERS:
        supported_langs = ', '.join(LANGUAGE_HANDLERS.keys())
        raise ValueError(f"Unsupported language: {lang}. Supported languages: {supported_langs}")
    
    try:
        return LANGUAGE_HANDLERS[lang_lower](text)
    except Exception as e:
        logger.error(f"Error processing text for language {lang}: {e}")
        return text

def auto_detect_and_fix_spacing(text: str) -> str:
    """
    Automatically detect language and fix spacing.
    
    Args:
        text: Input text
        
    Returns:
        Text with corrected spacing based on detected language
    """
    if not text or not text.strip():
        return text
    
    # Simple language detection based on character sets
    if re.search(r'[\u0900-\u097F]', text):
        return fix_spacing_for_lang('hi', text)
    elif re.search(r'[\u0600-\u06FF\u0750-\u077F]', text):
        return fix_spacing_for_lang('ar', text)
    else:
        return fix_spacing_for_lang('en', text)

def batch_fix_spacing(texts: list, lang: str) -> list:
    """
    Fix spacing for multiple texts efficiently.
    
    Args:
        texts: List of texts to process
        lang: Language code
        
    Returns:
        List of texts with corrected spacing
    """
    if not texts:
        return []
    
    return [fix_spacing_for_lang(lang, text) for text in texts if isinstance(text, str)]

# Backward compatibility functions
def fix_hindi_spacing(text: str) -> str:
    """Backward compatibility wrapper for Hindi spacing fix."""
    return _processor.fix_hindi_spacing(text)

def fix_arabic_spacing(text: str) -> str:
    """Backward compatibility wrapper for Arabic spacing fix."""
    return _processor.fix_arabic_spacing(text)

# Clear cache function for memory management
def clear_cache():
    """Clear all LRU caches to free memory."""
    _processor.fix_arabic_spacing.cache_clear()
    _processor.fix_english_spacing.cache_clear()
    logger.info("Spacing processor caches cleared")

if __name__ == "__main__":
    # Example usage and testing
    test_cases = [
        ("hi", "यह एक परीक्षण वाक्य है।"),
        ("ar", "هذا نص تجريبي،هل يعمل؟نعم."),
        ("en", "This is a test,does it work?Yes.")
    ]
    
    for lang, text in test_cases:
        try:
            result = fix_spacing_for_lang(lang, text)
            print(f"{lang}: {text} -> {result}")
        except Exception as e:
            print(f"Error processing {lang}: {e}")