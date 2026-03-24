"""
Domain and Payload Loader
==========================
Dynamically load templates and payloads from the redgen_payloads directory.
Handles domain selection and payload extraction.
"""

import os
import importlib.util
import sys
from pathlib import Path
from typing import List, Dict, Optional, Any


def get_available_domains() -> list:
    """
    Get list of available domains from the domains directory.
    
    Returns
    -------
    list : domain names (directory names in domains/)
    """
    domains_dir = Path(__file__).parent / "domains"
    if not domains_dir.exists():
        return []
    
    domains = [d.name for d in domains_dir.iterdir() 
               if d.is_dir() and not d.name.startswith('_')]
    return sorted(domains)


def load_payloads_from_domain(domain: str) -> list:
    """
    Dynamically load payloads.py from a specific domain.
    
    Parameters
    ----------
    domain : str
        Domain name (e.g., 'cybersecurity', 'misinformation')
    
    Returns
    -------
    list : list of payload dictionaries
    
    Raises
    ------
    ValueError : if domain not found or payloads.py missing
    """
    domains_dir = Path(__file__).parent / "domains"
    domain_path = domains_dir / domain
    payloads_file = domain_path / "payloads.py"
    
    if not domain_path.exists():
        available = get_available_domains()
        raise ValueError(
            f"Domain '{domain}' not found. Available domains: {', '.join(available)}"
        )
    
    if not payloads_file.exists():
        raise ValueError(
            f"payloads.py not found in domain '{domain}' at {payloads_file}"
        )
    
    # Dynamically load the payloads.py file
    spec = importlib.util.spec_from_file_location(
        f"redgen_payloads.domains.{domain}.payloads",
        payloads_file
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    
    if not hasattr(module, "PAYLOADS"):
        raise ValueError(
            f"Module {payloads_file} does not export PAYLOADS list"
        )
    
    payloads = module.PAYLOADS
    
    # Ensure each payload has required fields
    for i, p in enumerate(payloads):
        p.setdefault("id", f"{domain}_{i}")
        p.setdefault("severity", 5)
        p.setdefault("category", domain)
        # Convert 'behavior' field to 'text' if needed
        if "behavior" in p and "text" not in p:
            p["text"] = p["behavior"]
    
    return payloads


def load_templates() -> list:
    """
    Load templates from templates.py module.
    
    Returns
    -------
    list : list of template dictionaries
    """
    from . import templates as templates_module
    
    # Get all template functions - exclude type annotations and non-callables
    template_functions = []
    for name, obj in vars(templates_module).items():
        # Skip private items, type annotations, utility functions, and non-callables
        if (name.startswith('_') or 
            name in ['Optional', 'Dict', 'Callable', 'get_templates', 'apply_template'] or
            not callable(obj) or
            hasattr(obj, '__module__') and obj.__module__ != 'redgen.redgen_payloads.templates'):
            continue
        template_functions.append((name, obj))
    
    template_list = []
    
    for idx, (name, func) in enumerate(template_functions):
        template_list.append({
            "id": f"template_{idx}",
            "name": name,
            "text": None,  # Will be filled by the function
            "func": func,
            "severity": 5,
            "attack_type": "template_usage",
            "generation_mode": "original",
        })
    
    return template_list


def apply_template(template_dict: dict, payload_text: str) -> str:
    """
    Apply a template to a payload by calling the template function.
    
    Parameters
    ----------
    template_dict : dict
        Template dictionary with 'func' key
    payload_text : str
        The payload/behavior text to wrap
    
    Returns
    -------
    str : rendered prompt
    """
    if "func" not in template_dict:
        return payload_text
    
    template_func = template_dict["func"]
    try:
        return template_func(payload_text)
    except Exception as e:
        print(f"Warning: Failed to apply template {template_dict.get('name', '?')}: {e}")
        return payload_text
