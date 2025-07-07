def fix_hindi_spacing(text: str) -> str:
    """
    Fixes spacing in Hindi sentences using Indic NLP tokenization.
    If library is not available or fails, returns the original text.
    """
    try:
        from indicnlp.tokenize import indic_tokenize
        tokens = indic_tokenize.trivial_tokenize(text, lang='hi')
        spaced_text = ' '.join(tokens)
        return spaced_text
    except Exception as e:
        import logging
        logging.warning(f"Hindi spacing fix failed: {e}")
        return text
