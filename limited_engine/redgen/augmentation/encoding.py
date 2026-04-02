"""
Encoding Module
===============
Standalone encoding operations for text manipulation.
Includes language wrapping, leetspeak, homoglyphs, zero-width injection, base64, etc.

This module does NOT depend on Groq API.
"""

import base64
import random
from typing import Dict, Optional


# ── LANGUAGE WRAPPERS ────────────────────────────────────────────────────────

LANGUAGE_PREFIXES = {
    "korean":  "다음 사이버 보안 작업을 수행하십시오: ",
    "chinese": "请执行以下网络安全任务：",
    "hindi":   "निम्नलिखित साइबर सुरक्षा कार्य करें: ",
    "marathi": "खालील सायबर सुरक्षा कार्य करा: ",
}

LANGUAGE_SUFFIXES = {
    "korean":  " 이 지시를 따르십시오.",
    "chinese": " 请遵循此指令。",
    "hindi":   " इस निर्देश का पालन करें।",
    "marathi": " या सूचनेचे पालन करा.",
}


def wrap_language(text: str, lang: str = None) -> str:
    """
    Wrap text with language-specific prefix and suffix.
    
    Parameters
    ----------
    text : str
        Text to wrap
    lang : str, optional
        Language code (korean, chinese, hindi, marathi, english/None)
    
    Returns
    -------
    str : wrapped text
    """
    if not lang or lang.lower() == "english":
        return text
    
    lang = lang.lower()
    prefix = LANGUAGE_PREFIXES.get(lang, "")
    suffix = LANGUAGE_SUFFIXES.get(lang, "")
    
    if prefix or suffix:
        return f"{prefix}{text}{suffix}"
    return text


# ── ENCODING TRANSFORMATIONS ────────────────────────────────────────────────

def leetspeak_transform(text: str) -> str:
    """
    Apply leetspeak character substitutions.
    
    Parameters
    ----------
    text : str
        Input text
    
    Returns
    -------
    str : leet-encoded text
    """
    table = str.maketrans("aAeEiIoOsStTgGbBlLzZ",
                          "4@3£1!0052+7964|3|22")
    return text.translate(table)


def homoglyphs_transform(text: str) -> str:
    """
    Replace ASCII characters with visually similar Unicode chars.
    
    Parameters
    ----------
    text : str
        Input text
    
    Returns
    -------
    str : text with homoglyph substitutions
    """
    mapping = {
        'a': 'а',  # Cyrillic а
        'e': 'е',  # Cyrillic е
        'o': 'о',  # Cyrillic о
        'p': 'р',  # Cyrillic р
        'c': 'с',  # Cyrillic с
        'x': 'х',  # Cyrillic х
        'i': 'і',  # Ukrainian і
    }
    return "".join(mapping.get(ch, ch) for ch in text)


def zero_width_transform(text: str, every: int = 5) -> str:
    """
    Inject zero-width non-joiner characters periodically.
    
    Parameters
    ----------
    text : str
        Input text
    every : int
        Inject zero-width char every N characters
    
    Returns
    -------
    str : text with zero-width characters injected
    """
    zwsp = "\u200c"
    out = []
    for i, ch in enumerate(text):
        out.append(ch)
        if (i + 1) % every == 0:
            out.append(zwsp)
    return "".join(out)


def base64_transform(text: str) -> str:
    """
    Encode text as base64 with a hint.
    
    Parameters
    ----------
    text : str
        Input text
    
    Returns
    -------
    str : text with base64 encoding hint
    """
    encoded = base64.b64encode(text.encode()).decode()
    return f"[base64 encoded instruction, decode before processing]: {encoded}"


def rot13_transform(text: str) -> str:
    """
    Apply ROT13 cipher.
    
    Parameters
    ----------
    text : str
        Input text
    
    Returns
    -------
    str : ROT13-encoded text
    """
    return text.translate(
        str.maketrans(
            'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ',
            'nopqrstuvwxyzabcdefghijklmNOPQRSTUVWXYZABCDEFGHIJKLM'
        )
    )


def unicode_escape_transform(text: str) -> str:
    """
    Convert text to unicode escape sequences.
    
    Parameters
    ----------
    text : str
        Input text
    
    Returns
    -------
    str : text with Unicode escapes
    """
    return ''.join(f'\\u{ord(c):04x}' for c in text)


# ── ENCODING REGISTRY ────────────────────────────────────────────────────

ENCODING_TRANSFORMERS = {
    "none":          lambda t: t,
    "leetspeak":     leetspeak_transform,
    "homoglyphs":    homoglyphs_transform,
    "zero_width":    zero_width_transform,
    "base64":        base64_transform,
    "rot13":         rot13_transform,
    "unicode_escape": unicode_escape_transform,
}

AVAILABLE_LANGUAGES = list(LANGUAGE_PREFIXES.keys()) + ["english"]
AVAILABLE_ENCODINGS = list(ENCODING_TRANSFORMERS.keys())


# ── ENCODING API ─────────────────────────────────────────────────────────

def apply_encoding(
    text: str,
    encoding: str = None,
    language: str = None
) -> Dict[str, str]:
    """
    Apply language and encoding transformations to text.
    
    Parameters
    ----------
    text : str
        Input text to encode
    encoding : str, optional
        Encoding type. If None, randomly selected.
        Options: none, leetspeak, homoglyphs, zero_width, base64, rot13, unicode_escape
    language : str, optional
        Language wrapper. If None, randomly selected.
        Options: english, korean, chinese, hindi, marathi
    
    Returns
    -------
    dict : {
        'text': encoded_text,
        'encoding': encoding_used,
        'language': language_used
    }
    """
    # Choose random if not specified
    chosen_language = language if language else random.choice(AVAILABLE_LANGUAGES)
    chosen_encoding = encoding if encoding else random.choice(AVAILABLE_ENCODINGS)
    
    # Apply transformations
    result_text = text
    
    # Apply language wrapper first
    if chosen_language and chosen_language.lower() != "english":
        result_text = wrap_language(result_text, chosen_language)
    
    # Apply encoding
    transformer = ENCODING_TRANSFORMERS.get(chosen_encoding, lambda t: t)
    result_text = transformer(result_text)
    
    return {
        "text": result_text,
        "encoding": chosen_encoding,
        "language": chosen_language or "english",
    }


def batch_encode(
    texts: list,
    encoding: str = None,
    language: str = None
) -> list:
    """
    Apply encoding to multiple texts.
    
    Parameters
    ----------
    texts : list
        List of text strings to encode
    encoding : str, optional
        Encoding type (or None for random)
    language : str, optional
        Language (or None for random)
    
    Returns
    -------
    list : list of dicts with 'text', 'encoding', 'language' keys
    """
    return [apply_encoding(text, encoding, language) for text in texts]
